from dataclasses import dataclass, field
from typing import List, Optional, Literal, Dict

@dataclass
class Turn:
    from_role: str
    body: str
    ts: Optional[str] = None

@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    turns: List[Turn] = field(default_factory=list)
    last_bot_bodies: List[str] = field(default_factory=list)
    mode: Literal["pitch", "qualifying", "action", "closing"] = "qualifying"
    consecutive_unanswered: int = 0
    auto_reply_count: int = 0
    detected_language: str = "en"

# In-memory store for active conversations
conversation_store: Dict[str, ConversationState] = {}

def get_or_create_conversation(conv_id: str, merchant_id: str, customer_id: Optional[str] = None) -> ConversationState:
    if conv_id not in conversation_store:
        conversation_store[conv_id] = ConversationState(
            conversation_id=conv_id,
            merchant_id=merchant_id,
            customer_id=customer_id
        )
    return conversation_store[conv_id]
