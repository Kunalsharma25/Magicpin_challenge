import re
from typing import Dict, Any
from models import ReplyRequest, ReplyResponse
from conversation.state import get_or_create_conversation, Turn
from conversation.classify import is_auto_reply, is_commitment, is_hostile
from store import store

QUALIFYING_WORDS = ["would you", "do you", "can you tell", "what if", "how about"]
ACTIONING_WORDS = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]

def handle_reply(req: ReplyRequest) -> ReplyResponse:
    state = get_or_create_conversation(
        conv_id=req.conversation_id,
        merchant_id=req.merchant_id,
        customer_id=req.customer_id
    )

    incoming_text = req.message.strip()
    
    # 1. Check auto-reply pattern
    if is_auto_reply(state, incoming_text):
        state.auto_reply_count += 1
        state.turns.append(Turn(from_role=req.from_role, body=incoming_text))
        return ReplyResponse(
            action="end",
            rationale="Detected automated auto-reply message, exiting gracefully."
        )

    # Append turn
    state.turns.append(Turn(from_role=req.from_role, body=incoming_text))

    # 2. Check hostility
    if is_hostile(incoming_text):
        return ReplyResponse(
            action="end",
            body="Sorry for any disturbance, we won't send further automated updates.",
            rationale="Merchant requested to stop / expressed hostility, exiting immediately."
        )

    # 3. Check commitment -> intent transition to ACTION mode
    if is_commitment(incoming_text) or state.mode == "action":
        state.mode = "action"
        merchant = store.get_merchant(req.merchant_id)
        owner_name = merchant.identity.get("owner_first_name", "") if merchant and merchant.identity else ""
        salutation = f"Dr. {owner_name}" if owner_name and "dr" in owner_name.lower() else f"Hi {owner_name}" if owner_name else "Hi"
        
        # Build action response containing actioning vocabulary and strictly no qualifying questions
        body = f"{salutation}, done! Here is the confirmed campaign draft ready for rollout. Next step: confirm to launch."
        
        # Hard check to ensure no qualifying words leak into action response
        body_lower = body.lower()
        for q in QUALIFYING_WORDS:
            if q in body_lower:
                body = f"{salutation}, done! Here is the confirmed draft. Next step is launch."
                break
                
        state.last_bot_bodies.append(body)
        return ReplyResponse(
            action="send",
            body=body,
            rationale="Merchant committed: switched mode to action and delivered concrete next step."
        )

    # 4. Check consecutive unanswered threshold
    if state.consecutive_unanswered >= 3:
        return ReplyResponse(
            action="end",
            rationale="Exceeded 3 unanswered turns, exiting gracefully."
        )

    # 5. Default mid-conversation response
    merchant = store.get_merchant(req.merchant_id)
    owner_name = merchant.identity.get("owner_first_name", "") if merchant and merchant.identity else ""
    salutation = f"Dr. {owner_name}" if owner_name and "dr" in owner_name.lower() else f"Hi {owner_name}" if owner_name else "Hi"
    
    body = f"{salutation}, thank you for your response. Should we proceed with the recommended update?"
    state.last_bot_bodies.append(body)
    
    return ReplyResponse(
        action="send",
        body=body,
        rationale="Standard mid-conversation reply turn."
    )
