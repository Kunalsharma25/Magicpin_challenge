import re
import difflib
from typing import List, Dict, Any, Optional, Set, Tuple

# Hinglish marker set for language match verification
HINGLISH_MARKERS = {
    "hai", "aapka", "kya", "kar", "bhi", "mein", "nahi", "nahin",
    "acha", "accha", "karo", "haan", "chalo", "ji", "apne", "wale",
    "raha", "rahi", "huye", "ho", "huya", "sakta", "sakti", "lekin"
}

# Structural jargon terms to block
JARGON_BLOCKLIST = [
    "ctr_below_peer_median", "suppression_key", "signals",
    "lapsed_180d_plus", "trg_", "m_", "c_"
]

def check_taboo_words(body: str, vocab_taboo: List[str]) -> Tuple[bool, Optional[str]]:
    body_lower = body.lower()
    for taboo in vocab_taboo or []:
        if taboo and taboo.lower() in body_lower:
            return False, f"Message contains taboo word/phrase: '{taboo}'"
    return True, None

def check_jargon_leaks(body: str, signals: List[str], trigger_id: str = "", suppression_key: str = "") -> Tuple[bool, Optional[str]]:
    body_lower = body.lower()
    
    # Check merchant signals
    for sig in signals or []:
        if sig and sig.lower() in body_lower:
            return False, f"Message leaks internal signal term: '{sig}'"
            
    # Check blocklist terms
    for j in JARGON_BLOCKLIST:
        if j in body_lower:
            return False, f"Message leaks internal jargon/id: '{j}'"
            
    if trigger_id and trigger_id.lower() in body_lower:
        return False, f"Message leaks trigger id: '{trigger_id}'"
        
    if suppression_key and suppression_key.lower() in body_lower:
        return False, f"Message leaks suppression key: '{suppression_key}'"
        
    return True, None

def extract_grounding_tokens(data: Any, tokens: Set[str]):
    if isinstance(data, dict):
        for k, v in data.items():
            if k == "common_quote":  # Never include verbatim quotes as ground truth for exact match
                continue
            extract_grounding_tokens(v, tokens)
    elif isinstance(data, list):
        for item in data:
            extract_grounding_tokens(item, tokens)
    elif isinstance(data, (int, float)):
        tokens.add(str(data))
    elif isinstance(data, str):
        # Extract numbers, percentages, dates
        found_nums = re.findall(r'\d+(?:\.\d+)?', data)
        tokens.update(found_nums)
        # Extract words/proper nouns
        words = re.findall(r'[A-Za-z0-9]+', data)
        for w in words:
            if len(w) > 2:
                tokens.add(w.lower())

def check_fabrication(body: str, category_dict: Dict, merchant_dict: Dict, trigger_dict: Dict, customer_dict: Optional[Dict]) -> Tuple[bool, Optional[str]]:
    reference_tokens: Set[str] = set()
    extract_grounding_tokens(category_dict, reference_tokens)
    extract_grounding_tokens(merchant_dict, reference_tokens)
    extract_grounding_tokens(trigger_dict, reference_tokens)
    if customer_dict:
        extract_grounding_tokens(customer_dict, reference_tokens)

    # Extract all numbers from the message body
    body_numbers = re.findall(r'\d+(?:\.\d+)?', body)
    for num_str in body_numbers:
        # Check if number or rounded variant exists in reference_tokens
        num_val = float(num_str)
        found = False
        if num_str in reference_tokens or str(int(num_val)) in reference_tokens:
            found = True
        else:
            # Check near matches (e.g. percentages)
            for ref in reference_tokens:
                try:
                    ref_val = float(ref)
                    if abs(ref_val - num_val) < 0.05 or abs(ref_val * 100 - num_val) < 0.05:
                        found = True
                        break
                except ValueError:
                    continue
        if not found and num_val not in [1, 2, 7, 24, 30]:  # Ignore common standard numbers like 1, 2, 7, 24, 30
            return False, f"Message contains ungrounded number: '{num_str}'"
            
    return True, None

def check_cta_shape(body: str, cta: str) -> Tuple[bool, Optional[str]]:
    if cta == "binary":
        # Check for multi-option menu patterns
        multi_option = re.search(r'reply\s+\w+\s+for\s+.*,\s*\w+\s+for', body, re.IGNORECASE)
        if multi_option:
            return False, "Binary CTA must be a single yes/no or choice, not a multi-option menu."
    return True, None

