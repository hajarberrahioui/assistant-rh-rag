"""Fonctions de notation de l'évaluation (pur Python : testables sans modèle ni API)."""
import hashlib
import json
import re

import numpy as np
import yaml


def normalize(text):
    """Met le texte sous une forme comparable, pour ne juger que le fond et pas la mise en forme :
    minuscules, espaces insécables -> espaces, apostrophe typographique -> ', gras Markdown supprimé,
    "quatorze (14) semaines" -> "quatorze 14 semaines"."""
    text = text.lower().replace(" ", " ").replace(" ", " ").replace("’", "'").replace("*", "")
    text = re.sub(r"\((\d+)\)", r"\1", text)
    return re.sub(r"\s+", " ", text)


def check_answer(answer, q):
    """Vrai si la réponse contient chaque élément de must_contain ("a|b" = a ou b)
    et aucun élément de must_not_contain."""
    text = normalize(answer)
    ok_contain = all(any(normalize(alt) in text for alt in item.split("|")) for item in q.get("must_contain", []))
    ok_not = not any(normalize(item) in text for item in q.get("must_not_contain", []))
    return ok_contain and ok_not


def retrieval_rank(sources, q):
    """Rang (1, 2, ...) du premier chunk pertinent dans le top k, ou None s'il n'y en a pas."""
    for rank, s in enumerate(sources, start=1):
        if s["doc_id"] in q["expected_doc_ids"]:
            if not q.get("expected_sections") or s["section"] in q["expected_sections"]:
                return rank
    return None


def cites_expected_doc(answer, q):
    return any(doc_id in answer for doc_id in q["expected_doc_ids"])


def mean(values):
    values = [v for v in values if v is not None]
    return round(float(np.mean(values)), 4) if values else None


def compute_metrics(rows, retrieval_only):
    with_docs = [r for r in rows if "retrieval_hit" in r]
    normal = [r for r in rows if r["categorie"] == "normale"]
    out_scope = [r for r in rows if r["categorie"] == "hors_perimetre"]
    m = {
        "recall_at_k": mean([r["retrieval_hit"] for r in with_docs]),
        "mrr": mean([1 / r["rank"] if r["rank"] else 0 for r in with_docs]),
        # pour calibrer le seuil min_similarity :
        "min_best_sim_in_scope": min((r["best_similarity"] for r in normal if r["best_similarity"]), default=None),
        "max_best_sim_out_of_scope": max((r["best_similarity"] for r in out_scope if r["best_similarity"]),
                                         default=None),
        "error_rate": mean([r["error"] for r in rows]),
    }
    if not retrieval_only:
        lat = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
        m.update({
            "answer_accuracy": mean([r["answer_ok"] for r in rows if "answer_ok" in r]),
            "answer_accuracy_normale": mean([r["answer_ok"] for r in normal if "answer_ok" in r]),
            "refusal_accuracy": mean([r["refusal_ok"] for r in rows if "refusal_ok" in r]),
            "false_refusal_rate": mean([bool(r["refused"]) for r in normal if not r["error"]]),
            "citation_rate": mean([r["cites_expected_doc"] for r in normal if "cites_expected_doc" in r]),
            "latency_mean_ms": round(float(np.mean(lat))) if lat else None,
            "latency_p95_ms": round(float(np.percentile(lat, 95))) if lat else None,
            "tokens_mean": mean([r["prompt_tokens"] + r["completion_tokens"] for r in rows if not r["error"]]),
        })
        for cat in sorted({r["categorie"] for r in rows}):
            scored = [r["answer_ok"] for r in rows if r["categorie"] == cat and "answer_ok" in r]
            if scored:
                m[f"accuracy_{cat}"] = mean(scored)
    return {k: v for k, v in m.items() if v is not None}


def eval_fingerprint(params_path="params.yaml", questions_path="eval/questions.yaml", lock_path="dvc.lock",
                     code_path="src/rag.py"):
    """Empreinte de tout ce qui détermine un résultat d'évaluation : paramètres du système,
    questions, données (chunks produits par l'ingestion, d'après dvc.lock) et code du pipeline RAG.

    L'index Chroma n'est volontairement PAS pris en compte : il est entièrement déterminé par les
    chunks, les paramètres d'indexation et le modèle d'embeddings (déjà dans l'empreinte), mais ses
    fichiers internes changent à chaque reconstruction (identifiants, dates), même à contenu identique.
    Les fichiers sont relus puis resérialisés : les fins de ligne Windows/Linux ne changent pas l'empreinte."""
    def load(path):
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    params = load(params_path)
    lock = load(lock_path)
    content = {
        "params": {k: params[k] for k in ("ingest", "index", "rag")},
        "questions": load(questions_path),
        "data": sorted(o["md5"] for o in lock["stages"]["ingest"].get("outs", [])),
        "code": open(code_path, encoding="utf-8").read().replace("\r\n", "\n"),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
