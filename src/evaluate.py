"""Évaluation de l'assistant sur le jeu de questions + suivi dans MLflow.

Usage :
  python src/evaluate.py                     # évaluation complète (retrieval + réponses)
  python src/evaluate.py --retrieval-only    # seulement le retrieval (rapide, sans appel au LLM)
  python src/evaluate.py --run-name chunks-500
"""
import argparse
import csv
import json
import subprocess
import time
from pathlib import Path

import mlflow
import yaml
from groq import APIConnectionError, APITimeoutError, RateLimitError

from rag import RAGAssistant
from scoring import check_answer, cites_expected_doc, compute_metrics, eval_fingerprint, retrieval_rank


def answer_with_retry(assistant, question, role, retries=3):
    """Réessaie en cas de limite de débit ou de coupure réseau (erreurs temporaires)."""
    for attempt in range(retries):
        try:
            return assistant.answer(question, role=role)
        except (RateLimitError, APIConnectionError, APITimeoutError) as e:
            wait = 20 * (attempt + 1)
            print(f"   {type(e).__name__} : nouvelle tentative dans {wait} s")
            time.sleep(wait)
    raise RuntimeError(f"Échec après {retries} tentatives")


# ---------- Évaluation ----------

def evaluate(assistant, questions, retrieval_only, pause_s):
    rows = []
    for q in questions:
        print(f"{q['id']} {q['question'][:70]}")
        row = {"id": q["id"], "categorie": q["categorie"], "role": q.get("role", "employe"), "question": q["question"]}
        try:
            if retrieval_only:
                sources = assistant.retrieve(q["question"], where=assistant.access_filter(q.get("role", "employe")))
                row.update(answer="", refused=None, latency_ms=None, prompt_tokens=0, completion_tokens=0)
            else:
                r = answer_with_retry(assistant, q["question"], q.get("role", "employe"))
                sources = r["sources"]
                row.update(answer=r["answer"], refused=r["refused"], refusal_reason=r.get("refusal_reason"),
                           latency_ms=r["latency_ms"], prompt_tokens=r["prompt_tokens"],
                           completion_tokens=r["completion_tokens"])
                time.sleep(pause_s)
            row["error"] = False
        except Exception as e:                       # une erreur ne doit pas arrêter toute l'évaluation
            print(f"   ERREUR : {e}")
            row["error"], row["answer"] = True, f"ERREUR : {e}"
            sources = assistant.retrieve(q["question"], where=assistant.access_filter(q.get("role", "employe")))

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
    fingerprint = eval_fingerprint()
    metrics_path.write_text(json.dumps(
        {"run_name": args.run_name, "mode": "retrieval_only" if args.retrieval_only else "complet",
         "fingerprint": fingerprint, "metrics": metrics}, indent=2, ensure_ascii=False), encoding="utf-8")

    # Suivi MLflow : paramètres + métriques + fichiers, pour pouvoir comparer et reconstruire
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment(params["experiment_name"])
    with mlflow.start_run(run_name=args.run_name):
        mlflow.log_params(flatten({k: all_params[k] for k in ("ingest", "index", "rag")}))
        mlflow.log_params({"git_commit": git_commit(), "n_questions": len(questions), "fingerprint": fingerprint,
                           "mode": "retrieval_only" if args.retrieval_only else "complet"})
        mlflow.log_metrics(metrics)
        # Une exécution avec des erreurs techniques n'est pas comparable aux autres : on la marque.
        mlflow.set_tag("valide", str(metrics["error_rate"] == 0))
        for path in (details_path, metrics_path, Path(params["questions_path"]), Path("params.yaml"), Path("dvc.lock")):
            mlflow.log_artifact(str(path))

    print("\n===== MÉTRIQUES =====")
    for k, v in metrics.items():
        print(f"  {k:<28} {v}")
    print(f"\nDétail par question : {details_path}")
    if metrics["error_rate"] > 0:
        print("\n⚠️  Des erreurs techniques ont eu lieu : cette exécution est marquée 'valide=False' "
              "dans MLflow et ne doit pas servir de comparaison. Relance l'évaluation.")


if __name__ == "__main__":
    main()