def check_language_match(body: str, merchant_languages: List[str], customer_lang_pref: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    expects_hinglish = False
    if merchant_languages and "hi" in merchant_languages:
        expects_hinglish = True
    if customer_lang_pref and ("hi" in customer_lang_pref.lower() or "mix" in customer_lang_pref.lower()):
        expects_hinglish = True

    if expects_hinglish:
        body_words = set(re.findall(r'[a-zA-Z]+', body.lower()))
        if not (body_words & HINGLISH_MARKERS):
            return False, "Message expected Hindi/Hinglish code-mix but no Hinglish marker words were found."
            
    return True, None

def check_anti_repetition(body: str, history: List[str]) -> Tuple[bool, Optional[str]]:
    body_clean = body.strip().lower()
    for prev in history or []:
        prev_clean = prev.strip().lower()
        if body_clean == prev_clean:
            return False, "Message is byte-identical to a previously sent message."
        ratio = difflib.SequenceMatcher(None, body_clean, prev_clean).ratio()
        if ratio > 0.90:
            return False, f"Message is >90% similar ({ratio:.2f}) to a previously sent message."
    return True, None

def check_send_as(send_as: str, has_customer: bool) -> Tuple[bool, Optional[str]]:
    if has_customer and send_as != "merchant_on_behalf":
        return False, "send_as must be 'merchant_on_behalf' when customer context is present."
    if not has_customer and send_as != "vera":
        return False, "send_as must be 'vera' when customer context is not present."
    return True, None

def check_length_sanity(body: str) -> Tuple[bool, Optional[str]]:
    if not body or not body.strip():
        return False, "Message body is empty."
    if len(body) > 800:
        return False, f"Message body is too long ({len(body)} chars > 800 max)."
    return True, None

def check_consent_scope(customer_dict: Optional[Dict], trigger_kind: str) -> Tuple[bool, Optional[str]]:
    if not customer_dict:
        return True, None
        
    consent = customer_dict.get("consent", {})
    opted_in_at = consent.get("opted_in_at")
    scope = consent.get("scope", [])
    
    if opted_in_at is None and not scope:
        return False, "Customer has no consent record (opted_in_at is null)."
        
    # Check promotional vs recall scope matching
    is_promo = any(term in trigger_kind for term in ["offer", "discount", "festival", "winback", "trial"])
    if is_promo and "promotional_offers" not in scope and "all" not in scope:
        return False, f"Trigger '{trigger_kind}' requires 'promotional_offers' consent scope."
        
    return True, None

def validate_message(
    body: str,
    cta: str,
    send_as: str,
    category_dict: Dict[str, Any],
    merchant_dict: Dict[str, Any],
    trigger_dict: Dict[str, Any],
    customer_dict: Optional[Dict[str, Any]] = None,
    history: Optional[List[str]] = None
) -> Tuple[bool, List[str]]:
    """
    Runs all 9 post-LLM validation checks.
    Returns (is_valid, list_of_violation_strings).
    """
    violations = []

    # 1. Taboo check
    vocab_taboo = category_dict.get("voice", {}).get("vocab_taboo", [])
    ok, err = check_taboo_words(body, vocab_taboo)
    if not ok and err: violations.append(err)

    # 2. Jargon leak check
    signals = merchant_dict.get("signals", [])
    trg_id = trigger_dict.get("id", "")
    supp_key = trigger_dict.get("suppression_key", "")
    ok, err = check_jargon_leaks(body, signals, trg_id, supp_key)
    if not ok and err: violations.append(err)

    # 3. Fabrication guard
    ok, err = check_fabrication(body, category_dict, merchant_dict, trigger_dict, customer_dict)
    if not ok and err: violations.append(err)

    # 4. CTA shape check
    ok, err = check_cta_shape(body, cta)
    if not ok and err: violations.append(err)

    # 5. Language match check
    m_langs = merchant_dict.get("identity", {}).get("languages", [])
    c_pref = customer_dict.get("identity", {}).get("language_pref") if customer_dict else None
    ok, err = check_language_match(body, m_langs, c_pref)
    if not ok and err: violations.append(err)

    # 6. Anti-repetition check
    ok, err = check_anti_repetition(body, history or [])
    if not ok and err: violations.append(err)

    # 7. send_as check
    ok, err = check_send_as(send_as, customer_dict is not None)
    if not ok and err: violations.append(err)

    # 8. Length sanity
    ok, err = check_length_sanity(body)
    if not ok and err: violations.append(err)

    # 9. Consent scope check
    ok, err = check_consent_scope(customer_dict, trigger_dict.get("kind", ""))
    if not ok and err: violations.append(err)

    return len(violations) == 0, violations
