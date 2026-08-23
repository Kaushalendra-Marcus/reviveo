"""Deterministic cause classification (doc C3 tool: `classify_cause`).

Maps a Razorpay payment-failure signal onto the bounded `Cause` vocabulary the
rest of the pipeline understands. The exact-match table below is built from
Razorpay's documented card-payment error `reason` values
(https://razorpay.com/docs/errors/payments/cards/, confirmed live). Other
payment methods (UPI, netbanking, wallets) publish their own reason vocabulary
under the same snake_case convention, so unseen codes fall through to a
keyword matcher rather than defaulting straight to `unclassified`.

Pure and deterministic — no I/O — so it is safe to call inline in the
pipeline and to expose as an agent tool (doc C3).
"""
from __future__ import annotations

from ..enums import Cause

# Exact Razorpay `error.reason` → Cause.
_REASON_MAP: dict[str, Cause] = {
    # card_expired
    "card_expired": Cause.card_expired,
    # insufficient_funds
    "insufficient_funds": Cause.insufficient_funds,
    # payment_timeout
    "payment_timed_out": Cause.payment_timeout,
    # bank_declined — bank/gateway/card-issuer declines and technical failures
    "card_declined": Cause.bank_declined,
    "payment_failed": Cause.bank_declined,
    "bank_downtime": Cause.bank_declined,
    "bank_technical_error": Cause.bank_declined,
    "gateway_technical_error": Cause.bank_declined,
    "card_not_enrolled": Cause.bank_declined,
    "card_disabled_for_online_payments": Cause.bank_declined,
    "debit_instrument_inactive": Cause.bank_declined,
    "debit_instrument_blocked": Cause.bank_declined,
    "payment_risk_check_failed": Cause.bank_declined,
    "incorrect_cvv": Cause.bank_declined,
    "transaction_limit_exceeded": Cause.bank_declined,
    # checkout_abandoned — customer-side incomplete/cancelled action
    "payment_cancelled": Cause.checkout_abandoned,
    "authentication_failed": Cause.checkout_abandoned,
}

# Fallback keyword rules for reason/code strings not in the exact map above
# (other payment methods follow the same naming convention but aren't all
# individually enumerated here). Checked in order; first match wins.
_KEYWORD_RULES: list[tuple[tuple[str, ...], Cause]] = [
    (("expired",), Cause.card_expired),
    (("insufficient", "no_balance", "low_balance"), Cause.insufficient_funds),
    (("timeout", "timed_out"), Cause.payment_timeout),
    (("cancelled", "canceled", "abandoned"), Cause.checkout_abandoned),
    (("declined", "decline", "downtime", "technical_error", "risk_check",
      "blocked", "inactive", "cvv", "limit_exceeded", "authentication_failed"),
     Cause.bank_declined),
]


def classify_cause(error_code: str | None, error_description: str | None = None) -> Cause:
    """Deterministically classify a payment failure signal.

    `error_code` is expected to be Razorpay's `error.reason` value where
    available (the most specific documented field); a broader `error.code`
    (e.g. BAD_REQUEST_ERROR) or a synthetic code from the batch simulator also
    works via the keyword fallback. Returns `Cause.unclassified` when nothing
    matches — the decision engine only ever allows `unclassified` to escalate
    to a human (doc §3.9), it never guesses.
    """
    if not error_code:
        return Cause.unclassified

    key = error_code.strip().lower()
    if key in _REASON_MAP:
        return _REASON_MAP[key]

    haystack = f"{key} {(error_description or '').lower()}"
    for keywords, cause in _KEYWORD_RULES:
        if any(kw in haystack for kw in keywords):
            return cause

    return Cause.unclassified
