# magicpin AI Challenge — Implementation Spec ("Vera-beater")

**Purpose of this document**: hand this to a coding agent (or follow it yourself) to build a submission that scores well against the published rubric. It translates `challenge-brief.md` + `challenge-testing-brief.md` + `judge_simulator.py` into a concrete build plan, and adds an implementation-only "how to win" layer on top.

Read this alongside the two original briefs — this doc doesn't repeat every schema field, it tells you exactly what to build and in what order.

---

## 0. What actually gets scored (read this before writing code)

Two different scoring paths exist and they are **not identical** — build for both:

1. **`challenge-brief.md` §8 rubric** (the "official" 5 dimensions): Specificity, Category fit, Merchant fit, Trigger relevance, Engagement compulsion. Plus Phase 3 adaptation bonus, Phase 4 replay score, operational penalties.
2. **`judge_simulator.py`'s actual `LLMScorer`** (what you'll test against locally, and structurally what any similar harness will run): Specificity, Category fit, Merchant fit, **Decision quality** (this is where trigger relevance *and* the send/wait/end decision get judged), Engagement compulsion, plus penalties for fabrication (-2) and internal-jargon leakage (-1).

Design the composer and the reply-handler against **both**: every message must (a) cite a verifiable fact from the given contexts, (b) match category voice, (c) be personalized to merchant/customer state, (d) explicitly justify "why now" against the trigger, (e) use a compulsion lever with a single clear CTA, and (f) never leak internal field names (`ctr_below_peer_median`, `suppression_key`, `signals`, etc.) into merchant-facing text.

**Operational reliability is graded too** and is pure downside risk if skipped: healthz uptime, idempotent context handling, sub-30s responses, no malformed JSON, no verbatim repeats. Budget engineering time for this — it's cheap to get right and brutal to lose points on (§10 of testing brief: `-10` for offline, `-2` per malformed response, `-2` per repeat).

---

## 1. Target architecture

```
bot/
├── app.py                     # FastAPI app, 5 endpoints, wiring only
├── store.py                   # In-memory context + conversation store (idempotent, versioned)
├── models.py                  # Pydantic models for all 4 contexts + request/response bodies
├── composer/
│   ├── __init__.py
│   ├── prompts.py              # System prompt + per-trigger-kind prompt variants
│   ├── llm_client.py            # Thin wrapper around one LLM provider (temperature=0)
│   ├── compose.py               # compose(category, merchant, trigger, customer) -> ComposedMessage
│   └── validate.py              # Post-LLM validators (CTA shape, language match, fabrication check, jargon check)
├── engagement/
│   ├── scheduler.py             # /v1/tick logic: pick which triggers to act on this tick, respect caps
│   ├── suppression.py           # dedup by suppression_key, per-conversation repeat detection
│   └── cadence.py                # per-merchant/customer send-frequency guardrails
├── conversation/
│   ├── state.py                  # ConversationState dataclass + persistence
│   ├── classify.py               # auto-reply detector, intent detector, hostility detector, language detector
│   └── respond.py                # /v1/reply logic + conversation_handlers.respond()
├── data/
│   └── (dataset/ mounted here for local testing with judge_simulator.py)
├── bot.py                        # thin re-export: `compose()` for the offline submission.jsonl path
├── conversation_handlers.py      # optional deliverable: respond(state, merchant_message) -> dict
├── generate_submission.py        # script: run compose() over the 30 test pairs -> submission.jsonl
├── README.md                     # 1-page submission doc (template in §9 below)
└── requirements.txt
```

Keep the HTTP layer (`app.py`) thin. All scoring-relevant logic (composer, classifiers, scheduler) should be unit-testable without spinning up FastAPI, because you will iterate on prompts far more than on routes.

