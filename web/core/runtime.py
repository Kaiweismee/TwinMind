"""共用執行資源：沿用原本推薦與討論共用的執行緒池。"""
import logging
from concurrent.futures import ThreadPoolExecutor

_log = logging.getLogger("web.app")
_RECOMMEND_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="topic_recommend")
