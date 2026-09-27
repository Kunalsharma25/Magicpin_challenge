import threading
from typing import Dict, Tuple, Any, Optional
from models import CategoryContext, MerchantContext, CustomerContext, TriggerContext

class ContextStore:
    def __init__(self):
        self._lock = threading.Lock()
        # Storage: (scope, context_id) -> {"version": int, "payload": dict}
        self._store: Dict[Tuple[str, str], Dict[str, Any]] = {}        # Reverse mapping: merchant_id -> category_slug
        self._merchant_to_category: Dict[str, str] = {}

    def push_context(self, scope: str, context_id: str, version: int, payload: Dict[str, Any]) -> Tuple[bool, Optional[str], int]:
        """
        Pushes a context.
        Returns (accepted, error_msg, http_status_code).
        Idempotent if version == current_version.
        Rejects (409) if version < current_version.
        """
        key = (scope, context_id)
        with self._lock:
            existing = self._store.get(key)
            if existing:
                curr_version = existing["version"]
                if version < curr_version:
                    return False, f"stale_version: incoming version {version} <= current {curr_version}", 409
                if version == curr_version:
                    # Idempotent re-post
                    return True, None, 200

            # Store or update
            self._store[key] = {
                "version": version,
                "payload": payload
            }

            # Update reverse index if scope is merchant
            if scope == "merchant":
                cat_slug = payload.get("category_slug")
                if cat_slug:
                    self._merchant_to_category[context_id] = cat_slug

            return True, None, 200

    def get_raw(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._store.get((scope, context_id))
            return item["payload"] if item else None

    def get_category(self, slug: str) -> Optional[CategoryContext]:
        raw = self.get_raw("category", slug)
        if raw is None:
            return None
        return CategoryContext.model_validate(raw)

    def get_merchant(self, merchant_id: str) -> Optional[MerchantContext]:
        raw = self.get_raw("merchant", merchant_id)
        if raw is None:
            return None
        return MerchantContext.model_validate(raw)

    def get_customer(self, customer_id: str) -> Optional[CustomerContext]:
        raw = self.get_raw("customer", customer_id)
        if raw is None:
            return None
        return CustomerContext.model_validate(raw)

    def get_trigger(self, trigger_id: str) -> Optional[TriggerContext]:
        raw = self.get_raw("trigger", trigger_id)
        if raw is None:
            return None
        return TriggerContext.model_validate(raw)

    def get_category_for_merchant(self, merchant_id: str) -> Optional[CategoryContext]:
        merchant = self.get_merchant(merchant_id)
        if not merchant or not merchant.category_slug:
            with self._lock:
                slug = self._merchant_to_category.get(merchant_id)
            if slug:
                return self.get_category(slug)
            return None
        return self.get_category(merchant.category_slug)

    def wipe(self):
        with self._lock:
            self._store.clear()
            self._merchant_to_category.clear()

# Global store instance
store = ContextStore()
