"""Évaluation de l'assistant sur le jeu de questions + suivi dans MLflow.

Usage :
  python src/evaluate.py                     # évaluation complète (retrieval + réponses)
  python src/evaluate.py --retrieval-only    # seulement le retrieval (rapide, sans appel au LLM)
  python src/evaluate.py --run-name chunks-500
"""
import argparse
import csv
import json
import re
import subprocess
import time
from pathlib import Path

import mlflow
import numpy as np
import yaml
from groq import RateLimitError

from rag import RAGAssistant


# ---------- Critères de notation ----------

def retrieval_rank(sources, q):
    """Rang (1, 2, ...) du premier chunk pertinent dans le top k, ou None s'il n'y en a pas."""
    for rank, s in enumerate(sources, start=1):
        if s["doc_id"] in q["expected_doc_ids"]:
            if not q.get("expected_sections") or s["section"] in q["expected_sections"]:
                return rank
    return None


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


def cites_expected_doc(answer, q):
    return any(doc_id in answer for doc_id in q["expected_doc_ids"])


def answer_with_retry(assistant, question, retries=3):
    for attempt in range(retries):
        try:
            return assistant.answer(question)
        except RateLimitError:
            wait = 20 * (attempt + 1)
            print(f"   limite de débit Groq atteinte, nouvelle tentative dans {wait} s")
            time.sleep(wait)
    raise RuntimeError("Échec après plusieurs tentatives (limite de débit)")


# ---------- Évaluation ----------

def evaluate(assistant, questions, retrieval_only, pause_s):
    rows = []
    for q in questions:
        print(f"{q['id']} {q['question'][:70]}")
        row = {"id": q["id"], "categorie": q["categorie"], "question": q["question"]}
        try:
            if retrieval_only:
                sources = assistant.retrieve(q["question"])
                row.update(answer="", refused=None, latency_ms=None, prompt_tokens=0, completion_tokens=0)
            else:
                r = answer_with_retry(assistant, q["question"])
                sources = r["sources"]
                row.update(answer=r["answer"], refused=r["refused"], refusal_reason=r.get("refusal_reason"),
                           latency_ms=r["latency_ms"], prompt_tokens=r["prompt_tokens"],
                           completion_tokens=r["completion_tokens"])
                time.sleep(pause_s)
            row["error"] = False
        except Exception as e:                       # une erreur ne doit pas arrêter toute l'évaluation
            print(f"   ERREUR : {e}")
            sources, row["error"], row["answer"] = [], True, f"ERREUR : {e}"

        row["best_similarity"] = sources[0]["similarity"] if sources else None
        row["retrieved"] = " ; ".join(f"{s['chunk_id']}({s['similarity']:.3f})" for s in sources)
        if q["expected_doc_ids"]:
            rank = retrieval_rank(sources, q)
            row.update(retrieval_hit=rank is not None, rank=rank)
        if not retrieval_only and not row["error"]:
            if "must_contain" in q or "must_not_contain" in q:
                row["answer_ok"] = check_answer(row["answer"], q)
            if q.get("should_refuse"):
                row["refusal_ok"] = bool(row["refused"])
            if q["categorie"] == "normale":
                row["cites_expected_doc"] = cites_expected_doc(row["answer"], q)
        rows.append(row)
    return rows


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
        "max_best_sim_out_of_scope": max((r["best_similarity"] for r in out_scope if r["best_similarity"]), default=None),
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


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "inconnu"


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        out.update(flatten(v, key + ".") if isinstance(v, dict) else {key: v})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--run-name", default=None)
    args = parser.parse_args()

    with open("params.yaml", encoding="utf-8") as f:
        all_params = yaml.safe_load(f)
    params = all_params["evaluate"]
    with open(params["questions_path"], encoding="utf-8") as f:
        questions = yaml.safe_load(f)

    assistant = RAGAssistant()
    rows = evaluate(assistant, questions, args.retrieval_only, params["pause_s"])
    metrics = compute_metrics(rows, args.retrieval_only)

    # Sauvegarde locale des résultats
    results_dir = Path(params["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)
    details_path = results_dir / "details.csv"
    fields = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
    with open(details_path, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig : lisible dans Excel
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    metrics_path = results_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    # Suivi MLflow : paramètres + métriques + fichiers, pour pouvoir comparer et reconstruire
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment(params["experiment_name"])
    with mlflow.start_run(run_name=args.run_name):
        mlflow.log_params(flatten({k: all_params[k] for k in ("ingest", "index", "rag")}))
        mlflow.log_params({"git_commit": git_commit(), "n_questions": len(questions),
                           "mode": "retrieval_only" if args.retrieval_only else "complet"})
        mlflow.log_metrics(metrics)
        for path in (details_path, metrics_path, Path(params["questions_path"]), Path("params.yaml"), Path("dvc.lock")):
            mlflow.log_artifact(str(path))

    print("\n===== MÉTRIQUES =====")
    for k, v in metrics.items():
        print(f"  {k:<28} {v}")
    print(f"\nDétail par question : {details_path}")


if __name__ == "__main__":
    main()