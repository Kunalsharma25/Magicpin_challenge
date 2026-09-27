import threading
from typing import Set, Dict, List

class SuppressionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._sent_suppression_keys: Set[str] = set()
        self._sent_bodies_by_conv: Dict[str, List[str]] = {}

    def is_suppressed(self, suppression_key: str) -> bool:
        if not suppression_key:
            return False
        with self._lock:
            return suppression_key in self._sent_suppression_keys

    def record_send(self, suppression_key: str, body: str, conv_id: str):
        with self._lock:
            if suppression_key:
                self._sent_suppression_keys.add(suppression_key)
            if conv_id:
                if conv_id not in self._sent_bodies_by_conv:
                    self._sent_bodies_by_conv[conv_id] = []
                self._sent_bodies_by_conv[conv_id].append(body)

    def get_history(self, conv_id: str) -> List[str]:
        with self._lock:
            return list(self._sent_bodies_by_conv.get(conv_id, []))

    def clear(self):
        with self._lock:
            self._sent_suppression_keys.clear()
            self._sent_bodies_by_conv.clear()

suppression_manager = SuppressionManager()
