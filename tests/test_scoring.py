"""Tests des fonctions de notation : une erreur ici fausserait toute l'évaluation."""
import pytest

from scoring import check_answer, compute_metrics, eval_fingerprint, normalize, retrieval_rank


@pytest.mark.parametrize("answer, must", [
    ("jusqu’au **31 mars**", ["31 mars"]),                       # espace insécable + gras
    ("dure **quatorze (14) semaines**", ["14 semaines|quatorze semaines"]),  # chiffre entre parenthèses
    ("**30 jours**", ["30 jours"]),
])
def test_formatting_does_not_change_the_verdict(answer, must):
    assert check_answer(answer, {"must_contain": must})


def test_forbidden_content_fails_the_answer():
    q = {"must_contain": ["22"], "must_not_contain": ["60 jours"]}
    assert check_answer("Vous avez 22 jours.", q)
    assert not check_answer("Vous avez 22 jours, ou 60 jours selon la note.", q)


def test_normalize_is_case_insensitive():
    assert normalize("Portail RH") == "portail rh"


def test_retrieval_rank_respects_expected_section():
    q = {"expected_doc_ids": ["CDT-001"], "expected_sections": ["Article 231"]}
    sources = [{"doc_id": "CDT-001", "section": "Article 232"}, {"doc_id": "CDT-001", "section": "Article 231"}]
    assert retrieval_rank(sources, q) == 2
    assert retrieval_rank(sources[:1], q) is None


def test_metrics_are_computed_on_the_right_questions():
    rows = [
        {"categorie": "normale", "error": False, "best_similarity": 0.9, "retrieval_hit": True, "rank": 1,
         "answer_ok": True, "refused": False, "cites_expected_doc": True, "latency_ms": 1000,
         "prompt_tokens": 900, "completion_tokens": 100},
        {"categorie": "normale", "error": False, "best_similarity": 0.85, "retrieval_hit": False, "rank": None,
         "answer_ok": False, "refused": True, "cites_expected_doc": False, "latency_ms": 3000,
         "prompt_tokens": 900, "completion_tokens": 100},
        {"categorie": "hors_perimetre", "error": False, "best_similarity": 0.76, "refused": True,
         "refusal_ok": True, "latency_ms": 500, "prompt_tokens": 0, "completion_tokens": 0},
    ]
    m = compute_metrics(rows, retrieval_only=False)
    assert m["recall_at_k"] == 0.5 and m["mrr"] == 0.5
    assert m["answer_accuracy_normale"] == 0.5
    assert m["false_refusal_rate"] == 0.5 and m["refusal_accuracy"] == 1.0
    assert m["max_best_sim_out_of_scope"] == 0.76


def test_fingerprint_ignores_line_endings_but_not_parameters(tmp_path):
    files = {
        "params.yaml": "ingest: {chunk_size: 500}\nindex: {top: 1}\nrag: {top_k: 5}\n",
        "q.yaml": "- id: Q01\n",
        "dvc.lock": "stages:\n  ingest:\n    outs:\n    - md5: abc\n",
        "rag.py": "PROMPT = 'regles'\n",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    def fp():
        return eval_fingerprint(tmp_path / "params.yaml", tmp_path / "q.yaml", tmp_path / "dvc.lock",
                                tmp_path / "rag.py")

    reference = fp()
    (tmp_path / "params.yaml").write_bytes(files["params.yaml"].replace("\n", "\r\n").encode())
    assert fp() == reference                                   # Windows vs Linux : même empreinte
    (tmp_path / "params.yaml").write_text(files["params.yaml"].replace("500", "800"), encoding="utf-8")
    assert fp() != reference                                   # paramètre modifié : empreinte différente
    (tmp_path / "params.yaml").write_text(files["params.yaml"], encoding="utf-8")
    (tmp_path / "rag.py").write_text("PROMPT = 'autres regles'\n", encoding="utf-8")
    assert fp() != reference                                   # code / prompt modifié : empreinte différente
