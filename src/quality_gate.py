"""Quality gate : accepte ou rejette la version courante à partir de sa dernière évaluation.

Vérifie :
  1. que l'évaluation enregistrée (eval/results/metrics.json) correspond bien à la version
     actuelle des paramètres, des questions et des données (empreinte) ;
  2. que chaque métrique respecte son seuil (section quality_gates de params.yaml).
Code de sortie 0 = accepté, 1 = rejeté (ce qui fait échouer la CI).

Usage : python src/quality_gate.py
"""
import json
import sys
from pathlib import Path

import yaml

from scoring import eval_fingerprint


def check(results, gates, current_fingerprint):
    """Renvoie la liste des (contrôle, valeur, seuil, accepté)."""
    checks = [
        ("évaluation complète", results.get("mode"), "complet", results.get("mode") == "complet"),
        ("évaluation à jour (empreinte)", results.get("fingerprint"), current_fingerprint,
         results.get("fingerprint") == current_fingerprint),
    ]
    metrics = results.get("metrics", {})
    for name, threshold in gates.get("min", {}).items():
        value = metrics.get(name)
        checks.append((f"{name} >= {threshold}", value, threshold, value is not None and value >= threshold))
    for name, threshold in gates.get("max", {}).items():
        value = metrics.get(name)
        checks.append((f"{name} <= {threshold}", value, threshold, value is not None and value <= threshold))
    return checks


def main():
    with open("params.yaml", encoding="utf-8") as f:
        params = yaml.safe_load(f)
    results_path = Path(params["evaluate"]["results_dir"]) / "metrics.json"
    if not results_path.exists():
        print(f"REJETÉ : aucune évaluation trouvée ({results_path}). Lance python src/evaluate.py")
        sys.exit(1)
    results = json.loads(results_path.read_text(encoding="utf-8"))

    checks = check(results, params["quality_gates"], eval_fingerprint())
    for name, value, _, ok in checks:
        print(f"  {'OK   ' if ok else 'ÉCHEC'}  {name:<42} valeur : {value}")
    failed = [c for c in checks if not c[3]]
    if failed:
        print(f"\nREJETÉ : {len(failed)} contrôle(s) en échec.")
        if not checks[1][3]:
            print("L'évaluation ne correspond pas à la version actuelle : relance python src/evaluate.py et commite "
                  "eval/results/.")
        sys.exit(1)
    print("\nACCEPTÉ : tous les contrôles sont respectés.")


if __name__ == "__main__":
    main()
