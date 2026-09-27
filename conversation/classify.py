from conversation.state import ConversationState

CANNED_MARKERS = [
    "thank you for contacting", "will respond shortly", "automated",
    "team will get back", "shukriya", "team tak pahuncha", "out of office",
    "automatic reply"
]

COMMIT_PHRASES = [
    "let's do it", "lets do it", "ok let's", "go ahead", "yes i want",
    "i want to join", "haan kar do", "chalo shuru karo", "start karo", "proceed",
    "whats next", "what's next", "ok lets", "yes do it"
]

HOSTILE_PHRASES = [
    "stop messaging", "spam", "useless", "don't message", "dont message",
    "stop texting", "remove me", "unsubscribe", "block"
]

def is_auto_reply(state: ConversationState, incoming: str) -> bool:
    inc_lower = incoming.strip().lower()
    
    # 1. Canned phrase heuristic
    if any(m in inc_lower for m in CANNED_MARKERS):
        return True
        
    # 2. Verbatim repeat heuristic (catches if sent >= 2 times prior)
    prior_merchant_turns = [t.body.strip().lower() for t in state.turns if t.from_role in ("merchant", "customer")]
    if prior_merchant_turns.count(inc_lower) >= 1:
        return True
        
    return False

def is_commitment(incoming: str) -> bool:
    inc_lower = incoming.strip().lower()
    return any(p in inc_lower for p in COMMIT_PHRASES)

def is_hostile(incoming: str) -> bool:
    inc_lower = incoming.strip().lower()
    return any(p in inc_lower for p in HOSTILE_PHRASES)
