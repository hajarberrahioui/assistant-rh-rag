"""Validation de la configuration et du jeu d'évaluation (contrôles « données » des quality gates)."""
import re

import pytest
import yaml
from conftest import ROOT

CATEGORIES = {"normale", "hors_perimetre", "piege_obsolete", "piege_injection",
              "acces_restreint", "cas_individuel", "ambigue"}


@pytest.fixture(scope="module")
def params():
    return yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def questions():
    return yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def known_doc_ids():
    text = (ROOT / "docs" / "inventaire_corpus.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| ([A-Z]+-\d+) \|", text, flags=re.MULTILINE))


def test_parameters_are_consistent(params):
    ingest, rag = params["ingest"], params["rag"]
    assert 0 <= ingest["chunk_overlap"] < ingest["chunk_size"]
    assert rag["top_k"] >= 1
    assert 0 < rag["min_similarity"] < 1
    assert 0 <= rag["temperature"] <= 1


def test_quality_gates_are_defined(params):
    gates = params["quality_gates"]
    assert gates["min"] and gates["max"]
    assert all(0 <= v <= 1 for k, v in gates["min"].items())


def test_question_ids_are_unique(questions):
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids))


def test_questions_are_well_formed(questions, known_doc_ids):
    for q in questions:
        assert q["categorie"] in CATEGORIES, q["id"]
        assert q["question"].strip(), q["id"]
        assert set(q["expected_doc_ids"]) <= known_doc_ids, f"{q['id']} : document inconnu"
        assert all(item.strip() for item in q.get("must_contain", [])), q["id"]
        if q.get("should_refuse"):
            assert q["expected_doc_ids"] == [], f"{q['id']} : un refus n'attend aucun document"


def test_every_category_is_represented(questions):
    assert {"normale", "hors_perimetre", "piege_obsolete", "piege_injection"} <= {q["categorie"] for q in questions}
