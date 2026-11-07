"""Indexation : calcul des embeddings des chunks et stockage dans ChromaDB.

Entrée  : data/processed/chunks.jsonl
Sortie  : data/index/ (base Chroma persistée sur disque)
Usage   : python src/index.py
"""
import json
import time

import chromadb
import yaml
from sentence_transformers import SentenceTransformer


def load_params(path="params.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["index"]


def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def to_chroma_metadata(chunk):
    """Chroma n'accepte pas les valeurs None : on les remplace (page -1, section vide)."""
    meta = {k: v for k, v in chunk.items() if k not in ("chunk_id", "text")}
    meta["page"] = meta["page"] if meta["page"] is not None else -1
    meta["section"] = meta["section"] or ""
    return meta


def main():
    params = load_params()
    chunks = load_chunks(params["chunks_path"])

    # Modèle multilingue (nos documents sont en français).
    # Les modèles E5 attendent le préfixe "passage: " pour les documents
    # et "query: " pour les questions : c'est ainsi qu'ils ont été entraînés.
    model = SentenceTransformer(params["embedding_model"])
    texts = ["passage: " + c["text"] for c in chunks]

    start = time.time()
    embeddings = model.encode(
        texts,
        batch_size=params["batch_size"],
        normalize_embeddings=True,   # vecteurs de norme 1 -> similarité cosinus
        show_progress_bar=True,
    )
    print(f"{len(texts)} embeddings calculés en {time.time() - start:.1f} s "
          f"(dimension {embeddings.shape[1]})")

    # On reconstruit l'index de zéro à chaque exécution : résultat reproductible.
    client = chromadb.PersistentClient(path=params["index_dir"])
    if params["collection"] in [c.name for c in client.list_collections()]:
        client.delete_collection(params["collection"])
    collection = client.create_collection(
        name=params["collection"],
        metadata={"hnsw:space": "cosine", "embedding_model": params["embedding_model"]},
    )

    batch = 500
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        collection.add(
            ids=[c["chunk_id"] for c in part],
            documents=[c["text"] for c in part],
            embeddings=embeddings[i:i + batch].tolist(),
            metadatas=[to_chroma_metadata(c) for c in part],
        )
    print(f"Index '{params['collection']}' : {collection.count()} chunks -> {params['index_dir']}")


if __name__ == "__main__":
    main()
