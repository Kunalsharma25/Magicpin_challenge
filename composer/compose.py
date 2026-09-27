import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any
from models import CategoryContext, MerchantContext, CustomerContext, TriggerContext
from composer.prompts import SYSTEM_PROMPT, PROMPT_VARIANTS, get_default_variant
from composer.llm_client import llm_client

@dataclass
class ComposedMessage:
    body: str
    cta: str
    send_as: str
    suppression_key: str
    rationale: str

def serialize_context(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if v is not None}
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if v is not None}
    return {}

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None

from composer.validate import validate_message, check_consent_scope

def compose(
    category: CategoryContext,
    merchant: MerchantContext,
    trigger: TriggerContext,
    customer: Optional[CustomerContext] = None,
    history: Optional[list] = None
) -> ComposedMessage:

    cat_dict = serialize_context(category)
    mer_dict = serialize_context(merchant)
    trg_dict = serialize_context(trigger)
    cus_dict = serialize_context(customer) if customer else None

    # Check consent scope before composition per §4.3 Rule 9
    if cus_dict:
        consent_ok, consent_err = check_consent_scope(cus_dict, trigger.kind)
        if not consent_ok:
            # Skip composing entirely for customer without consent
            supp_key = trigger.suppression_key or f"{trigger.kind}:{merchant.merchant_id}:{customer.customer_id}"
            return ComposedMessage(
                body="",
                cta="none",
                send_as="merchant_on_behalf",
                suppression_key=supp_key,
                rationale=f"Skipped composition: {consent_err}"
            )

    # Derive variant or fallback to default
    variant = PROMPT_VARIANTS.get(trigger.kind)
    if not variant:
        variant = get_default_variant(trg_dict)

    user_prompt = f"""=== CONTEXT BLOCKS ===

CATEGORY CONTEXT:
{json.dumps(cat_dict, indent=2, ensure_ascii=False)}

MERCHANT CONTEXT:
{json.dumps(mer_dict, indent=2, ensure_ascii=False)}

TRIGGER CONTEXT:
{json.dumps(trg_dict, indent=2, ensure_ascii=False)}

CUSTOMER CONTEXT:
{json.dumps(cus_dict, indent=2, ensure_ascii=False) if cus_dict else "None (Merchant facing)"}

=== SPECIFIC TRIGGER GUIDANCE ===
{variant}

Compose the outbound WhatsApp message following the rules in the system prompt. Return ONLY valid JSON:
{{"body": "...", "cta": "binary"|"open_ended"|"none", "send_as": "vera"|"merchant_on_behalf", "rationale": "..."}}
"""

    raw_response = llm_client.complete(SYSTEM_PROMPT, user_prompt, temperature=0.0)
    parsed = extract_json(raw_response)

    # Retry once if JSON parse failed
    if not parsed:
        retry_prompt = user_prompt + "\n\nCRITICAL: Your previous response was not valid JSON. Return ONLY raw JSON starting with '{' and ending with '}'."
        raw_response = llm_client.complete(SYSTEM_PROMPT, retry_prompt, temperature=0.0)
        parsed = extract_json(raw_response)

    if not parsed:
        parsed = {
            "body": f"Hi {mer_dict.get('identity', {}).get('owner_first_name', 'there')}, notice activity regarding {trigger.kind}. Let us know if you'd like to update your setup.",
            "cta": "binary",
            "send_as": "vera" if not customer else "merchant_on_behalf",
            "rationale": f"Fallback composition for trigger {trigger.id}."
        }

    body = parsed.get("body", "")
    cta = parsed.get("cta", "binary")
    send_as = "merchant_on_behalf" if customer is not None else "vera"
    rationale = parsed.get("rationale", f"Composed message for trigger {trigger.kind}.")

    # Run deterministic validators
    is_valid, violations = validate_message(
        body=body,
        cta=cta,
        send_as=send_as,
        category_dict=cat_dict,
        merchant_dict=mer_dict,
        trigger_dict=trg_dict,
        customer_dict=cus_dict,
        history=history
    )

    # Re-prompt once if validation failed
    if not is_valid and violations:
        violation_str = "\n".join(f"- {v}" for v in violations)
        reprompt = user_prompt + f"\n\nYOUR PREVIOUS MESSAGE WAS REJECTED DUE TO THE FOLLOWING VIOLATIONS:\n{violation_str}\n\nPlease rewrite the message addressing all violations. Return ONLY valid JSON."
        retry_raw = llm_client.complete(SYSTEM_PROMPT, reprompt, temperature=0.0)
        retry_parsed = extract_json(retry_raw)
        if retry_parsed:
            retry_body = retry_parsed.get("body", "")
            # Verify retry
            retry_ok, retry_violations = validate_message(
                body=retry_body,
                cta=retry_parsed.get("cta", cta),
                send_as=send_as,
                category_dict=cat_dict,
                merchant_dict=mer_dict,
                trigger_dict=trg_dict,
                customer_dict=cus_dict,
                history=history
            )
            if retry_ok or len(retry_violations) < len(violations):
                body = retry_body
                cta = retry_parsed.get("cta", cta)
                rationale = retry_parsed.get("rationale", rationale)

    # Derive suppression_key
    supp_key = getattr(trigger, "suppression_key", None)
    if not supp_key and isinstance(trg_dict, dict):
        supp_key = trg_dict.get("suppression_key")
    if not supp_key:
        cust_id = customer.customer_id if customer else ""
        supp_key = f"{trigger.kind}:{merchant.merchant_id}:{cust_id}"

    return ComposedMessage(
        body=body,
        cta=cta,
        send_as=send_as,
        suppression_key=supp_key,
        rationale=rationale
    )
