import threading
from typing import Dict, Set

class CadenceManager:
    def __init__(self, max_per_tick: int = 1):
        self._lock = threading.Lock()
        self.max_per_tick = max_per_tick
        self._merchant_tick_counts: Dict[str, int] = {}
        self._customer_tick_counts: Dict[str, int] = {}

    def can_send(self, merchant_id: str, customer_id: str = None) -> bool:
        with self._lock:
            m_count = self._merchant_tick_counts.get(merchant_id, 0)
            if m_count >= self.max_per_tick:
                return False
            if customer_id:
                c_count = self._customer_tick_counts.get(customer_id, 0)
                if c_count >= self.max_per_tick:
                    return False
            return True

    def record_send(self, merchant_id: str, customer_id: str = None):
        with self._lock:
            self._merchant_tick_counts[merchant_id] = self._merchant_tick_counts.get(merchant_id, 0) + 1
            if customer_id:
                self._customer_tick_counts[customer_id] = self._customer_tick_counts.get(customer_id, 0) + 1

    def reset_tick(self):
        with self._lock:
            self._merchant_tick_counts.clear()
            self._customer_tick_counts.clear()

cadence_manager = CadenceManager()
