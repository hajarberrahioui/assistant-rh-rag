"""Tests du monitoring : journal structuré, confidentialité, indicateurs."""
from monitoring import build_report, log_request, make_record, read_log

RESULT = {"refused": False, "refusal_reason": None, "best_similarity": 0.9, "latency_ms": 1000,
          "prompt_tokens": 900, "completion_tokens": 100,
          "sources": [{"doc_id": "CONG-002"}, {"doc_id": "CONG-002"}, {"doc_id": "CDT-001"}]}


def test_question_text_is_not_logged_by_default():
    record = make_record("Mon salaire est-il correct ?", "employe", "m", result=RESULT)
    assert "question" not in record and record["question_length"] == 28


def test_errors_are_logged_with_their_type():
    record = make_record("q", "rh", "m", error=TimeoutError("api"))
    assert record["error"] and record["error_type"] == "TimeoutError"


def test_log_is_appended_and_read_back(tmp_path):
    path = tmp_path / "logs" / "requetes.jsonl"
    for _ in range(3):
        log_request(make_record("q", "employe", "m", result=RESULT), path)
    assert len(read_log(path)) == 3


def test_report_indicators():
    records = [make_record("q", "employe", "m", result=dict(RESULT, latency_ms=ms)) for ms in (1000, 2000, 3000)]
    records.append(make_record("q", "rh", "m", error=RuntimeError()))
    report = build_report(records)
    assert report["n_requests"] == 4
    assert report["error_rate"] == 0.25
    assert report["latency_mean_ms"] == 2000
    assert report["requests_by_role"] == {"employe": 3, "rh": 1}
    assert report["top_documents"]["CONG-002"] == 3


def test_empty_log_gives_empty_report(tmp_path):
    assert build_report(read_log(tmp_path / "absent.jsonl")) == {"n_requests": 0}
