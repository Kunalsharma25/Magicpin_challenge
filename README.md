# magicpin AI Challenge — Merchant Engagement Bot (`Vera-Beater`)

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![OpenAI GPT-4o-mini](https://img.shields.io/badge/LLM-GPT--4o--mini-green.svg)](https://openai.com/)
[![Render Deployed](https://img.shields.io/badge/Render-Deployed-success.svg)](https://magicpin-challenge-yxdv.onrender.com)
[![Score](https://img.shields.io/badge/Judge%20Score-80%25%20(40%2F50)-brightgreen.svg)]()

> A state-of-the-art FastAPI service designed to compose hyper-personalized, grounded WhatsApp engagement messages for merchants and customers across 5 vertical categories (*Dentists, Salons, Restaurants, Gyms, Pharmacies*).

---

## 🎯 Live API Endpoint & Deployment

- **Production Cloud Host**: `https://magicpin-challenge-yxdv.onrender.com`
- **Health Check**: `GET https://magicpin-challenge-yxdv.onrender.com/v1/healthz`
- **Metadata**: `GET https://magicpin-challenge-yxdv.onrender.com/v1/metadata`
- **Architecture**: Modular FastAPI + OpenAI GPT-4o-mini (Primary) with Groq & Gemini fallbacks.

---

## 🏗 System Architecture & Key Modules

```
D:\Magicpic_challenge\
├── app.py                   # FastAPI application routing & HTTP handlers
├── bot.py                   # Entrypoint with dynamic $PORT binding for Render deployment
├── models.py                # Pydantic schemas with extra="allow" for open context payloads
├── store.py                 # Monotonic versioned context store with 409 conflict detection
├── composer/
│   ├── llm_client.py        # Multi-provider LLM Client (OpenAI -> Groq -> Gemini -> Fallback)
│   ├── prompts.py           # Universal system prompt + 26 trigger-kind prompt variants
│   ├── validate.py          # 9 deterministic post-LLM validation checks
│   └── compose.py           # Context serializer, LLM prompt assembly & retry logic
├── engagement/
│   ├── suppression.py       # De-duplication & suppression key generator
│   ├── cadence.py           # 30-day send caps & 7-day category suppression rules
│   └── scheduler.py         # Priority queue, tie-breaker ranking & 10s tick timeout guard
├── conversation/
│   ├── state.py             # Conversation turn history & state machine
│   ├── classify.py          # Auto-reply detector, hostile opt-out & commitment intent classifiers
│   └── respond.py           # Multi-turn conversation handler
├── judge_simulator.py       # Native rubric evaluator & scenario benchmark runner
└── generate_submission.py   # Canonical generator for 30 benchmark pairs -> submission.jsonl
```

---

## 🔥 Key Technical Highlights

1. **Zero Hallucination Grounding**: Fact-anchored generation adhering strictly to numbers, dates, and compliance citations present in payload context blocks.
2. **Deterministic 9-Point Validator**: Built-in guardrails checking taboo vocabulary, signal/jargon leaks, single binary CTA shape, Hinglish markers, and consent boundaries.
3. **Multi-Turn Intelligence**:
   - **Auto-Reply Trap**: Detects repeated canned messages and terminates conversation after 2 turns to prevent infinite loops.
   - **Intent Transition**: Automatically switches from qualification mode to action mode (immediate action verbs, zero qualifying words) upon merchant commitment.
   - **Hostile Opt-Out**: Graceful non-defensive exit (`action: "end"`) when hostility or opt-out is detected.
4. **Latency & Timeout Protection**: Parallel `ThreadPoolExecutor` tick scheduler with a 10s safety net to guarantee `/v1/tick` SLAs under network stress.

---

## 🛠 Local Setup & Running Tests

### 1. Installation
```powershell
pip install -r requirements.txt
```

### 2. Environment Setup
Create a `.env` file in the project root:
```env
OPENAI_API_KEY=sk-proj-...
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=...
```

### 3. Start the Server Locally
```powershell
python bot.py
```
*(Server runs on `http://localhost:8080`)*

### 4. Run the LLM Judge Simulator Benchmark
```powershell
# Run short phase 2 evaluation
python judge_simulator.py

# Run multi-turn scenarios against live endpoint
python judge_simulator.py auto_reply_hell
python judge_simulator.py intent_transition
python judge_simulator.py hostile
```

### 5. Generate Submission JSONL
```powershell
python generate_submission.py
```
Generates 30 real benchmark records in `submission.jsonl`.

---

## 📊 Benchmark Results

| Scenario | Score | Rating | Highlights |
| :--- | :---: | :---: | :--- |
| **Phase 2 Short Benchmark** | **40 / 50 (80%)** | **EXCELLENT** | Perfect Category Fit (9/10), High Specificity (8/10) |
| **Auto-Reply Hell** | **PASS** | **SUCCESS** | Correctly terminates loop on turn 2 |
| **Intent Transition** | **PASS** | **SUCCESS** | Switches to action verbs upon commitment |
| **Hostile Handling** | **PASS** | **SUCCESS** | Non-defensive opt-out handling |

---

## 📄 License
Internal Submission for **magicpin AI Challenge**. All Rights Reserved.
