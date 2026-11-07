"""Tests unitaires de l'ingestion : lecture, découpage, métadonnées."""
from pathlib import Path

import pytest

from ingest import build_chunks, read_markdown, split_pdf_articles, split_text

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


def test_front_matter_is_read_as_metadata():
    meta, body = read_markdown(FIXTURES / "politique_test_v1.md")
    assert meta["doc_id"] == "TEST-001"
    assert meta["statut"] == "obsolete"
    assert body.lstrip().startswith("# Politique de test")


def test_windows_line_endings_are_supported(tmp_path):
    path = tmp_path / "doc.md"
    path.write_bytes((FIXTURES / "grille_test.md").read_bytes().replace(b"\n", b"\r\n"))
    meta, _ = read_markdown(path)
    assert meta["doc_id"] == "TEST-002"


def test_missing_front_matter_is_rejected(tmp_path):
    path = tmp_path / "sans_metadonnees.md"
    path.write_text("# Titre\n\nTexte", encoding="utf-8")
    with pytest.raises(ValueError):
        read_markdown(path)


def test_chunks_never_exceed_size_nor_cut_words():
    text = " ".join(f"Phrase numéro {i} du règlement intérieur." for i in range(200))
    chunks = split_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    words = set(text.split())
    for c in chunks:
        assert c.split()[0] in words and c.split()[-1] in words   # début et fin = mots entiers


def test_pdf_is_split_by_article_across_pages():
    pages = [(1, "Préambule\nArticle premier\nTexte un.\nArticle 2\nDébut de l'article"),
             (2, "suite de l'article deux.\nArticle 3 bis\nTexte trois.")]
    articles = split_pdf_articles(pages)
    assert [a[0] for a in articles] == ["Préambule", "Article premier", "Article 2", "Article 3 bis"]
    assert articles[2] == ("Article 2", 1, "Début de l'article suite de l'article deux.")


def test_every_chunk_carries_metadata_and_a_unique_id():
    chunks = build_chunks(FIXTURES, chunk_size=500, overlap=50)
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)
    for c in chunks:
        for key in ("doc_id", "source", "version", "statut", "niveau_acces", "text"):
            assert c[key], f"{key} manquant dans {c['chunk_id']}"
        assert c["text"].startswith(c["titre"])                    # le titre est rappelé dans le chunk
    assert {c["niveau_acces"] for c in chunks} == {"public", "rh"}
