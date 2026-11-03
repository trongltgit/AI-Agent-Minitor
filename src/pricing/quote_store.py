"""
Quote single-use store.
Quote được tạo server-side, gắn user/agent, chỉ claim được 1 lần (anti-replay execute).
"""
from __future__ import annotations
import time
from threading import Lock
from typing import Dict, Any, Optional
from collections import OrderedDict

_TTL = 120  # giây
_MAX = 5000


class QuoteStore:
    def __init__(self):
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = Lock()

    def _purge(self):
        now = time.time()
        dead = [k for k, v in self._store.items() if now - v["created_at"] > _TTL or v.get("used")]
        for k in dead:
            self._store.pop(k, None)
        while len(self._store) > _MAX:
            self._store.popitem(last=False)

    def put(self, quote_id: str, payload: Dict[str, Any], owner: str) -> None:
        with self._lock:
            self._purge()
            self._store[quote_id] = {
                "payload": payload,
                "owner": owner,
                "created_at": time.time(),
                "used": False,
            }

    def get(self, quote_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._purge()
            item = self._store.get(quote_id)
            if not item or item["used"]:
                return None
            if time.time() - item["created_at"] > _TTL:
                self._store.pop(quote_id, None)
                return None
            return item

    def claim(self, quote_id: str, owner: str) -> Optional[Dict[str, Any]]:
        """Atomic single-use claim. Trả payload nếu thành công, None nếu đã dùng / sai owner / hết hạn."""
        with self._lock:
            self._purge()
            item = self._store.get(quote_id)
            if not item:
                return None
            if item["used"]:
                return None
            if item["owner"] != owner:
                return None
            if time.time() - item["created_at"] > _TTL:
                self._store.pop(quote_id, None)
                return None
            item["used"] = True
            return item["payload"]

    def stats(self) -> Dict[str, int]:
        with self._lock:
            self._purge()
            used = sum(1 for v in self._store.values() if v.get("used"))
            return {"active": len(self._store) - used, "used": used, "total": len(self._store)}


quote_store = QuoteStore()
