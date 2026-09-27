from typing import List, Dict, Any
from datetime import datetime
from store import store
from composer import compose
from engagement.suppression import suppression_manager
from engagement.cadence import cadence_manager

def parse_iso_datetime(dt_str: str) -> float:
    if not dt_str:
        return float('inf')
    try:
        clean_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str).timestamp()
    except Exception:
        return float('inf')

def schedule_tick(available_trigger_ids: List[str], now_iso: str) -> List[Dict[str, Any]]:
    cadence_manager.reset_tick()
    now_ts = parse_iso_datetime(now_iso)
    
    candidates = []

    for tid in available_trigger_ids:
        trigger = store.get_trigger(tid)
        if not trigger:
            continue
            
        merchant = store.get_merchant(trigger.merchant_id)
        if not merchant:
            continue
            
        category = store.get_category_for_merchant(trigger.merchant_id)
        if not category:
            continue
            
        customer = store.get_customer(trigger.customer_id) if trigger.customer_id else None

        # Filter 1: Expired triggers
        if trigger.expires_at and parse_iso_datetime(trigger.expires_at) < now_ts:
            continue

        # Filter 2: Suppression key already sent
        supp_key = trigger.suppression_key or f"{trigger.kind}:{merchant.merchant_id}:{customer.customer_id if customer else ''}"
        if suppression_manager.is_suppressed(supp_key):
            continue

        # Filter 3: Cadence guardrail
        if not cadence_manager.can_send(merchant.merchant_id, customer.customer_id if customer else None):
            continue

        # Engagement warmth tiebreaker
        warmth_score = 0
        if merchant.conversation_history:
            last_hist = merchant.conversation_history[-1]
            eng = last_hist.get("engagement", "")
            if eng in ("intent_planning", "intent_action"):
                warmth_score = 2
            elif eng == "merchant_replied":
                warmth_score = 1

        candidates.append({
            "trigger": trigger,
            "merchant": merchant,
            "category": category,
            "customer": customer,
            "suppression_key": supp_key,
            "urgency": trigger.urgency or 1,
            "warmth_score": warmth_score
        })

    # Sort candidates by urgency (desc), warmth_score (desc)
    candidates.sort(key=lambda c: (c["urgency"], c["warmth_score"]), reverse=True)

    # Round-robin diversification by kind
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for c in candidates:
        kind = c["trigger"].kind
        if kind not in by_kind:
            by_kind[kind] = []
        by_kind[kind].append(c)

    selected = []
    kinds = list(by_kind.keys())
    while len(selected) < 20 and any(by_kind[k] for k in kinds):
        for k in kinds:
            if by_kind[k] and len(selected) < 20:
                selected.append(by_kind[k].pop(0))

    from concurrent.futures import ThreadPoolExecutor

    def process_candidate(s):
        trg = s["trigger"]
        mer = s["merchant"]
        cat = s["category"]
        cust = s["customer"]
        supp_key = s["suppression_key"]

        conv_id = f"conv_{mer.merchant_id}_{trg.id}"
        history = suppression_manager.get_history(conv_id)

        composed = compose(category=cat, merchant=mer, trigger=trg, customer=cust, history=history)

        if not composed.body and composed.cta == "none":
            return None

        suppression_manager.record_send(supp_key, composed.body, conv_id)
        cadence_manager.record_send(mer.merchant_id, cust.customer_id if cust else None)

        owner_first = mer.identity.get("owner_first_name", "") if mer.identity else ""

        return {
            "conversation_id": conv_id,
            "merchant_id": mer.merchant_id,
            "customer_id": cust.customer_id if cust else None,
            "send_as": composed.send_as,
            "trigger_id": trg.id,
            "template_name": f"vera_{trg.kind}_v1",
            "template_params": [owner_first] if owner_first else [],
            "body": composed.body,
            "cta": composed.cta,
            "suppression_key": composed.suppression_key,
            "rationale": composed.rationale
        }

    actions = []
    if selected:
        from concurrent.futures import as_completed
        with ThreadPoolExecutor(max_workers=min(len(selected), 10)) as executor:
            futures = [executor.submit(process_candidate, s) for s in selected]
            try:
                for future in as_completed(futures, timeout=10.0):
                    res = future.result()
                    if res:
                        actions.append(res)
            except Exception as e:
                print(f"[Scheduler Warning] schedule_tick timeout safety net hit: {e}")

    return actions
