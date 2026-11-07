"""Tests de la quality gate : elle doit rejeter une version dégradée ou une évaluation périmée."""
from quality_gate import check

GATES = {"min": {"recall_at_k": 0.85, "refusal_accuracy": 1.0}, "max": {"latency_p95_ms": 12000}}
GOOD = {"recall_at_k": 0.89, "refusal_accuracy": 1.0, "latency_p95_ms": 8100}


def verdicts(results, fingerprint="abc"):
    return [ok for *_, ok in check(results, GATES, fingerprint)]


def test_good_version_is_accepted():
    assert all(verdicts({"mode": "complet", "fingerprint": "abc", "metrics": GOOD}))


def test_degraded_metric_is_rejected():
    bad = dict(GOOD, refusal_accuracy=0.8)
    assert not all(verdicts({"mode": "complet", "fingerprint": "abc", "metrics": bad}))


def test_missing_metric_is_rejected():
    partial = {k: v for k, v in GOOD.items() if k != "recall_at_k"}
    assert not all(verdicts({"mode": "complet", "fingerprint": "abc", "metrics": partial}))


def test_outdated_evaluation_is_rejected():
    assert not all(verdicts({"mode": "complet", "fingerprint": "ancienne", "metrics": GOOD}))


def test_retrieval_only_evaluation_is_not_enough():
    assert not all(verdicts({"mode": "retrieval_only", "fingerprint": "abc", "metrics": GOOD}))
