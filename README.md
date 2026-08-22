# Reviveo

### AI-powered revenue recovery for payments at risk.

> **Detect. Decide. Recover. Measure.**

Reviveo is an AI-powered revenue recovery agent that helps merchants detect failed or at-risk payments, identify the underlying cause, choose a safe recovery strategy, execute it within strict guardrails, and measure the revenue actually recovered.

---

## The Problem

Revenue loss rarely happens in one clean step.

A payment fails, a subscription payment gets stuck, or a customer abandons checkout. Traditional systems often detect the problem but leave recovery to fixed rules or manual follow-ups.

Reviveo closes that loop:

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

Reviveo receives payment and recovery events through Razorpay webhooks and identifies revenue at risk.

```text
payment.failed
checkout abandoned
subscription failure
```

### 2. Analyze

The system determines why the payment failed using payment signals and failure data.

```text
Card Expired
Insufficient Funds
Payment Timeout
Bank Declined
Checkout Abandoned
Unknown
```

### 3. Decide

An AI-powered decision engine evaluates:

* Root cause
* Confidence level
* Customer history
* Payment amount
* Previous recovery attempts

The agent can only select actions explicitly allowed by the deterministic policy engine.

### 4. Guard

Before executing any action, Reviveo checks:

```text
Retry limits
↓
Cooldown periods
↓
Daily limits
↓
Confidence thresholds
↓
Approval requirements
```

The AI cannot bypass these guardrails.

### 5. Recover

Depending on the situation, Reviveo can:

* Create a recovery payment link
* Schedule a smart retry
* Notify the customer
* Escalate high-risk cases for approval
* Monitor native subscription recovery

### 6. Measure

A payment is counted as **recovered only when a new successful payment is explicitly linked to a recovery attempt**.

```text
Original Failed Event
        ↓
Recovery Decision
        ↓
Recovery Attempt
        ↓
New Payment
        ↓
Verified Successful Payment
        ↓
Recovered Revenue
```

---

## Agent Architecture

```text
                 RAZORPAY EVENT
                       │
                       ▼
                ┌─────────────┐
                │   DETECT    │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │   ANALYZE   │
                │ Root Cause  │
                └──────┬──────┘
                       │
                       ▼
              ┌───────────────────┐
              │ AI DECISION ENGINE│
              │                   │
              │ Cause             │
              │ Customer History  │
              │ Amount            │
              │ Confidence        │
              └─────────┬─────────┘
                        │
                        ▼
                 ┌─────────────┐
                 │ GUARDRAILS  │
                 └──────┬──────┘
                        │
            ┌───────────┼────────────┐
            ▼           ▼            ▼
          RETRY       NOTIFY       ESCALATE
            │           │            │
            └───────────┼────────────┘
                        ▼
                    EXECUTE
                        │
                        ▼
                 PAYMENT RESULT
                        │
                        ▼
                   AUDIT TRAIL
```

---

## Safety First

Reviveo is designed so that the AI is **not the final authority**.

```text
AI can recommend an action
          ↓
Policy engine validates it
          ↓
Guardrails enforce limits
          ↓
High-risk actions require approval
          ↓
Every decision is logged
```

### Confidence Policy

| Confidence | Action                                                      |
| ---------- | ----------------------------------------------------------- |
| High       | Auto-execute allowed low-risk action                        |
| Medium     | Execute only permitted low-risk actions or request approval |
| Low        | Always escalate                                             |

---

## Core Features

* AI-powered recovery decisions
* Razorpay test-mode integration
* Payment failure detection
* Root-cause analysis
* Bounded AI action selection
* Smart retry scheduling
* Human approval workflow
* Runtime safety limits
* Idempotent webhook processing
* Recovery attribution
* Revenue analytics
* Full audit trail
* Synthetic simulation mode
* Multi-merchant-ready data model

---

## Dashboard

The dashboard provides a complete view of the recovery pipeline:

```text
Overview
├── Revenue at Risk
├── Recovered Revenue
├── Recovery Rate
├── Revenue Trends
└── Recent Events

Recovery Operations
├── Events
├── Audit Trail
├── Customers
├── Strategies
└── Approvals

Control
├── Guardrails
├── Reports
└── Simulations
```

---

## Tech Stack

### Frontend

* Next.js
* TypeScript
* Tailwind CSS
* shadcn/ui
* Recharts

### Backend

* Python
* FastAPI
* SQLAlchemy
* SQLite / PostgreSQL

### AI

* LLM-powered bounded decision agent
* Deterministic rule engine
* Structured outputs
* Tool and runtime limits

### Payments

* Razorpay Test Mode
* Razorpay Webhooks
* Payment Links
* Checkout and subscription event handling

---

## Project Structure

```text
reviveo/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── hooks/
│
├── backend/
│   ├── api/
│   ├── pipeline/
│   ├── agent/
│   ├── decision_engine/
│   ├── guardrails/
│   ├── execution/
│   ├── webhooks/
│   ├── services/
│   └── database/
│
├── docs/
│
└── README.md
```

---

## Recovery Attribution

Reviveo does not simply count any future payment from the same customer as recovered revenue.

Each recovery follows an explicit chain:

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

A payment is counted as recovered only when it:

1. Is explicitly linked to a recovery attempt.
2. Successfully resolves a new payment.
3. Falls within the configured recovery window.
4. Matches the relevant financial obligation.

---

## Audit Trail

Every significant decision and action is recorded.

```text
Detection
   ↓
Cause Analysis
   ↓
Decision
   ↓
Guardrail Check
   ↓
Approval / Execution
   ↓
Outcome
```

The goal is simple:

> Every recovery action should be explainable, bounded, and traceable.

---

## Running the Project

```bash
# Clone the repository
git clone <repository-url>

cd reviveo

# Start backend
cd backend
pip install -r requirements.txt

# Start frontend
cd ../frontend
npm install
npm run dev
```

Create the required environment variables before running payment integrations:

```env
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
DATABASE_URL=
LLM_API_KEY=
```

**Never commit secrets to Git.**

---

## Project Status

Reviveo is currently being built as an **AI Revenue Recovery Agent for Razorpay's test environment**.

The current scope focuses on:

```text
Detect
→ Analyze
→ Decide
→ Guard
→ Execute
→ Verify
→ Measure
```

---

## Why Reviveo?

Most systems stop at:

> "A payment failed."

Reviveo asks:

> "Why did it fail, what is the safest action we can take, and did that action actually recover revenue?"

---

## License

Built as a project for experimentation and demonstration.

---

**Reviveo — Recover revenue. Intelligently.**

If you want, I can next make this into a **proper premium GitHub README with badges, architecture image placeholders, screenshots section, and a strong hackathon-ready presentation style**.