**LLM choice**: pick one frontier model, temperature=0 (the brief requires determinism given same inputs), and have a fallback provider for resilience (mirrors production Vera's Azure-OpenAI-primary/DeepSeek-fallback pattern noted in `engagement-design.md` §Open Questions #6). Claude or GPT-4-class models handle the Hindi-English code-mix and clinical-vs-promotional voice distinctions better than smaller models — this is worth the latency/cost given the 30s budget.

---

## 2. Data models (`models.py`)

**Correction after reviewing the real dataset** (`dentists.json`, `gyms.json`, `pharmacies.json`, `restaurants.json`, `salons.json`, `merchants_seed.json`, `customers_seed.json`, `triggers_seed.json`, `generate_dataset.py`): several of these blocks are **not fixed schemas** — they vary field-by-field per category/merchant. Don't model them as strict Pydantic sub-models with named fields; model them as open dicts and read out of them defensively (`.get(...)`) inside the composer instead. This is more accurate to the real data than a rigid schema and makes the fabrication-grounding check simpler (see §4.3).

- `CategoryContext` — `slug`, `display_name`, `voice{tone, register, code_mix, vocab_allowed[], vocab_taboo[], salutation_examples[], tone_examples[]}` (note the real field is `vocab_taboo`, not `taboos`), `offer_catalog[]` (`id, title, value, audience, type`), `peer_stats` (**open dict** — differs per category: dentists have `retention_6mo_pct`, gyms have `monthly_churn_pct`/`trial_to_paid_pct`, salons have `retention_3mo_pct`, restaurants have `retention_30d_pct`, pharmacies have `delivery_share_pct`/`repeat_customer_pct` — don't hardcode field names), `digest[]` (**heterogeneous by `kind`**: `research`/`compliance`/`cde`/`trend`/`tech`/`seasonal`/`supply`/`alert` — common fields are `id, kind, title, source, summary, actionable`; kind-specific extras like `trial_n`, `patient_segment`, `date`, `credits`, `deadline` appear only on some), `patient_content_library[]` (`id, title, channel, length_seconds, body`), `seasonal_beats[]` (`month_range, note`), `trend_signals[]` (`query, delta_yoy, segment_age, skew`), `regulatory_authorities[]`, `professional_journals[]` (present in the real data, absent from the earlier brief-only model — worth citing for compliance-kind triggers).
- `MerchantContext` — `merchant_id`, `category_slug`, `identity{name, city, locality, place_id, verified, languages[]` (ISO-ish codes, e.g. `["en","hi","mr"]`) `, owner_first_name, established_year}` — **`owner_first_name` is real and always populated**, use it for the `Dr. {owner_first_name}` salutation rule. `subscription{status, plan, days_remaining, renewed_at?, days_since_expiry?}` — the optional fields are populated situationally (`renewed_at` for active, `days_since_expiry` for expired, neither for trial). `performance{window_days, views, calls, directions, ctr, leads, delta_7d{...}}` — `delta_7d`'s inner keys (`views_pct`, `calls_pct`, `ctr_pct`) are **not guaranteed all present** (e.g. one seed merchant has only `views_pct`/`calls_pct`) — read defensively. `offers[]` (`id, title, status, started/ended`). `conversation_history[]` (`ts, from, body, engagement` — `engagement` values seen: `merchant_replied`, `merchant_no_reply`, `intent_action`, `intent_question`, `intent_planning`; use this to detect "hot" merchants already mid-conversation). `customer_aggregate` (**open dict**, shape varies wildly by category — dentists: `total_unique_ytd/lapsed_180d_plus/retention_6mo_pct/high_risk_adult_count`; restaurants: `total_unique_ytd/delivery_orders_30d/dine_in_orders_30d`; gyms: `total_active_members/monthly_churn_pct/trial_to_paid_pct`; pharmacies: `total_unique_ytd/repeat_customer_pct/chronic_rx_count`). `signals[]` — **literal enumerable jargon strings**, e.g. `"ctr_below_peer_median"`, `"stale_posts:22d"`, `"renewal_due_soon:12d"`, `"engaged_in_last_48h"` — these are exactly what must never leak into outbound text (see §4.3). `review_themes[]` (`theme, sentiment, occurrences_30d, common_quote?`) — `common_quote` is verbatim customer text; never quote it verbatim outbound, always paraphrase the theme.
- `CustomerContext` — `customer_id`, `merchant_id`, `identity{name, phone_redacted, language_pref, age_band, ...}` — **`language_pref` is free text, not an ISO code**: observed values include `"hi-en mix"`, `"te-en mix"`, `"kn-en mix"`, `"ta-en mix"`, `"english"`, `"hi"`, `"en"`. Parse this with substring/keyword matching, not an exact-match enum — and note it uses a different shape from `merchant.identity.languages` (a list of ISO codes), so write two separate parsers. `relationship{first_visit, last_visit, visits_total, services_received[], lifetime_value, ...}` (category-specific extras appear here too, e.g. `favourite_dish`, `chronic_conditions`, `wedding_date` — open dict). `state` (`new|active|lapsed_soft|lapsed_hard|churned`). `preferences{...}` (open dict — `preferred_slots`, `channel`, `reminder_opt_in`, plus ad hoc keys like `preferred_stylist`, `training_focus`, `delivery_address`). `consent{opted_in_at, scope[]}` — **respect `consent.scope`**: don't compose a `promotional_offers` message to a customer whose scope only lists `recall_reminders`, and treat `opted_in_at: null` / `scope: []` (the walk-in/no-profile case, e.g. `c_015`) as "do not message this customer at all, ever."
- `TriggerContext` — `id`, `scope` (`merchant|customer`), `kind`, `source` (`internal|external`), `merchant_id`, `customer_id?`, `payload{}` (**fully open, kind-specific** — see the real kind list in §4.1; some generated instances carry only `{"placeholder": true, "metric_or_topic": kind}`, see the "thin payload" handling note there), `urgency` (int, higher = more urgent), `suppression_key`, `expires_at` (ISO datetime, sometimes `Z`, sometimes `+05:30` — parse both).

Also model the wire contracts precisely:
- `ContextPushRequest` / `ContextPushResponse` (200 accepted / 409 stale_version / 400 invalid_scope)
- `TickRequest` / `TickResponse` (`actions[]`, cap 20 per tick — enforce this cap defensively even if you never hit it)
- `ReplyRequest` / `ReplyResponse` (`action: send|wait|end`)
- `HealthzResponse`, `MetadataResponse`

Accept unknown/extra fields loosely (`model_config = {"extra": "allow"}`) — confirmed necessary: the real payload/peer_stats/customer_aggregate shapes above already vary field-by-field within the provided dataset itself, before any live "post-submission context injection" adds more.

---

## 3. `store.py` — context store

Requirements straight from the testing brief, all of which are graded (operational penalties):

- Key: `(scope, context_id)`. Value: `{version, payload}`.
- **Idempotent**: re-posting the same `(context_id, version)` → no-op, still return `200 {accepted: true}`.
- **Monotonic versioning**: reject (`409 stale_version`) if incoming `version <= current_version`.
- Never wipe state mid-test. Only wipe on an explicit (optional) `POST /v1/teardown`.
- Provide lookup helpers: `get_category(slug)`, `get_merchant(id)`, `get_customer(id)`, `get_trigger(id)`, and a reverse index `merchant_id -> category_slug` (from `merchant.category_slug`) so the scheduler can join contexts without re-scanning.
- Thread-safety: use a simple lock or single-threaded asyncio event loop discipline — `/v1/tick` and `/v1/context` can be concurrent under the judge's up-to-10-req/s load.

Implement as a plain Python dict behind a small class — no external DB needed for the 60-minute test window. Do add a "wipe on teardown" method for hygiene/privacy (§11 of testing brief: don't persist context after the test ends).

---

## 4. The composer — where the points actually come from

### 4.1 Prompt architecture

Use **one shared system prompt** (category voice + universal constraints) plus **per-`kind` user-prompt templates** (per `engagement-design.md`: "different `kind` values may use different prompt variants ... dispatches by kind"). Concretely:

```python
# composer/prompts.py

SYSTEM_PROMPT = """You are composing ONE outbound WhatsApp message on behalf of Vera,
magicpin's merchant-AI assistant (or, if send_as=merchant_on_behalf, on behalf of the
merchant themselves, to their own customer).

You will be given four context blocks: CATEGORY, MERCHANT, TRIGGER, and optionally CUSTOMER.
Follow these rules exactly:

1. SPECIFICITY: anchor the message on at least one verifiable fact literally present in
   the contexts (a number, date, percentage, headline, or source citation). Never write
   generic claims like "grow your business" or "increase your sales" without a number
   attached. Prefer service+price framing ("Dental Cleaning @ ₹299") over discount framing
   ("20% off") when the offer catalog gives you a service+price option.
2. CATEGORY FIT: match voice.tone and voice.register exactly (read them from the CATEGORY
   block given to you — do not assume a tone from the category name). Use vocab_allowed terms
   where natural. NEVER use any word in vocab_taboo. Address the merchant using one of the
   patterns in voice.salutation_examples (e.g. it may resolve to "Dr. {owner_first_name}" for
   a clinical category, or "Hi {owner_first_name}" for others) — substitute the merchant's
   real owner_first_name or business name as the template indicates; never invent a title
   that isn't implied by salutation_examples.
3. MERCHANT FIT: use the merchant's real name, locality, numbers, offers, and conversation
   history. Check identity.languages: if any Indian-language code (hi, mr, ta, te, kn, etc.)
   appears alongside "en", write natural code-mixed WhatsApp language, not pure formal English
   — default to Hindi-English mixing if you're not confident producing natural mixing for that
   specific regional language. If a CUSTOMER is present, use their name and language_pref
   (free text, e.g. "hi-en mix", "english") and reference their actual relationship/state data.
4. TRIGGER RELEVANCE ("why now"): the message must make it obvious, in the first sentence
   or two, why this arrives right now — tie explicitly to trigger.kind and trigger.payload.
   Do not write a message that could have been sent on any random day.
5. ENGAGEMENT COMPULSION: use at least one of: specificity/verifiability, loss aversion,
   social proof, effort externalization ("I've drafted X"), curiosity, reciprocity, asking
   the merchant a direct question, single binary commitment. End on ONE clear ask.
6. NEVER FABRICATE: only use facts present in the contexts given to you. If you don't have
   a number, date, or name for something, don't invent one. Do not name a competitor, cite a
   paper, or state a statistic that isn't literally in the payload.
7. NEVER leak internal fields to the merchant/customer: never surface raw keys or jargon such
   as "ctr_below_peer_median", "suppression_key", "signals", "lapsed_180d_plus", trigger ids,
   or any snake_case system term. Translate them into natural language.
8. Single primary CTA. Binary (reply 1/2, YES/STOP) for action-oriented triggers; open-ended
   question for pure-information triggers; NO multi-option menus ("reply YES for X, NO for Y").
9. No long preambles, no "I hope you're doing well", no re-introducing yourself after the
   first message in a conversation.
10. Keep it WhatsApp-length: concise, scannable, not a paragraph wall.

Return ONLY valid JSON: {"body": str, "cta": "binary"|"open_ended"|"none",
"send_as": "vera"|"merchant_on_behalf", "rationale": str}
The rationale is READ by a judge — make it accurately describe why THIS message, referencing
the specific trigger and specific merchant/customer facts you used.
"""
```

Per-`kind` templates (append to the user message, don't replace the system prompt). **This table is now built from the real 26 kinds observed across `triggers_seed.json` and `generate_dataset.py`'s `additional_kinds` list** (the earlier version of this table had some invented kind names — `weather_heatwave`, `local_news_event`, `unplanned_slot_open`, `category_research_digest_release` — that don't exist in this dataset; replace it with this one):

| kind | scope | framing hint to inject |
|---|---|---|
| `research_digest` | merchant | source-citation framing (`digest[].source`, e.g. "JIDA Oct 2026 p.14"); name the segment it's relevant to if the digest item specifies one (e.g. `patient_segment: high_risk_adults`) |
| `regulation_change` | merchant | compliance/matter-of-fact framing; cite the regulating body and the deadline (`payload.deadline_iso` / digest `source`) verbatim |
| `cde_opportunity` | merchant | professional-development framing; cite credits, date, fee from the digest item |
| `recall_due` | customer | slot-offering framing; use `payload.available_slots[]` if present, else ask for a preferred time; never invent a slot |
| `trial_followup` / `wedding_package_followup` | customer | next-step framing off `payload.next_session_options[]` / `next_step_window_open`; low-pressure, assumes goodwill from a completed first touch |
| `chronic_refill_due` | customer | practical, non-alarmist reminder; cite `payload.molecule_list` and `stock_runs_out_iso`; offer delivery if `delivery_address_saved` |
| `perf_spike` | merchant | congratulatory + capitalize-on-momentum framing; cite the exact `%` and window from `payload.delta_pct`/`window`; credit the likely driver if `payload.likely_driver` is given |
| `perf_dip` / `seasonal_perf_dip` | merchant | diagnostic, non-alarmist framing; cite the `%` drop; if `payload.is_expected_seasonal` is true, frame as normal/expected (don't alarm), else offer a concrete next step |
| `milestone_reached` | merchant | social-proof / celebratory framing; cite `value_now` vs `milestone_value` |
| `renewal_due` | merchant | direct, value-forward framing (not fear-based); cite `days_remaining` and what stays working with an active plan |
| `winback_eligible` | merchant | re-engagement after subscription lapse; cite `days_since_expiry` and the concrete perf cost since |
| `dormant_with_vera` | merchant | low-friction re-engagement, single easy question, acknowledge the gap without guilt-tripping |
| `festival_upcoming` | merchant | timely/local-relevance framing tied to `payload.festival`/`date`; only fire the specific-category angle (e.g. bridal for salons) |
| `ipl_match_today` | merchant | same-day urgency framing off `payload.match`/`match_time_iso`; only worth sending same-day, respect `is_weeknight` framing from the category digest (weeknight matches outperform Saturdays per the restaurant digest) |
| `category_seasonal` | merchant | shelf/ops-action framing off `payload.trends[]`; practical, not promotional |
| `competitor_opened` | merchant | voyeur-curiosity framing ("want to see who?"); only name the competitor if `payload.competitor_name` is present — never invent one |
| `review_theme_emerged` | merchant | pattern-surfacing framing; **paraphrase** the theme, never quote `common_quote` verbatim |
| `supply_alert` | merchant | urgent, factual, compliance-adjacent framing (highest default urgency in the dataset); cite the molecule/batch and the concrete customer-facing action |
| `gbp_unverified` | merchant | one clear ask (start verification), cite `estimated_uplift_pct` as the "why bother" |
| `active_planning_intent` | merchant | **action-mode, not qualifying-mode** — `payload.merchant_last_message` is the merchant's own words showing they already asked/committed; the reply must deliver a concrete draft/next step, never re-ask a variant of the same question. Reuse the intent-transition rules from §6.2. |
| `curious_ask_due` | merchant | single, easy, non-threatening open question (`payload.ask_template`) — this is the direct-question lever the brief flags as underused |
| `customer_lapsed_soft` / `customer_lapsed_hard` | customer | recall/win-back framing; softer, curiosity-based tone for "soft"; more direct value-forward tone for "hard"; cite `days_since_last_visit` if present |
| `appointment_tomorrow` | customer | plain reminder framing, scope=customer |
| default / unknown kind | either | fall back to a generic "cite what you have + ask one question" template — never crash on an unrecognized kind |

**Thin-payload handling**: two kinds (`customer_lapsed_soft`, `appointment_tomorrow`) never appear in the hand-authored seeds — every instance of them in the expanded dataset is generator-created with a near-empty payload (`{"placeholder": true, "metric_or_topic": "<kind>"}`). The same can happen to any other kind's *generated* (non-seed) instances. When `trigger.payload` has no real fields beyond `placeholder`/`metric_or_topic`, don't force a fabricated "why now" detail — instead pull the specificity from `merchant.performance`, `merchant.customer_aggregate`, `merchant.signals` (translated to plain language), or `category.peer_stats`/`offer_catalog`, and keep the trigger-kind framing generic ("it's been a while since your last visit" rather than inventing a day count that isn't in the payload).

**`DEFAULT_VARIANT` should not be a flat generic fallback.** The 26-kind table above is exhaustive for the dataset you've been given, but don't build `DEFAULT_VARIANT` as a lazy "just ask a question" template — build it to derive a reasonable framing from the trigger's *structural* fields, which exist regardless of `kind`:
- `scope == "customer"` → default framing is personal/relational (reference `customer.relationship`/`state`); `scope == "merchant"` → default framing is operational (reference `merchant.performance`/`signals`).
- `source == "external"` → likely news/research/compliance-flavored; lean on `category.digest`/`trend_signals` for grounding. `source == "internal"` → likely a performance/behavioral signal; lean on `merchant.performance`/`signals`/`customer_aggregate`.
- `urgency` (int) scales tone: higher urgency → more direct/immediate framing; low urgency → softer, more optional framing ("worth a look when you have a minute" vs. "this needs attention now").
This makes an unrecognized kind still produce a reasoned, non-generic message instead of visibly falling back to a template — this matters because, while the graded dataset is fixed and deterministic (see §12), this is a free correctness improvement with no cost, and it's the one place genuinely novel input (if any ever arrives) degrades gracefully instead of visibly.

Dispatch logic: `PROMPT_VARIANTS.get(trigger.kind, DEFAULT_VARIANT)`. Keep this a simple dict lookup so adding a new `kind` is a one-line change (this is explicitly called out in `engagement-design.md` as the desired extensibility property — demonstrate it).

### 4.2 `compose()` contract

```python
# composer/compose.py

def compose(category: CategoryContext, merchant: MerchantContext,
            trigger: TriggerContext, customer: CustomerContext | None = None) -> ComposedMessage:
    """
    1. Build prompt from SYSTEM_PROMPT + PROMPT_VARIANTS[trigger.kind] + serialized contexts.
    2. Call LLM at temperature=0.
    3. Parse JSON. If parse fails, retry once with a stricter "return ONLY JSON" nudge.
    4. Run validate.py checks (see 4.3). If they fail, re-prompt once with the specific
       violation named ("your message used the taboo word 'guaranteed', rewrite without it").
    5. Compute suppression_key: prefer trigger.suppression_key; else derive
       f"{trigger.kind}:{merchant.merchant_id}:{customer.customer_id if customer else ''}".
    6. Return ComposedMessage(body, cta, send_as, suppression_key, rationale).
    """
```

Must be **deterministic** given identical inputs (brief §7.1 requirement) — temperature=0, and don't inject wall-clock time or randomness into the prompt itself (timestamps used for framing should come from the trigger/context payload, not `datetime.now()`).

### 4.3 Post-LLM validation (`composer/validate.py`) — this is your cheapest points

Implement deterministic, non-LLM checks that catch the exact things the rubric penalizes. Re-prompt (max 1 retry) on failure, then fall back to a programmatic patch if the retry still fails, rather than ever sending a broken message:

1. **Taboo check**: body doesn't contain any string in `category.voice.vocab_taboo` (case-insensitive) — note the real field name is `vocab_taboo`, not `taboos`.
2. **Jargon leak check — now a precise, not fuzzy, check**: the real dataset's `merchant.signals[]` are literal enumerable strings (`"ctr_below_peer_median"`, `"stale_posts:22d"`, `"renewal_due_soon:12d"`, `"engaged_in_last_48h"`, etc.) — since these are known verbatim per-request (they came straight from the context you built the prompt from), just check the composed body doesn't contain any of them **as an exact substring**, case-insensitive. This is strictly more reliable than a generic snake_case heuristic. Keep a small supplementary blocklist for structural leaks that aren't in `signals` — raw `trigger.id`/`suppression_key` values, any `trg_`/`m_`/`c_` id prefix, and the literal word `suppression_key`.
3. **Fabrication guard — build this generically, not per-field**: given the open/heterogeneous schemas in §2, don't try to enumerate specific field paths. Instead: recursively walk the full serialized JSON of all four input contexts (category, merchant, trigger, customer) once, collecting every number, percentage, date, and proper-noun-ish token into a reference set (normalize currency symbols/commas/% and parse numbers so `"₹299"`, `"Rs 299"`, and `"299"` all match the same reference value, with small rounding tolerance for percentages). Then extract the same token types from the composed body and confirm each traces back to the reference set. Flag anything that doesn't match for re-prompt. Never quote `review_themes[].common_quote` verbatim regardless of match — always paraphrase it, since it's another customer's literal words.
4. **CTA shape check**: if `cta == "binary"`, body must contain exactly one binary ask, not multiple options (regex for multiple "reply X for / Y for" patterns → reject).
5. **Language match check — two separate parsers, since the two schemas differ**: `merchant.identity.languages` is a list of ISO-ish codes (e.g. `["en","hi","mr"]`); `customer.identity.language_pref` is free text (observed values: `"hi-en mix"`, `"te-en mix"`, `"kn-en mix"`, `"ta-en mix"`, `"english"`, `"hi"`, `"en"`) — match by substring, not exact equality. If either signals Hindi code-mix expected (merchant has `"hi"` in `languages`, or customer `language_pref` contains `"hi"`), verify the body contains at least one of a ~20-word Hindi/Hinglish marker set (`hai`, `aapka`, `kya`, `kar`, `bhi`, `mein`, `nahi`, `acha`, `karo`, `haan`, `chalo`, etc. — not a strict required subset, just "at least one"). **Known limitation to note in the README**: for `te-en mix`/`kn-en mix`/`ta-en mix` customers, don't attempt full Telugu/Kannada/Tamil generation — default to natural conversational English with light Hindi-adjacent warmth, since building full marker lexicons for three more languages is out of scope; call this out explicitly as an honest tradeoff rather than silently under-serving those customers.
6. **Anti-repetition check**: body must not be byte-identical (or >90% similar) to any prior body sent in the same `conversation_id` or to the same `merchant_id` for the same `suppression_key` — check against `conversation_history` in `MerchantContext` and against your own send log. This directly avoids the -2/repeat penalty (§10 of testing brief).
7. **send_as check**: `merchant_on_behalf` only when `customer` is not None; `vera` otherwise. Hard-enforce this in code, don't rely on the LLM to get it right.
8. **Length sanity**: reject/re-prompt if body is empty (this is treated as malformed, -2 penalty) or absurdly long (>800 chars is almost certainly a preamble violation).
9. **Consent scope check** (new): before composing at all, confirm the trigger's implied message type is inside `customer.consent.scope[]` (e.g. don't compose a discount/promo message for a customer whose scope is only `["recall_reminders"]`) and that `customer.consent.opted_in_at` is not null. If `opted_in_at` is null and `scope` is empty (the walk-in/no-profile case, e.g. `c_015` in the seed data), skip composing entirely and don't schedule a send for that customer — surface this as a `wait`/no-action outcome, not a malformed response.

Log every validator failure + retry outcome — you'll want this for debugging against `judge_simulator.py` and for the README's "tradeoffs" section.

---

## 5. `/v1/tick` — scheduler (`engagement/scheduler.py`)

This is where "diversified conversation portfolio" (brief §3, pain point #4) and "restraint is rewarded" (testing brief FAQ) both get judged.

Algorithm per tick:

1. For each `trigger_id` in `available_triggers`, look up the trigger, its merchant (and customer if `scope=customer`), and the merchant's category. Skip silently if any required context is missing (don't error the whole tick).
2. Filter out triggers that are expired (`now > expires_at`).
3. Filter out triggers whose `suppression_key` was already sent (dedup — see `engagement/suppression.py`).
4. Apply a **cadence guardrail**: don't send more than N messages to the same `merchant_id` (or `customer_id`) within a rolling window (e.g. don't fire two sends to Dr. Meera in the same tick, and respect a soft daily cap — this maps to the brief's "engage 3-5×/week" target, not "every tick"). A reasonable default: max 1 send per `(merchant_id or customer_id)` per tick, max ~3 per rolling simulated day.
5. Rank remaining candidates by `urgency` (desc), then diversify by `kind` (don't send five `research_digest`s and zero `recall_due`s if both are available — round-robin across kinds when urgencies tie).
6. Cap total actions at 20 (hard API limit) — but in practice, send fewer, better messages. Empty `actions: []` is a valid, good response when nothing clears the bar. **Don't spam to hit a volume target** — the rubric rewards quality and explicitly penalizes generic/repeated content.
7. For each selected trigger, call `compose()`, then build the `TickResponse.actions[]` entry: `conversation_id` (new, e.g. `conv_{merchant_id}_{trigger_id}_{ts}`), `merchant_id`, `customer_id`, `send_as`, `trigger_id`, `template_name` + `template_params` (see §6 below), `body`, `cta`, `suppression_key`, `rationale`.
8. Record the send in `store` / suppression log immediately (before returning), so a concurrent or subsequent tick can't double-send the same `suppression_key`.
9. Whole handler must return within budget — if you're at risk of exceeding it, return whatever's ready and drop remaining candidates for this tick rather than blocking (testing brief FAQ: "don't try to background-process and return late").

### Template params (first-touch / 24h window)

Track, per `(merchant_id, customer_id)` pair, whether this is the first outbound in the current 24h session window (no inbound reply yet, or last inbound >24h ago). If so:
- Use a `template_name` from a small static registry (e.g. `vera_research_digest_v1`, `vera_recall_due_v1`, `vera_generic_v1`) and populate `template_params` as an ordered list matching that template's `{{1}}/{{2}}/...` slots (name, key fact, CTA fragment).
- If a live 24h session is open (merchant/customer has replied within 24h), free-form `body` is fine and `template_name`/`template_params` can be omitted or left as the last-used template for audit purposes.

This directly implements brief §5 constraint 1 (WhatsApp 24h session window) — build the tracking even though the judge won't actually call Meta; it shows correctness and is explicitly graded in Appendix A/B's "why it scores well".

---

## 6. `/v1/reply` and multi-turn (`conversation/`)

This is where Phase 4 replay points live (up to +30 for top 10) and where `judge_simulator.py`'s `auto_reply`, `intent`, and `hostile` scenarios are scored directly — build defensively against exactly those three scenarios.

### 6.1 `ConversationState` (`conversation/state.py`)

```python
@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: str | None
    turns: list[Turn]              # [{from, body, ts}]
    last_bot_bodies: list[str]     # for anti-repetition
    mode: Literal["pitch", "qualifying", "action", "closing"]
    consecutive_unanswered: int
    detected_language: str
```

Persist keyed by `conversation_id` in the same in-memory store. This state is what `conversation_handlers.respond(state, merchant_message)` (the optional deliverable) operates on too — implement the real logic once in `conversation/respond.py` and have both `/v1/reply` and `conversation_handlers.py::respond()` call it, so you don't maintain two copies.

### 6.2 Classifiers (`conversation/classify.py`)

Build these as fast, mostly-deterministic pre-filters that run **before** calling the LLM. Important architectural point given how this phase gets judged: unlike the tick/compose path (which runs against a fixed, known dataset — see §12), the live conversation phase is scored against **scripted replies whose exact phrasing you haven't seen**. A pure regex/keyword classifier that hard-decides the outcome will hold up fine against `judge_simulator.py`'s own literal test strings, but is brittle to any rewording of the same intent (e.g. "go for it" instead of "let's do it", "pls stop texting" instead of "stop messaging"). So: **treat every classifier below as a fast hint, not a hard gate.** Run it, and if it fires, pass its verdict into the composer's prompt as strong guidance ("the merchant's message pattern-matches as an auto-reply/commitment/hostile message — verify this reading and respond accordingly, but use your own judgment on the actual wording since keyword matches can be wrong"), and let the LLM make the final call on `action` and `body`. This gets you the speed and auditability of heuristics for the cases you tested, plus genuine language understanding for phrasing you didn't anticipate — the worst case if a keyword list is under- or over-broad is a slightly-off LLM judgment call, not a silently wrong hard branch.

**Auto-reply detector** — the brief's hint is explicit: *"same message verbatim 3+ times = auto-reply."* Implement:
```python
def is_auto_reply(state: ConversationState, incoming: str) -> bool:
    # Canned-phrase heuristic (catches it on turn 1, don't wait for 3 repeats)
    canned_markers = ["thank you for contacting", "will respond shortly", "automated",
                      "team will get back", "shukriya", "team tak pahuncha"]
    if any(m in incoming.lower() for m in canned_markers):
        return True
    # Verbatim-repeat heuristic (catches it even without canned markers)
    prior_from_merchant = [t.body for t in state.turns if t.from_role in ("merchant","customer")]
    return prior_from_merchant.count(incoming.strip()) >= 2  # this is the 3rd occurrence
```
This is the one classifier that's safe to hard-gate rather than just hint, since it's structural (verbatim repetition) rather than phrasing-dependent — but still keep the canned-phrase list as a hint layer, since novel canned phrasing ("we'll get back to you soon") could otherwise slip past both the exact-phrase list and the repeat-count check on turn 1. Behavior on detection: **try exactly once** to route past it (Pattern B in the brief — "Vera tried once after detecting auto-reply, then stopped"), then on a second confirmed auto-reply, return `action: "end"` with a polite, positive-sign-off rationale. Don't burn more than 2 turns on this (brief pain point #1: "burns 2-3 turns each time — better detection wins").

**Intent detector** — catch explicit commitment language and route straight to action, skipping further qualification:
```python
COMMIT_PHRASES = ["let's do it", "lets do it", "ok let's", "go ahead", "yes i want",
                   "i want to join", "haan kar do", "chalo shuru karo", "start karo", "proceed"]
```
Treat a match as a strong hint, not the sole signal — also ask the composer LLM directly, as part of its prompt, "does this message express clear agreement/commitment, even if it doesn't match a known phrase?" and OR the two signals together. On either firing: set `state.mode = "action"` and compose a reply that **does something** or **states the concrete next step** (words like "done", "sending", "here's", "confirm") — never re-ask a qualifying question (`judge_simulator.py`'s own check literally scans for "would you/do you/can you tell/what if/how about" as a FAIL signal and "done/sending/draft/here/confirm/proceed/next" as a PASS signal — write your action-mode prompt to naturally produce the latter vocabulary, and hard-block the qualifying phrases with a post-LLM regex check identical in spirit to §4.3's other validators, since this one's cheap and precise to enforce mechanically regardless of phrasing).

**Hostility detector** — simple keyword/sentiment check ("stop messaging", "spam", "useless", abusive language) as a hint, same pattern: also let the composer LLM read the raw message and independently assess tone, since sentiment is exactly the kind of judgment a keyword list handles worst. On detection (by either signal): respond with a short, non-defensive apology/opt-down (`action: "send"` with body containing "sorry"/apolog*/"won't" — matches the simulator's own check) or `action: "end"` if the message is a clear stop-request. Never argue back. If the same message also contains an unrelated question (Phase 4 scenario 3: "can you also help me file my GST?"), acknowledge you can't help with that specific thing while staying polite, and redirect to what you can do — **don't ignore the off-topic question, and don't get derailed into trying to answer it**.

**Language detector** — cheap heuristic (Devanagari char range or common Hindi-in-Latin tokens) to decide whether to keep responding in Hinglish or pure English, and to detect a mid-conversation language switch (brief §12 open challenge #4). This one is genuinely fine as a hard signal (it drives style, not the send/wait/end decision, so a wrong call here just means a slightly-off tone rather than a wrong action).

### 6.3 `/v1/reply` handler logic

```
1. Look up / create ConversationState for conversation_id.
2. Append incoming turn.
3. If is_auto_reply(state, message):
     if this is the first detection -> compose ONE more nudge that doesn't ask the merchant
        to repeat themselves (route around the auto-reply, e.g. "I'll go ahead and check X myself")
        -> action: send
     else -> action: end, rationale: "detected repeated auto-reply, exiting gracefully"
4. elif is_hostile(message):
     -> if explicit stop/spam request: action: end
        else: action: send, short apology + optional graceful redirect
5. elif is_commitment(message):
     -> state.mode = "action"; compose an action-mode reply (do the thing / state the concrete
        next step); action: send
6. elif message signals "not interested" / "no" / "not now":
     -> action: end (graceful exit) OR action: wait with a longer wait_seconds if it's soft
        deferral ("maybe later") rather than a hard no
7. elif state.consecutive_unanswered >= 3 (no inbound in N ticks):
     -> action: end (brief §12 challenge #5: know when to stop after 3 unanswered nudges)
8. else:
     -> normal composed reply via compose()-equivalent for mid-conversation turns (reuse the
        composer with a "reply" trigger-kind variant that has access to full turn history)
9. Before returning: run the same anti-repetition validator against state.last_bot_bodies.
10. Persist state, return within 30s.
```

Wrap the whole handler in a timeout guard — if LLM composition is at risk of exceeding budget, fall back to a short templated acknowledgment (`action: "send"`, body="Got it — give me a moment and I'll follow up.") rather than timing out and getting scored `bot_silent`.

---

## 7. Suppression & cadence (`engagement/suppression.py`, `engagement/cadence.py`)

- `suppression.py`: a set of `suppression_key`s already sent (persisted for the whole test, not per-tick). Also maintain a per-`conversation_id` list of prior bodies for the verbatim-repeat check used by both the scheduler and the reply handler.
- `cadence.py`: a rolling counter per `merchant_id`/`customer_id` of sends in the last simulated day, with a soft cap (configurable, default ~1-2/day in test conditions, reflecting the brief's real target of 3-5/**week**, scaled to a 60-minute simulated test window — don't literally try to hit 3-5 sends in 60 minutes if that means spamming). Bias toward **fewer, better** messages; the rubric has no reward for raw volume and explicit penalties for spam-like behavior.

---

## 8. Adaptive context injection (Phase 3) — don't leave this on the table

Phase 3 bonus is up to **+5 per dimension** for incorporating new context mid-test, so make it structurally impossible to ignore:

- Whenever `/v1/context` receives a higher version for a `category` or `merchant` the bot has already used in a live conversation, **do not treat old composed messages as still valid** — the next `compose()` call for that entity must re-read the store fresh (never cache a serialized context blob longer than one call).
- When a new `digest` item lands on a category (new version), and a `research_digest`-kind trigger exists or arrives for that category, prefer the **newest** digest item in the prompt, not a stale cached one.
- When a merchant's `performance` snapshot updates (spike/dip), and a `perf_spike`/`perf_dip` trigger is active, use the **new** numbers — this is graded explicitly ("Bots that incorporate the new context ... score higher").
- When a new `customer` context + `recall_due` trigger arrive together (the brief's specific Phase-3 test case for 5 merchants), make sure your `/v1/tick` and `/v1/context` code paths don't require the customer to have existed at warmup — treat any newly-pushed context as immediately usable.
- Never let the fabrication guard (§4.3.3) get confused by legitimately-new data — it should check against the **current** store state, not a snapshot taken at composer-build time.

---

## 9. Deliverables checklist (map 1:1 to brief §7)

- [ ] `bot.py` — HTTP server (`app.py` content re-exported/imported here per the skeleton's naming) exposing all 5 endpoints, importable `compose()` for offline use.
- [ ] `generate_submission.py` — loads the 30 canonical test pairs (or all provided merchant/trigger pairs if the specific 30 aren't identifiable ahead of time — check the dataset for anything resembling a "submission test set" manifest; if absent, run all merchant×trigger combos that share a `merchant_id` reference and pick the ones matching known test IDs `T01..T30`), calls `compose()` for each, writes `submission.jsonl` with exactly the keys: `test_id, body, cta, send_as, suppression_key, rationale`.
- [ ] `README.md` — 1 page. Structure:
  1. **Approach** (2-3 sentences): shared composer, per-kind prompt dispatch, deterministic validation layer, classifier-first reply handling.
  2. **Tradeoffs**: e.g. "prioritized reliability/determinism over creative variance (temp=0)"; "cadence-capped sends over volume"; "heuristic language/auto-reply detection over ML for latency and auditability".
  3. **What additional context would have helped most**: be honest and specific — e.g. a real offer source-of-truth (per `engagement-design.md`'s open question #5), richer customer visit-history, or ground-truth on what counts as the canonical 30-pair test set.
- [ ] `conversation_handlers.py` (optional but do it — tiebreaker): `respond(state, merchant_message) -> dict` calling the same logic as `/v1/reply`.
- [ ] `requirements.txt` (fastapi, uvicorn, pydantic, your LLM SDK, python-dotenv).
- [ ] Deploy to a public HTTPS URL (Render/Fly/Railway all work well for a FastAPI app with zero infra ceremony — pick whichever the team already has an account on).

---

## 10. Testing plan

1. Run `judge_simulator.py` locally against `bot.py` early and often:
   ```bash
   export BOT_URL=http://localhost:8080
   python judge_simulator.py            # TEST_SCENARIO = "all" by default in the file
   ```
   It runs `warmup`, `auto_reply_hell`, `intent_transition`, `hostile` — all four map directly to graded behaviors above. Also run `full_evaluation` once you have real dataset files to get real 0-50 scores per composed message and iterate on the prompt until averages are consistently 7+/10 per dimension.
2. Add a small pytest suite around `composer/validate.py` and `conversation/classify.py` directly (no HTTP needed) — these are pure functions and the cheapest place to catch regressions.
3. Manually inspect a sample of `submission.jsonl` against brief Appendix A/B's "good message" examples before submitting — read them out loud, in the merchant's voice, and check: would a real Dr. Meera or Studio11 salon owner actually reply to this?
4. Load-test `/v1/tick` and `/v1/reply` for latency under the 30s budget with realistic context sizes (50 merchants, 200 customers) before submission — a slow LLM call chain (compose → validate → re-prompt) can blow the budget; measure and add a hard per-call timeout with the templated-fallback safety net from §6.3.

---

## 11. Build order (recommended sequence for the coding agent)

1. `models.py` + `store.py` + `app.py` skeleton with all 5 endpoints wired to the store (no LLM yet) — get `judge_simulator.py`'s `warmup` scenario green first.
2. `composer/prompts.py` + `llm_client.py` + `compose.py` with just the default prompt variant — get real (if generic) messages flowing through `/v1/tick`.
3. `composer/validate.py` — add the deterministic checks; re-run `full_evaluation` and watch scores jump.
4. Per-`kind` prompt variants (§4.1 table) — biggest lever on Category fit + Trigger relevance.
5. `conversation/classify.py` (as hints, feeding both a rule-based path and the composer's LLM judgment — see §6.2) + `respond.py` — get `auto_reply_hell`, `intent_transition`, `hostile` scenarios passing.
6. `engagement/scheduler.py` cadence + diversification + suppression — get `full_evaluation`'s tick behavior sensible (not spammy, not silent).
7. Adaptation hardening (§8) — verify with a manual test: push v1 context, get a composed message, push v2 with different perf numbers, confirm the next message reflects v2 not v1.
8. `conversation_handlers.py`, `generate_submission.py`, `README.md`, deploy, final `judge_simulator.py full_evaluation` pass, submit.

---

## 12. Dataset-grounded corrections (post-review of the real files)

Everything above already has the corrections folded in inline; this section is the delta summary plus two operational build steps the coding agent needs that weren't derivable from the briefs alone.

### Build the local test fixtures deterministically
`generate_dataset.py` expects a `categories/` subfolder next to the seed files. Before running it:
```
mkdir -p categories
mv dentists.json gyms.json pharmacies.json restaurants.json salons.json categories/
python generate_dataset.py --seed-dir . --out ./expanded
```
This is **seeded (`SEED = 20260426`)**, so it produces the exact same 50 merchants / 200 customers / 100 triggers / `test_pairs.json` every time, for anyone who runs it — meaning the "30 canonical test pairs" referenced earlier in this doc (§9) are **not ambiguous**: they're whatever `expanded/test_pairs.json` contains after running this script. Point `generate_submission.py` at that file directly instead of guessing at a manifest. Mount `expanded/` as the `data/` fixture directory for local `judge_simulator.py` runs.

### `active_planning_intent` is a compose-time concern, not just a reply-time one
The dataset's `active_planning_intent` trigger kind (e.g. `trg_013_corporate_thali_planning`, `trg_016_kids_yoga_program_drafting`) carries the merchant's actual last message verbatim in `payload.merchant_last_message` ("Yes good idea, what would it look like", "Hi I want to add a kids yoga program — what should it look like?"). This means the intent-transition logic in §6.2 (never re-ask a qualifying question after commitment, deliver a concrete draft/next step instead) needs to be reachable from **both** `/v1/tick`'s `compose()` path and `/v1/reply`'s conversation path — factor it as a shared "action-mode" prompt fragment used by both, keyed off `trigger.kind == "active_planning_intent"` in the tick path and off the classifier in the reply path.

### Use `conversation_history[].engagement` as a scheduler signal
Each entry's `engagement` field (`merchant_replied`, `merchant_no_reply`, `intent_action`, `intent_question`, `intent_planning`) is a ready-made proxy for "how warm is this merchant right now." Feed it into the scheduler's ranking (§5 step 5) as a tiebreaker alongside `urgency` — a merchant whose most recent `conversation_history` entry is `intent_planning`/`intent_action` should be prioritized for an `active_planning_intent`-kind trigger over a cold merchant with the same nominal urgency score.

### Cite `regulatory_authorities[]` / `professional_journals[]` for compliance/research framing
These two category-level fields (e.g. dentists: `["Dental Council of India (DCI)", "Indian Dental Association (IDA)"]` / `["JIDA", "Indian Journal of Dental Research", "Dental Tribune India"]`) exist in the real data but weren't in the earlier schema. Use them to validate/reinforce a `regulation_change` or `research_digest` message's source citation reads as authentically in-category rather than generic ("per DCI's latest circular" vs. a vague "per new regulations").

### Fast-win update: social-proof grounding is easier than assumed
§14's peer_stats social-proof point (below) undersold how directly usable this is — e.g. dentists' `peer_stats.avg_ctr: 0.030` vs. a specific merchant's `performance.ctr: 0.021` is a ready-made, fully-grounded "your CTR is X vs. peer average Y" specificity+social-proof combo move requiring zero fabrication, available for essentially every merchant in the dataset. Bake this comparison into the default template's specificity guidance, not just as an occasional embellishment.

---

## 13. Generalization & robustness — what's actually at risk

Worth being precise about this rather than vague: `generate_dataset.py` states outright that it's **"Deterministic — fixed seed, same output for everyone"**. That means the primary scoring path (`/v1/tick` composing messages against `test_pairs.json`, and Phase 3's version-bump mutations to those same records) is graded against a known, fixed universe — the 5 categories and 26 trigger kinds in this dataset, not an unknown 6th category or 27th kind. Most of the pipeline above is already schema-driven (reads `voice.salutation_examples`, `vocab_taboo`, `signals[]`, etc. at runtime rather than hardcoding per-category behavior), so it holds up on that fixed universe without further work.

The one part of grading that is **not** drawn from this fixed dataset is the live conversation phase — scripted merchant replies whose exact phrasing isn't something you can pre-verify against a seed file. That's why §6.2 above treats every classifier as a hint that both a keyword match and an LLM judgment feed into, rather than a hard gate on keyword lists alone — that's the one place genuinely novel phrasing can arrive, and it's been hardened accordingly.

Two remaining cheap protections worth building, for defense-in-depth beyond what's already specified:

1. **Field-mismatch logging, not just silent tolerance.** `extra="allow"` plus defensive `.get()` reads (already specified throughout) stop a shape mismatch from crashing the bot, but by design they do it silently — if the live grading harness's `/v1/context` payloads use a slightly different key name than what's in these seed files, you'd get a quietly weaker message rather than a visible error. Add a debug log line in the composer whenever an expected top-level key (`voice`, `peer_stats`, `identity`, `payload`, etc.) is absent from a context that should have it, so this is visible during your own testing window rather than discovered only in final scores.
2. **Don't let `DEFAULT_VARIANT` visibly degrade.** Covered in §4.1 above — worth restating here because it's the direct mitigation for "novel kind arrives": derive framing from `scope`/`source`/`urgency` rather than falling back to a flat generic template.

Net: for the graded-content dimensions (Specificity, Category fit, Merchant fit, Decision quality, Engagement compulsion), the pipeline should hold up well because the system prompt encodes a reasoning process off whatever's literally in the given contexts, not hardcoded per-category content. The genuine residual risk was concentrated in the live-conversation classifiers, and that's now been addressed structurally rather than left as a caveat.

---

## 14. Fast wins that are easy to underweight

- **Service+price over discount framing** everywhere the offer catalog allows it — this is called out twice in the brief as a differentiator vs. production Vera.
- **Asking the merchant a direct question** and **social proof** — brief §10 explicitly says these are production Vera's "biggest miss" and would "unlock a lot of engagement." Make sure your prompt variants actually use `peer_stats` for social-proof framing ("3 dentists in your locality did X this month" style, but only when the payload actually supports the specific claim — don't fabricate the "3 dentists").
- **Rationale quality** — the testing brief FAQ confirms the judge reads `rationale` and "high-quality rationales help the judge interpret edge cases generously." Don't treat it as a throwaway field; make it a precise, specific sentence citing the exact trigger/merchant facts used.
- **Restraint** — an empty `actions: []` when nothing clears the bar is explicitly rewarded. Don't force a send every tick just to look active.
