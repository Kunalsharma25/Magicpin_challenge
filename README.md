# magicpin AI Challenge Submission — Vera-Beater Bot

## 1. Approach
Our submission implements a high-reliability, multi-tiered architecture that strictly separates context storage, prompt composition, post-LLM deterministic validation, engagement scheduling, and multi-turn conversation handling:

- **Context Storage (`store.py`)**: Monotonic, idempotent in-memory store supporting versioned context updates (`/v1/context`) with reverse category lookups.
- **Composer Pipeline (`composer/`)**: Built around a unified system prompt enforcing 10 rubric constraints (Specificity, Category Voice, Merchant Fit, Trigger Relevance, Engagement Compulsion, Zero Fabrication, Zero Jargon Leakage, Single CTA, WhatsApp formatting, JSON output). Dispatches to 26 trigger-kind prompt variants with a structural fallback mechanism.
- **Deterministic Validation Layer (`composer/validate.py`)**: Post-LLM gate executing 9 non-LLM checks (taboo words, signal/jargon leaks, recursive context token grounding, binary CTA shape, language marker matching, anti-repetition similarity, consent scope, and length sanity) with automated single-turn re-prompting.
- **Engagement Scheduler (`engagement/`)**: Evaluates trigger urgency, cadence caps (1 send/entity/tick), and conversation history warmth to round-robin diversify outbound tick actions (`/v1/tick`).
- **Multi-Turn Reply Engine (`conversation/`)**: Pre-filters canned auto-replies, hostility, and explicit merchant commitment, transitioning immediately to action-mode outputs without re-qualifying questions (`/v1/reply` and `conversation_handlers.py`).

## 2. Tradeoffs
- **Determinism over Creative Variance (`temperature=0`)**: Enforced deterministic LLM sampling to guarantee consistent, repeatable outputs across identical context inputs.
- **Quality & Cadence over Raw Volume**: Capped tick send frequency to prioritize high-compulsion messages over volume, avoiding spam penalties.
- **Heuristic Pre-Filtering for Multi-Turn Intent**: Combined regex and phrase-marker heuristics with LLM judgment hints to maximize evaluation speed within the 30s response budget.
- **Regional Language Scope**: Supported Hindi-English code-mixing directly while maintaining polite conversational English for other regional preferences to avoid ungrounded vocabulary generation.

## 3. What Additional Context Would Have Helped Most
- **Canonical Offer Source-of-Truth**: Real-time offer availability and pricing parameters to expand service+price framing beyond static seed catalogs.
- **Historical Customer Interaction Logs**: Richer longitudinal visit and transaction history for customer-facing triggers to generate even deeper factual grounding.
- **Unified Standardized Manifests**: Explicit test pair manifests across all dataset versions to simplify offline submission generation.
