# Reviveo

**AI-powered revenue recovery for payments at risk.**

Reviveo detects failed and at-risk Razorpay payments, figures out why they failed, decides the safest recovery action, executes it within strict guardrails, and reports the actual revenue recovered, not just the revenue identified as at risk.

Built for the **Razorpay AI Builder Internship 2026** buildathon.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-reviveo.vercel.app-2ea44f)](https://reviveo.vercel.app)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com)
[![Razorpay](https://img.shields.io/badge/Payments-Razorpay-0C2451)](https://razorpay.com)
[![Groq](https://img.shields.io/badge/AI-Groq%20%2F%20Qwen-orange)](https://groq.com)

**Live app:** [reviveo.vercel.app](https://reviveo.vercel.app)
**Repository:** [github.com/Kaushalendra-Marcus/reviveo](https://github.com/Kaushalendra-Marcus/reviveo)

---

## Demo Video

[![Watch the Reviveo demo](https://img.youtube.com/vi/jMqsnPQtysM/maxresdefault.jpg)](https://youtu.be/jMqsnPQtysM)

A five-minute walkthrough of a real Razorpay test-mode payment failure being detected, diagnosed, decided on, and recovered by Reviveo, guardrails included.

---

## The Problem

Revenue loss rarely happens in one clean step. A payment fails, a subscription payment gets stuck, or a customer abandons checkout. Most systems detect the problem and stop there, leaving recovery to fixed rules or manual follow-up.

Reviveo closes that loop end to end:

```text
Failed Payment
    ↓
Detect
    ↓
Analyze Root Cause
    ↓
Decide Best Recovery Action
    ↓
Safety & Guardrails
    ↓
Execute
    ↓
Payment Recovered
    ↓
Measure & Audit
```

---

## How Reviveo Works

### 1. Detect

Reviveo listens to Razorpay webhooks and its own scheduled checks to identify revenue at risk in real time:

```text
payment.failed
checkout abandoned
subscription failure
overdue invoice
```

### 2. Analyze

The system classifies why the payment failed, using the actual Razorpay error code, not a guess:

```text
Card Expired
Insufficient Funds
Payment Timeout
Bank Declined
Checkout Abandoned
Unknown
```

### 3. Decide

A decision engine (backed by an LLM tool-calling agent, currently Groq running Qwen3.8-27B) evaluates:

* Root cause and confidence score
* Customer history
* Payment amount
* Previous recovery attempts

The agent can only select an action from a fixed, allowed list. It never invents a new action or bypasses a limit.

### 4. Guard

Before anything executes, Reviveo checks, in order:

```text
Retry limits
Cooldown periods
Daily spending and contact limits
Confidence thresholds
Approval requirements
```

If a guardrail fails, the action is blocked or routed to a human, not silently skipped.

### 5. Recover

Depending on the situation, Reviveo can:

* Create a real Razorpay recovery payment link
* Schedule a smart retry
* Notify the customer
* Escalate high-risk or low-confidence cases for human approval
* Track native subscription recovery

### 6. Measure

A payment is only counted as recovered when a new, successful Razorpay payment is explicitly linked back to a specific recovery attempt, not just any later payment from the same customer.

```text
Original Failed Event
    ↓
Recovery Decision
    ↓
Recovery Attempt
    ↓
New Razorpay Payment
    ↓
Verified, Attributed Recovery
```

---

## Agent Architecture

```text
                 RAZORPAY EVENT
                       |
                       v
                ┌─────────────┐
                │   DETECT    │
                └──────┬──────┘
                       |
                       v
                ┌─────────────┐
                │   ANALYZE   │
                │ Root Cause  │
                └──────┬──────┘
                       |
                       v
              ┌───────────────────┐
              │  DECISION ENGINE  │
              │                   │
              │ Cause             │
              │ Customer History  │
              │ Amount            │
              │ Confidence        │
              └─────────┬─────────┘
                        |
                        v
                 ┌─────────────┐
                 │ GUARDRAILS  │
                 └──────┬──────┘
                        |
            ┌───────────┼────────────┐
            v           v            v
          RETRY       NOTIFY       ESCALATE
            |           |            |
            └───────────┼────────────┘
                        v
                    EXECUTE
                        |
                        v
                 PAYMENT RESULT
                        |
                        v
                   AUDIT TRAIL
```

---

## Safety First

The AI is never the final authority. Every recommendation passes through a deterministic layer before anything real happens:

```text
Agent recommends an action
    ↓
Policy engine validates it against the allowed action list
    ↓
Guardrails enforce spending, retry, and contact limits
    ↓
High-risk or low-confidence actions require human approval
    ↓
Every step is logged to the audit trail, outcome included
```

### Confidence Policy

| Confidence | Threshold | Action                                                       |
| ---------- | --------- | ------------------------------------------------------------- |
| High       | ≥ 85%     | Auto-execute an allowed, low-risk action                      |
| Medium     | 50 to 85% | Execute permitted low-risk actions, or route for approval     |
| Low        | < 50%     | Always escalate to a human                                    |

---

## Core Features

* AI-assisted recovery decisions with a deterministic safety layer underneath
* Real Razorpay test-mode integration (webhooks, Payment Links)
* Root-cause classification from actual Razorpay error codes
* Bounded agent action selection, never an open-ended tool loop
* Smart retry scheduling with cooldowns
* Human approval workflow with a visible payment link once approved
* Runtime spending, retry, and contact limits
* Idempotent webhook processing
* Recovery attribution (a payment counts as recovered only when linked to a specific attempt)
* Revenue analytics with a live vs. synthetic data toggle
* Full, append-only audit trail
* Synthetic batch simulation mode for demonstrating recovery rate at scale
* Multi-merchant-ready data model

---

## Dashboard

```text
Overview
  Revenue at Risk, Recovered Revenue, Recovery Rate, Trends, Recent Events

Recovery Operations
  Events, Audit Trail, Customers, Strategies, Recoveries

Control
  Guardrails, Reports, Settings and Approvals
```

The Overview page includes a Live / Synthetic toggle, so real Razorpay-verified events can be viewed in isolation from the bulk synthetic dataset used to demonstrate recovery rate at scale.

---

## Tech Stack

**Frontend**
Next.js, TypeScript, Tailwind CSS, shadcn/ui, Recharts, Framer Motion

**Backend**
Python, FastAPI, a lightweight custom data layer over SQLite (Postgres-swappable)

**AI**
Groq (Qwen3.8-27B) for tool-calling agent decisions and reasoning text, with a deterministic rule-based decision engine as the fallback and safety layer

**Payments**
Razorpay Test Mode, Razorpay Webhooks, Payment Links, subscription event handling

---

## Project Structure

```text
reviveo/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   └── lib/
│
├── backend/
│   ├── app/
│   │   ├── api/            REST routes and response schemas
│   │   ├── agent/           bounded agentic tools
│   │   ├── batch/            synthetic batch simulation
│   │   ├── domain/          decision engine, cause analysis, guardrails
│   │   ├── pipeline/        the detect-to-outcome pipeline
│   │   ├── services/        Razorpay, AI, execution, approvals
│   │   ├── webhooks/       Razorpay webhook receiver
│   │   ├── config.py
│   │   ├── db.py
│   │   └── schema.sql
│   └── tests/
│
└── README.md
```

---

## Recovery Attribution

Reviveo does not count any later payment from the same customer as recovered revenue. Each recovery follows an explicit, auditable chain:

```text
Event
    ↓
Decision
    ↓
Recovery Attempt
    ↓
New Razorpay Payment
    ↓
Verified Recovery
```

A payment is only counted as recovered when it:

1. Is explicitly linked to a specific recovery attempt.
2. Successfully resolves that attempt's new payment.
3. Falls within the configured recovery window.
4. Matches the original financial obligation.

---

## Audit Trail

Every detection, decision, guardrail check, execution, and outcome is recorded, in order:

```text
Detection
    ↓
Cause Analysis
    ↓
Decision
    ↓
Guardrail Check
    ↓
Approval or Execution
    ↓
Outcome
```

The goal: every recovery action should be explainable, bounded, and traceable after the fact, not just at the moment it happened.

---

## Getting Started

```bash
git clone https://github.com/Kaushalendra-Marcus/reviveo.git
cd reviveo

# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in the values below
uvicorn app.main:app --reload --port 8000

# Frontend, in a separate terminal
cd ../frontend
npm install
npm run dev
```

### Backend environment variables

```env
RUN_MODE=synthetic          # synthetic or live
API_KEY=
DATABASE_URL=reviveo.db
DEFAULT_MERCHANT_ID=codecraft

RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

GROQ_API_KEY=
AI_MODEL_FAST=qwen/qwen3.8-27b
AI_MODEL_SUMMARY=qwen/qwen3.8-27b

FRONTEND_ORIGIN=http://localhost:3000
```

The app runs fully in synthetic mode with none of the Razorpay or Groq keys set, useful for exploring the dashboard and running the test suite without any external credentials.

**Never commit real secrets to Git.**

### Frontend environment variable

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Why Reviveo?

Most systems stop at "a payment failed."

Reviveo asks why it failed, what the safest recovery action is, and whether that action actually recovered the revenue, then proves it with an audit trail and a real recovered-revenue number.

---

## License

Built as a submission for the Razorpay AI Builder Internship 2026 buildathon, for demonstration and evaluation purposes.

---

**Reviveo: recover revenue, intelligently.**
