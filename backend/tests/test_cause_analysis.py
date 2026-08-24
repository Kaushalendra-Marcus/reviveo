from app.domain.cause_analysis import classify_cause
from app.enums import Cause


def test_exact_reason_matches():
    assert classify_cause("card_expired") == Cause.card_expired
    assert classify_cause("insufficient_funds") == Cause.insufficient_funds
    assert classify_cause("payment_timed_out") == Cause.payment_timeout
    assert classify_cause("card_declined") == Cause.bank_declined
    assert classify_cause("payment_cancelled") == Cause.checkout_abandoned
    assert classify_cause("authentication_failed") == Cause.checkout_abandoned


def test_case_and_whitespace_insensitive():
    assert classify_cause("  Card_Expired  ") == Cause.card_expired
    assert classify_cause("INSUFFICIENT_FUNDS") == Cause.insufficient_funds


def test_keyword_fallback():
    assert classify_cause("UPI_INSUFFICIENT_BALANCE") == Cause.insufficient_funds
    assert classify_cause("NETBANKING_TIMEOUT") == Cause.payment_timeout
    assert classify_cause("WALLET_DECLINED_BY_ISSUER") == Cause.bank_declined


def test_unknown_code_is_unclassified():
    assert classify_cause("SOME_TOTALLY_NEW_CODE_XYZ") == Cause.unclassified


def test_missing_code_is_unclassified():
    assert classify_cause(None) == Cause.unclassified
    assert classify_cause("") == Cause.unclassified


def test_description_used_in_fallback():
    assert classify_cause("GATEWAY_ERR_99", "customer had insufficient funds") == Cause.insufficient_funds
