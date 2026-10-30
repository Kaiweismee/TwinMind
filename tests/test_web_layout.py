"""移動檔案後的匯入、路徑與延遲呼叫回歸測試。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web.core import rag_backend, settings
from web.conversations import discussion_insights, twin_chat
from web.knowledge import user_rag
from web.recommendations import topic_fit, topic_fit_llm, topic_fit_semantic
from web.repositories import chat_store, user_store

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WebLayoutTests(unittest.TestCase):
    def setUp(self):
        guard = patch('psycopg2.connect', side_effect=AssertionError('不可連接真實資料庫'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_all_modules_import_without_app_bootstrap(self):
        # 使用新的 Python 行程，避免先匯入 app 掩蓋缺失的相依設定。
        modules = sorted((
            '.'.join(p.relative_to(PROJECT_ROOT).with_suffix('').parts)
            for p in (PROJECT_ROOT / 'web').rglob('*.py')
            if p.name != '__init__.py' and p.name != 'app.py'
        ), reverse=True)
        code = '''
import importlib, json, sys
from unittest.mock import patch
with patch('psycopg2.connect', side_effect=AssertionError('unexpected database access')), \\
     patch('openai.OpenAI', side_effect=AssertionError('unexpected AI client')):
    for name in json.loads(sys.argv[1]):
        importlib.import_module(name)
assert not any(name in sys.modules for name in (
    'chat_store', 'user_store', 'discussion', 'twin_chat', 'person_chat',
    'user_rag', 'topic_fit', 'topic_fit_llm', 'topic_fit_semantic',
)), 'Old web modules must not be loaded as top-level aliases'
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, json.dumps(modules)],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_resources_still_use_project_root(self):
        self.assertEqual(settings.ROOT, PROJECT_ROOT)
        self.assertEqual(settings.STATIC, PROJECT_ROOT / 'web/static')
        self.assertEqual(settings.PROFILE_AVATAR_ROOT, PROJECT_ROOT / 'data/profile_avatars')
        self.assertEqual(twin_chat.UPLOAD_ROOT, PROJECT_ROOT / 'data/twin_uploads')
        self.assertTrue((settings.STATIC / 'index.html').is_file())

    def test_upload_text_uses_moved_extractor(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(twin_chat, 'UPLOAD_ROOT', Path(directory)):
            item = twin_chat.save_upload(7, 'note.txt', '我是資管系學生'.encode())
            self.assertEqual(item['text_preview'], '我是資管系學生')
            saved = twin_chat.get_upload_path(7, item['stored_name'])
            self.assertEqual(saved.read_text(), '我是資管系學生')

    def test_backfill_resolves_conversations_and_repositories(self):
        with patch.object(user_rag, 'ensure_user_person'), \
             patch.object(user_store, 'list_user_twins', return_value=[{'id': 3}]), \
             patch.object(twin_chat, 'list_messages', return_value=[
                 {'id': 1, 'role': 'user', 'content': '背景資料'},
                 {'id': 2, 'role': 'assistant', 'content': '回答'},
             ]), \
             patch.object(user_rag, 'ingest_twin_chat_message', return_value=[10]) as ingest:
            count = user_rag.backfill_user_knowledge(7, display_name='測試')
        self.assertEqual(count, 1)
        ingest.assert_called_once()
        self.assertEqual(ingest.call_args.args, (7, 3))
        self.assertEqual(ingest.call_args.kwargs['role'], 'user')

    def test_llm_recommendations_use_shared_rag_backend(self):
        topic_fit_llm._EXCERPT_CACHE.clear()
        self.addCleanup(topic_fit_llm._EXCERPT_CACHE.clear)
        with patch.object(topic_fit_llm, '_LLM_USE_VECTOR', True), \
             patch.object(rag_backend, 'batch_search_chunks', return_value={'example': [{'content': '資料'}]}) as search, \
             patch.object(rag_backend, 'format_context', return_value='參考資料'), \
             patch.object(topic_fit_llm, '_db_excerpts', side_effect=AssertionError('不應使用備援')):
            excerpts = topic_fit_llm.prefetch_rag_excerpts('測試議題', ['example'])
        self.assertEqual(excerpts, {'example': '參考資料'})
        search.assert_called_once()

    def test_semantic_ranking_does_not_silently_fall_back(self):
        expected = [{'slug': 'example', 'topic_fit_score': 80}]
        with patch.object(topic_fit, '_topic_fit_backend', return_value='semantic'), \
             patch.object(topic_fit_semantic, 'rank_persons_for_topic_semantic', return_value=expected) as rank:
            actual = topic_fit.rank_persons_for_topic('測試', [{'slug': 'example'}], limit=1)
        self.assertEqual(actual, expected)
        rank.assert_called_once_with('測試', [{'slug': 'example'}], limit=1)

    def test_insight_cache_loads_from_moved_repository(self):
        row = {'message_count': 4, 'llm_message_count': 4, 'insights': {'ready': True}}
        with patch.object(discussion_insights, '_insights_cache', {}), \
             patch.object(discussion_insights, '_insights_llm_at', {}), \
             patch.object(chat_store, 'load_session_insights', return_value=row) as load:
            result = discussion_insights.get_cached_insights(777, 4)
        self.assertEqual(result, {'ready': True})
        load.assert_called_once_with(777)


if __name__ == '__main__':
    unittest.main()
