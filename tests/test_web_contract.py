"""網頁拆分的回歸測試；使用替身，不連 PostgreSQL、不呼叫 OpenAI。

執行：./venv/bin/python -B -m unittest discover -s tests -v
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app
from web.core.dependencies import get_optional_user
from web.repositories import chat_store
from web.repositories import user_store
from web.core.settings import AUTH_COOKIE


class WebContractTests(unittest.TestCase):
    def setUp(self):
        # 故意不使用 TestClient 的 context manager：避免執行真實建表與暖機。
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.db_guard = patch('psycopg2.connect', side_effect=AssertionError('測試不可連接真實資料庫'))
        self.db_guard.start()
        self.addCleanup(self.db_guard.stop)
        self.addCleanup(app.dependency_overrides.clear)

    def as_user(self, user=None):
        user = user or {'id': 7, 'display_name': '測試使用者', 'active_twin_id': 3}
        app.dependency_overrides[get_optional_user] = lambda: user
        return user

    def test_openapi_matches_original_contract(self):
        fixture = Path(__file__).parent / 'fixtures' / 'web_openapi.json'
        self.assertEqual(json.loads(fixture.read_text()), app.openapi())

    def test_home_and_static_entry_are_available(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/js/init.js', response.text)
        self.assertEqual(self.client.get('/static/js/init.js').status_code, 200)
        self.assertEqual(self.client.get('/lab').status_code, 200)

    def test_protected_features_require_login(self):
        app.dependency_overrides[get_optional_user] = lambda: None
        for path in ('/api/twins', '/api/sessions', '/api/profile', '/api/media-library',
                     '/api/person-chat/threads', '/api/twin-chat/messages', '/api/notifications'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {'detail': '請先登入'})

    def test_register_sets_cookie_and_syncs_knowledge(self):
        user = {'id': 7, 'display_name': '測試使用者'}
        with patch.object(user_store, 'register_user', return_value=user), \
             patch.object(user_store, 'create_auth_session', return_value=('test-token', None)), \
             patch('web.routers.auth._sync_user_rag') as sync:
            response = self.client.post('/api/auth/register', json={
                'email': 'test@example.com', 'username': 'tester', 'password': 'test-password',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies[AUTH_COOKIE], 'test-token')
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertEqual(response.json()['user']['id'], 7)
        sync.assert_called_once_with(user)

    def test_static_session_path_is_not_parsed_as_an_id(self):
        with patch.object(chat_store, 'list_all_session_ids', return_value=[3, 9]):
            response = self.client.get('/api/sessions/all-ids')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ids': [3, 9]})

    def test_room_access_denied_before_loading_messages(self):
        self.as_user()
        with patch.object(chat_store, 'check_session_access', return_value=(False, '無權限')):
            response = self.client.get('/api/sessions/3')
        self.assertEqual(response.status_code, 403)

    def test_other_users_attachment_is_forbidden(self):
        self.as_user()
        response = self.client.get('/api/twin-chat/files/99/test.txt')
        self.assertEqual(response.status_code, 403)

    def test_rag_query_preserves_filters_and_output(self):
        rows = [{'chunk_id': 12, 'similarity': .876543, 'source_type': 'wiki',
                 'title': '範例', 'source_url': 'https://example.com', 'content': '測試內容'}]
        with patch('web.routers.query.search_chunks', return_value=rows) as search, \
             patch('web.routers.query.format_context', return_value='參考資料'):
            response = self.client.post('/api/query', json={
                'question': ' 問題 ', 'person': ' example ', 'top_k': 4, 'types': 'wiki, news',
            })
        self.assertEqual(response.status_code, 200)
        search.assert_called_once_with('問題', person_slug='example', top_k=4,
                                       source_types=['wiki', 'news'])
        self.assertEqual(response.json()['results'][0]['similarity'], .8765)
        self.assertEqual(response.json()['context'], '參考資料')

    def test_invalid_rag_query_rejected(self):
        self.assertEqual(self.client.post('/api/query', json={
            'question': '', 'person': 'example',
        }).status_code, 400)
        self.assertEqual(self.client.post('/api/query', json={
            'question': '問題', 'person': 'example', 'top_k': -1,
        }).status_code, 422)

    def test_next_turn_passes_user_and_options(self):
        user = self.as_user()
        with patch.object(chat_store, 'check_session_access', return_value=(True, None)), \
             patch('web.routers.discussion._run_single_turn', return_value={'done': True}) as turn:
            response = self.client.post('/api/sessions/3/turn', json={'top_k': 4})
        self.assertEqual(response.json(), {'done': True})
        self.assertEqual(turn.call_args.args, (3,))
        self.assertEqual(turn.call_args.kwargs['top_k'], 4)
        self.assertEqual(turn.call_args.kwargs['profile']['id'], user['id'])

    def test_message_flow_stores_message_and_returns_state(self):
        self.as_user()
        with patch.object(chat_store, 'check_session_access', return_value=(True, None)), \
             patch.object(chat_store, 'get_session', return_value={'topic': '測試', 'members': []}), \
             patch.object(chat_store, 'add_message', return_value={'id': 42, 'content': '你好'}) as save, \
             patch('web.services.messages._turn_state', return_value={'done': True, 'next_label': None}):
            response = self.client.post('/api/sessions/3/messages', json={'content': ' 你好 '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.args, (3, 'user', '你好'))
        self.assertEqual(response.json()['user_message']['id'], 42)
        self.assertFalse(response.json()['awaiting_turn'])

    def test_startup_registration_and_initializers(self):
        from web.core.lifecycle import startup
        self.assertIn(startup, app.router.on_startup)
        with patch('web.core.lifecycle.chat_store.ensure_chat_schema') as chat, \
             patch('web.core.lifecycle.user_store.ensure_user_schema') as users, \
             patch('web.core.lifecycle.twin_chat.ensure_twin_chat_schema') as twins, \
             patch('web.core.lifecycle.person_chat.ensure_person_chat_schema') as persons, \
             patch('web.core.lifecycle.PROFILE_AVATAR_ROOT') as avatar, \
             patch('web.core.lifecycle.threading.Thread') as thread:
            startup()
        for initializer in (chat, users, twins, persons):
            initializer.assert_called_once_with()
        avatar.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        thread.return_value.start.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
