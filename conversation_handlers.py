from typing import Dict, Any
from models import ReplyRequest
from conversation.respond import handle_reply

def respond(state: Any, merchant_message: str) -> Dict[str, Any]:
    """
    Deliverable required by brief §7:
    respond(state, merchant_message) -> dict
    Delegates to conversation/respond.py handle_reply logic.
    """
    conv_id = getattr(state, "conversation_id", "conv_default")
    merchant_id = getattr(state, "merchant_id", "m_default")
    customer_id = getattr(state, "customer_id", None)
    
    req = ReplyRequest(
        conversation_id=conv_id,
        merchant_id=merchant_id,
        customer_id=customer_id,
        from_role="merchant",
        message=merchant_message
    )
    
    resp = handle_reply(req)
    
    out = {"action": resp.action}
    if resp.body:
        out["body"] = resp.body
    if resp.wait_seconds is not None:
        out["wait_seconds"] = resp.wait_seconds
    if resp.rationale:
        out["rationale"] = resp.rationale
        
    return out
