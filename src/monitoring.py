"""Monitoring : journal structuré des requêtes et rapport d'indicateurs.

- log_request(...) : ajoute une ligne JSON par requête dans logs/requetes.jsonl
- build_report(...) : calcule taux d'erreur, taux de refus, latence (moyenne, P95), tokens, similarité

Usage (rapport) : python src/monitoring.py
"""
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml


def load_params(path="params.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["monitoring"]


def make_record(question, role, model, result=None, error=None, log_questions=False):
    """Construit l'entrée du journal pour une requête (réussie ou en erreur)."""
    record = {
        "request_id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role": role,
        "model": model,
        "question_length": len(question),
        "error": error is not None,
        "error_type": type(error).__name__ if error is not None else None,
    }
    if log_questions:            # désactivé par défaut : une question RH peut contenir des données personnelles
        record["question"] = question
    if result is not None:
        record.update({
            "refused": result["refused"],
            "refusal_reason": result.get("refusal_reason"),
            "best_similarity": result["best_similarity"],
            "source_doc_ids": sorted({s["doc_id"] for s in result["sources"]}),
            "latency_ms": result["latency_ms"],
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
        })
    return record


def log_request(record, log_path):
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_log(log_path):
    path = Path(log_path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_report(records):
    """Indicateurs de monitoring (disponibilité, performance, qualité, coût, dérive)."""
    if not records:
        return {"n_requests": 0}
    ok = [r for r in records if not r["error"]]
    lat = [r["latency_ms"] for r in ok]
    tokens = [r["prompt_tokens"] + r["completion_tokens"] for r in ok]
    sims = [r["best_similarity"] for r in ok]

    def rnd(x, n=1):
        return round(float(x), n)

    return {
        "n_requests": len(records),
        "period": [records[0]["timestamp"], records[-1]["timestamp"]],
        # Disponibilité et erreurs
        "error_rate": rnd(1 - len(ok) / len(records), 3),
        "errors_by_type": dict(Counter(r["error_type"] for r in records if r["error"])),
        # Performance
        "latency_mean_ms": rnd(np.mean(lat)) if lat else None,
        "latency_p95_ms": rnd(np.percentile(lat, 95)) if lat else None,
        # Qualité observable en production (sans vérité terrain) : refus et similarité
        "refusal_rate": rnd(np.mean([r["refused"] for r in ok]), 3) if ok else None,
        "mean_best_similarity": rnd(np.mean(sims), 3) if sims else None,
        "low_similarity_share": rnd(np.mean([s < 0.80 for s in sims]), 3) if sims else None,
        # Coût
        "tokens_mean": rnd(np.mean(tokens)) if tokens else None,
        "tokens_total": int(sum(tokens)),
        # Usage
        "requests_by_role": dict(Counter(r["role"] for r in records)),
        "top_documents": dict(Counter(d for r in ok for d in r["source_doc_ids"]).most_common(5)),
    }


def main():
    params = load_params()
    report = build_report(read_log(params["log_path"]))
    Path(params["report_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(params["report_path"]).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("===== RAPPORT DE MONITORING =====")
    for k, v in report.items():
        print(f"  {k:<24} {v}")
    print(f"\n-> {params['report_path']}")


if __name__ == "__main__":
    main()
