"""Tests du pipeline RAG avec de faux composants (pas de modèle, pas de base, pas d'API)."""
from types import SimpleNamespace

import numpy as np
import pytest

from rag import REFUSAL, SYSTEM_PROMPT, RAGAssistant


class FakeEmbedder:
    def encode(self, texts, normalize_embeddings=True):
        return np.ones((len(texts), 4))


class FakeCollection:
    def __init__(self, distances):
        self.distances, self.last_where = distances, None

    def query(self, query_embeddings, n_results, where=None):
        self.last_where = where
        n = len(self.distances)
        metas = [{"doc_id": f"DOC-{i}", "section": f"Section {i}", "page": -1, "version": "1.0",
                  "statut": "en_vigueur", "niveau_acces": "public", "source": "x.md"} for i in range(n)]
        return {"ids": [[f"DOC-{i}-0000" for i in range(n)]], "documents": [[f"texte {i}" for i in range(n)]],
                "distances": [self.distances], "metadatas": [metas]}


class FakeLLM:
    def __init__(self, text):
        self.text, self.calls = text, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))],
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))


def make_assistant(distances, llm_text="Vous avez 22 jours [DOC-0, Section 0]."):
    a = RAGAssistant.__new__(RAGAssistant)          # sans __init__ : rien n'est chargé
    a.params = {"top_k": len(distances), "min_similarity": 0.80, "llm_model": "test",
                "temperature": 0.0, "max_tokens": 100}
    a.embedder, a.collection, a.llm = FakeEmbedder(), FakeCollection(distances), FakeLLM(llm_text)
    return a


def test_low_similarity_is_refused_without_calling_the_llm():
    a = make_assistant([0.30, 0.35])                 # similarité 0.70 < seuil 0.80
    r = a.answer("Quelle est la capitale de l'Australie ?")
    assert r["refused"] and r["refusal_reason"] == "low_similarity"
    assert r["answer"] == REFUSAL
    assert a.llm.calls == []                         # aucun token dépensé


def test_relevant_question_sends_context_and_rules_to_the_llm():
    a = make_assistant([0.10, 0.15])
    r = a.answer("Combien de jours de congé ?")
    assert not r["refused"] and r["prompt_tokens"] == 100
    messages = a.llm.calls[0]["messages"]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "texte 0" in messages[1]["content"] and "statut : en_vigueur" in messages[1]["content"]


def test_refusal_written_by_the_llm_is_detected():
    a = make_assistant([0.10], llm_text=REFUSAL)
    r = a.answer("Question sans réponse dans les documents")
    assert r["refused"] and r["refusal_reason"] == "llm"


def test_sources_are_sorted_with_similarity():
    a = make_assistant([0.10, 0.20])
    sources = a.retrieve("question")
    assert [s["similarity"] for s in sources] == pytest.approx([0.90, 0.80])


def test_metadata_filter_is_passed_to_the_vector_store():
    a = make_assistant([0.10])
    a.retrieve("question", where={"niveau_acces": "public"})
    assert a.collection.last_where == {"niveau_acces": "public"}
