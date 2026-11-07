"""Ingestion du corpus : lecture (Markdown + PDF), nettoyage, découpage en chunks, métadonnées.

Entrée  : les documents de data/raw/
Sortie  : data/processed/chunks.jsonl (un chunk par ligne, au format JSON)
Usage   : python src/ingest.py
"""
import json
import re
from pathlib import Path

import pymupdf
import yaml

# Métadonnées des PDF (un PDF n'a pas de front matter, on les déclare ici).
PDF_METADATA = {
    "code_du_travail.pdf": {
        "doc_id": "CDT-001",
        "titre": "Code du travail marocain (loi n° 65-99)",
        "type": "loi",
        "version": "consolidee-2011",
        "date": "2011-10-26",
        "niveau_acces": "public",
        "statut": "en_vigueur",
    }
}


def load_params(path="params.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["ingest"]


# ---------- 1. Lecture ----------

def read_markdown(path: Path):
    """Sépare le front matter (métadonnées YAML) du contenu Markdown."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")  # fins de ligne Windows
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Front matter manquant dans {path.name}")
    metadata = yaml.safe_load(match.group(1))
    return metadata, match.group(2)


def read_pdf(path: Path):
    """Renvoie la liste des (numéro de page, texte) du PDF."""
    with pymupdf.open(path) as doc:
        return [(i + 1, page.get_text()) for i, page in enumerate(doc)]


# ---------- 2. Nettoyage ----------

def clean_text(text: str) -> str:
    text = re.sub(r"^\s*-\s*\d+\s*-\s*$", "", text, flags=re.MULTILINE)  # numéros de page "- 12 -"
    text = re.sub(r"[ \t]+", " ", text)          # espaces multiples
    text = re.sub(r"\n{3,}", "\n\n", text)       # lignes vides multiples
    return text.strip()


# ---------- 3. Découpage ----------

def split_markdown_sections(body: str):
    """Coupe le Markdown à chaque titre (#, ##, ###) -> liste de (titre, contenu)."""
    sections, title, lines = [], "Introduction", []
    for line in body.splitlines():
        if re.match(r"^#{1,3} ", line):
            if "".join(lines).strip():
                sections.append((title, "\n".join(lines)))
            title, lines = line.lstrip("#").strip(), []
        else:
            lines.append(line)
    if "".join(lines).strip():
        sections.append((title, "\n".join(lines)))
    return sections


def split_pdf_articles(pages):
    """Recolle les pages du PDF puis coupe le texte à chaque "Article N".

    Renvoie une liste de (titre de l'article, page de début, texte).
    Un article peut commencer sur une page et finir sur la suivante :
    c'est pour ça qu'on recolle d'abord toutes les pages.
    """
    full, starts = "", []                      # starts : (position dans full, numéro de page)
    for page, text in pages:
        starts.append((len(full), page))
        full += clean_text(text) + "\n"

    def page_at(pos):
        return max(p for start, p in starts if start <= pos)

    pattern = re.compile(r"^\s*(Article\s+(?:premier|\d+(?:\s*bis)?))\s*$", flags=re.MULTILINE)
    matches = list(pattern.finditer(full))
    segments = []
    if matches and matches[0].start() > 0:
        segments.append(("Préambule", 1, full[:matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full)
        segments.append((m.group(1), page_at(m.start()), full[m.end():end]))

    # Dans le PDF, chaque ligne est coupée (texte justifié) : on recolle les lignes.
    return [(title, page, re.sub(r"\s*\n\s*", " ", text).strip())
            for title, page, text in segments if text.strip()]


def split_sentences(text: str, max_len: int):
    """Coupe un texte trop long en phrases (puis en mots si une phrase est trop longue)."""
    units = []
    for sentence in re.split(r"(?<=[.;:!?])\s+", text):
        while len(sentence) > max_len:
            cut = sentence.rfind(" ", 0, max_len)
            cut = cut if cut > 0 else max_len
            units.append(sentence[:cut])
            sentence = sentence[cut:].strip()
        if sentence:
            units.append(sentence)
    return units


def split_text(text: str, chunk_size: int, overlap: int):
    """Regroupe paragraphes / phrases jusqu'à chunk_size caractères, avec un chevauchement.

    On ne coupe jamais au milieu d'un mot : un paragraphe trop long est découpé en phrases.
    """
    units = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if paragraph:
            units.extend([paragraph] if len(paragraph) <= chunk_size
                         else split_sentences(paragraph, chunk_size))

    chunks, current = [], ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + len(unit) + 1 <= chunk_size:
            current = f"{current}\n{unit}"
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            tail = tail[tail.find(" ") + 1:] if " " in tail else ""   # repartir sur un début de mot
            current = f"{tail} {unit}".strip() if len(tail) + len(unit) + 1 <= chunk_size else unit
    if current:
        chunks.append(current)
    return chunks


# ---------- 4. Pipeline ----------

def build_chunks(raw_dir: Path, chunk_size: int, overlap: int):
    all_chunks = []
    for path in sorted(raw_dir.iterdir()):
        if path.suffix == ".md":
            meta, body = read_markdown(path)
            pieces = []
            for section, content in split_markdown_sections(body):
                for text in split_text(clean_text(content), chunk_size, overlap):
                    pieces.append({"section": section, "page": None, "text": text})
        elif path.suffix == ".pdf":
            meta = PDF_METADATA[path.name]
            pieces = []
            for article, page, content in split_pdf_articles(read_pdf(path)):
                for text in split_text(content, chunk_size, overlap):
                    pieces.append({"section": article, "page": page, "text": text})
        else:
            continue

        for i, piece in enumerate(pieces):
            # Le titre du document et de la section est ajouté au texte :
            # un chunk "Report : jusqu'au 31 mars" seul ne dit pas de quoi il parle.
            header = meta["titre"] + (f" > {piece['section']}" if piece["section"] else "")
            all_chunks.append({
                "chunk_id": f"{meta['doc_id']}-{i:04d}",
                "text": f"{header}\n\n{piece['text']}",
                "source": path.name,
                "page": piece["page"],
                "section": piece["section"],
                **{k: str(meta[k]) for k in ("doc_id", "titre", "type", "version", "date", "niveau_acces", "statut")},
            })
    return all_chunks


def main():
    params = load_params()
    chunks = build_chunks(Path(params["raw_dir"]), params["chunk_size"], params["chunk_overlap"])
    output = Path(params["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    docs = sorted({c["doc_id"] for c in chunks})
    print(f"{len(chunks)} chunks créés à partir de {len(docs)} documents -> {output}")
    for d in docs:
        print(f"  {d}: {sum(c['doc_id'] == d for c in chunks)} chunks")


if __name__ == "__main__":
    main()