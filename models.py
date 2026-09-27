from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# Base context model with defensive extra fields allowed
class OpenBaseModel(BaseModel):
    model_config = {"extra": "allow"}

class CategoryContext(OpenBaseModel):
    slug: str
    display_name: Optional[str] = None
    voice: Optional[Dict[str, Any]] = None
    offer_catalog: Optional[List[Dict[str, Any]]] = None
    peer_stats: Optional[Dict[str, Any]] = None
    digest: Optional[List[Dict[str, Any]]] = None

class MerchantContext(OpenBaseModel):
    merchant_id: str
    category_slug: Optional[str] = None
    identity: Optional[Dict[str, Any]] = None
    subscription: Optional[Dict[str, Any]] = None
    performance: Optional[Dict[str, Any]] = None
    offers: Optional[List[Dict[str, Any]]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    customer_aggregate: Optional[Dict[str, Any]] = None
    signals: Optional[List[str]] = None
    review_themes: Optional[List[Dict[str, Any]]] = None

class CustomerContext(OpenBaseModel):
    customer_id: str
    merchant_id: str
    identity: Optional[Dict[str, Any]] = None
    relationship: Optional[Dict[str, Any]] = None
    state: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    consent: Optional[Dict[str, Any]] = None

class TriggerContext(OpenBaseModel):
    id: str
    scope: str
    kind: str
    source: str
    merchant_id: str
    customer_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    urgency: int = 1
    suppression_key: str
    expires_at: Optional[str] = None

# API Request/Response models
class ContextPushRequest(OpenBaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None

class ContextPushResponse(OpenBaseModel):
    accepted: bool
    error: Optional[str] = None

class TickRequest(OpenBaseModel):
    now: str
    available_triggers: List[str]

class TickAction(OpenBaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: str
    trigger_id: str
    template_name: Optional[str] = None
    template_params: Optional[List[str]] = None
    body: str
    cta: str
    suppression_key: str
    rationale: str

class TickResponse(OpenBaseModel):
    actions: List[TickAction] = Field(default_factory=list)

class ReplyRequest(OpenBaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: Optional[str] = None
    turn_number: Optional[int] = 1

class ReplyResponse(OpenBaseModel):
    action: str  # "send" | "wait" | "end"
    body: Optional[str] = None
    wait_seconds: Optional[int] = None
    rationale: Optional[str] = None

class HealthzResponse(OpenBaseModel):
    status: str = "ok"

class MetadataResponse(OpenBaseModel):
    team_name: str = "Vera-Beater"
    model: str = "gemini-2.5-flash"
