"""Stress test de los modelos externos frente a pérdida de SMART.

Usa exclusivamente los HDD externos guardados en el artefacto de validación;
no reajusta los modelos. Escribe resultados por escenario y modelo.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lifelines.utils import concordance_index

ROOT = Path(__file__).parent
RNG = np.random.default_rng(700)


def main() -> None:
    data = pd.read_csv(ROOT / "cox_elastic_net_output" / "analysis_dataset.csv")
    artifact = joblib.load(ROOT / "cox_elastic_net_output" / "cox_elastic_net_models.joblib")
    scores: dict[str, dict[str, list[float]]] = {
        scenario: {model: [] for model in ("baseline", "elastic_net")}
        for scenario in ("sin_cambio", "50pct_smart_ausente", "todos_smart_ausentes")
    }

    for fold in artifact["outer_fold_models"].values():
        test = data[data.serial_number.isin(fold["test_serials"])]
        for model_name in ("baseline", "elastic_net"):
            fitted = fold[model_name]
            features = fitted["features"]
            imputer_features = list(fitted["imputer"].feature_names_in_)
            for serial, group in test.groupby("serial_number"):
                if not group.event.eq(1).any():
                    continue
                raw = group.reindex(columns=imputer_features).copy()
                partially_missing = raw.copy()
                mask = RNG.random(partially_missing.shape) < 0.5
                partially_missing = partially_missing.mask(mask)
                scenarios = {
                    "sin_cambio": raw.copy(),
                    "50pct_smart_ausente": partially_missing,
                    "todos_smart_ausentes": raw.copy(),
                }
                scenarios["todos_smart_ausentes"] = raw.copy()
                scenarios["todos_smart_ausentes"].loc[:, :] = np.nan

                for scenario, values in scenarios.items():
                    imputed = fitted["imputer"].transform(values)
                    imputed = pd.DataFrame(imputed, columns=imputer_features, index=group.index).loc[:, features]
                    transformed = fitted["scaler"].transform(imputed.to_numpy())
                    x = pd.DataFrame(transformed, columns=features, index=group.index)
                    risk = fitted["model"].predict_partial_hazard(x).to_numpy().ravel()
                    score = concordance_index(group.duration, -risk, group.event)
                    scores[scenario][model_name].append(float(score))

    rng = np.random.default_rng(2026)
    result = {"scored_serials": len(scores["sin_cambio"]["baseline"]), "scenarios": {}}
    for scenario, models in scores.items():
        means = {name: float(np.mean(values)) for name, values in models.items()}
        delta = np.asarray(models["elastic_net"]) - np.asarray(models["baseline"])
        boot = {
            name: np.array([rng.choice(values, size=len(values), replace=True).mean() for _ in range(2000)])
            for name, values in models.items()
        }
        boot_delta = np.array([rng.choice(delta, size=len(delta), replace=True).mean() for _ in range(2000)])
        result["scenarios"][scenario] = {
            "baseline_macro_c_index": means["baseline"],
            "baseline_cluster_bootstrap_95_interval": [float(v) for v in np.quantile(boot["baseline"], [0.025, 0.975])],
            "elastic_net_macro_c_index": means["elastic_net"],
            "elastic_net_cluster_bootstrap_95_interval": [float(v) for v in np.quantile(boot["elastic_net"], [0.025, 0.975])],
            "paired_delta": float(delta.mean()),
            "paired_delta_cluster_bootstrap_95_interval": [float(v) for v in np.quantile(boot_delta, [0.025, 0.975])],
        }
    out = ROOT / "cox_elastic_net_output" / "robustness_results.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
