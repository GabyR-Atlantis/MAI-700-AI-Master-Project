#!/usr/bin/env python3
"""Nested, serial-grouped comparison of Cox Elastic Net with the fixed Cox baseline."""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
from sklearn.impute import SimpleImputer
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.preprocessing import StandardScaler

from baseline import FEATURES, SEED, make_dataset

BASELINE_PENALIZER = 1.0
BASELINE_L1_RATIO = 0.0
PENALIZERS = (0.01, 0.1, 1.0)
L1_RATIOS = (0.25, 0.75)
OUTER_FOLDS = 5
INNER_FOLDS = 3


def grouped_splits(data: pd.DataFrame, folds: int, seed: int):
    summary = data.groupby("serial_number", sort=True).event.max()
    serials = summary.index.to_numpy()
    labels = summary.to_numpy(dtype=int)
    counts = np.bincount(labels, minlength=2)
    n_splits = min(folds, len(serials), int(counts[1]))
    if n_splits < 2:
        raise ValueError("Grouped cross-validation requires at least two serials")
    if counts[1] < 2:
        raise ValueError("At least two event-bearing serials are needed for held-out scoring")
    if counts[0] > 0:
        splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        indices = splitter.split(serials, labels)
    else:
        splitter = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
        indices = splitter.split(serials)
    return [(set(serials[train]), set(serials[test])) for train, test in indices]


def prepare(train: pd.DataFrame, test: pd.DataFrame):
    usable = [name for name in FEATURES if train[name].notna().any()]
    if not usable:
        raise ValueError("No SMART predictors have values in this training fold")
    imputer = SimpleImputer(strategy="median")
    x_train = imputer.fit_transform(train[usable])
    x_test = imputer.transform(test[usable])
    varying = np.nanstd(x_train, axis=0) > 0
    usable = [name for name, keep in zip(usable, varying) if keep]
    x_train, x_test = x_train[:, varying], x_test[:, varying]
    if not usable:
        raise ValueError("All available SMART predictors are constant in this training fold")
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train)
    x_test = scaler.transform(x_test)
    train_x = pd.DataFrame(x_train, columns=usable, index=train.index)
    test_x = pd.DataFrame(x_test, columns=usable, index=test.index)
    train_x["duration"] = train.duration.to_numpy()
    train_x["event"] = train.event.to_numpy()
    return train_x, test_x, {"imputer": imputer, "scaler": scaler, "features": usable}


def score_by_serial(model: CoxPHFitter, test: pd.DataFrame, test_x: pd.DataFrame):
    risk = model.predict_partial_hazard(test_x).to_numpy().ravel()
    scored = {}
    for serial, indices in test.groupby("serial_number").groups.items():
        rows = test.loc[indices]
        if not rows.event.eq(1).any():
            continue
        local_risk = risk[test.index.get_indexer(indices)]
        try:
            scored[str(serial)] = float(concordance_index(
                rows.duration.to_numpy(), -local_risk, rows.event.to_numpy()))
        except ZeroDivisionError:
            continue
    return scored


def fit_and_score(train: pd.DataFrame, test: pd.DataFrame, penalizer: float,
                  l1_ratio: float):
    if not train.event.eq(1).any():
        raise ValueError("Training partition has no observed event")
    train_x, test_x, transforms = prepare(train, test)
    model = CoxPHFitter(penalizer=penalizer, l1_ratio=l1_ratio)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(train_x, duration_col="duration", event_col="event")
    scores = score_by_serial(model, test, test_x)
    return scores, {**transforms, "model": model}, [str(w.message) for w in caught]


def mean_score(scores: dict[str, float]) -> float | None:
    return float(np.mean(list(scores.values()))) if scores else None


def did_not_converge(warnings_seen: list[str]) -> bool:
    return any("failed to converge" in message.lower() for message in warnings_seen)


def bootstrap_mean_ci(values: np.ndarray, iterations: int, seed: int):
    rng = np.random.default_rng(seed)
    draws = np.array([rng.choice(values, size=len(values), replace=True).mean()
                      for _ in range(iterations)])
    return [float(v) for v in np.quantile(draws, [0.025, 0.975])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "cox_elastic_net_output")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--bootstraps", type=int, default=2000)
    args = parser.parse_args()
    if args.bootstraps < 100:
        parser.error("--bootstraps must be at least 100")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = make_dataset(args.input)
    data.to_csv(args.output_dir / "analysis_dataset.csv", index=False)
    outer_splits = grouped_splits(data, OUTER_FOLDS, args.seed)

    baseline_scores: dict[str, float] = {}
    elastic_scores: dict[str, float] = {}
    selected: dict[str, dict] = {}
    outer_artifacts: dict[str, dict] = {}
    outer_fit_notes = {}
    experiment_trials = []

    for outer_number, (train_ids, test_ids) in enumerate(outer_splits, start=1):
        train = data[data.serial_number.isin(train_ids)]
        test = data[data.serial_number.isin(test_ids)]
        if set(train.serial_number) & set(test.serial_number):
            raise RuntimeError("Leakage guard failed: outer serial overlap")
        inner_splits = grouped_splits(train, min(INNER_FOLDS, len(train_ids)), args.seed + outer_number)
        candidate_scores: dict[tuple[float, float], list[float]] = {
            (penalty, l1): [] for penalty in PENALIZERS for l1 in L1_RATIOS
        }

        for inner_number, (inner_train_ids, inner_valid_ids) in enumerate(inner_splits, start=1):
            inner_train = train[train.serial_number.isin(inner_train_ids)]
            inner_valid = train[train.serial_number.isin(inner_valid_ids)]
            if set(inner_train.serial_number) & set(inner_valid.serial_number):
                raise RuntimeError("Leakage guard failed: inner serial overlap")
            for penalty, l1 in candidate_scores:
                trial = {"outer_fold": outer_number, "inner_fold": inner_number,
                         "penalizer": penalty, "l1_ratio": l1}
                try:
                    scores, _, fit_warnings = fit_and_score(inner_train, inner_valid, penalty, l1)
                    score = mean_score(scores)
                    trial["warnings"] = fit_warnings
                    if did_not_converge(fit_warnings):
                        trial["result"] = "rejected: optimizer did not converge"
                    elif score is None:
                        trial["result"] = "negative: no comparable event-bearing validation serials"
                    else:
                        candidate_scores[(penalty, l1)].append(score)
                        trial["mean_validation_c_index"] = score
                        trial["result"] = "scored"
                except Exception as exc:
                    trial["result"] = "failed"
                    trial["error"] = f"{type(exc).__name__}: {exc}"
                experiment_trials.append(trial)

        means = {params: float(np.mean(scores)) for params, scores in candidate_scores.items()
                 if len(scores) == len(inner_splits)}
        if not means:
            raise RuntimeError(f"No Elastic Net candidate completed inner validation in outer fold {outer_number}")
        best_params = max(means, key=means.get)
        selected[str(outer_number)] = {"penalizer": best_params[0], "l1_ratio": best_params[1],
                                       "inner_mean_c_index": means[best_params]}

        base_fold_scores, base_artifact, base_warnings = fit_and_score(
            train, test, BASELINE_PENALIZER, BASELINE_L1_RATIO)
        en_fold_scores, en_artifact, en_warnings = fit_and_score(
            train, test, best_params[0], best_params[1])
        if did_not_converge(base_warnings) or did_not_converge(en_warnings):
            raise RuntimeError(f"Non-converged final fit in outer fold {outer_number}; refusing to report its score")
        baseline_scores.update(base_fold_scores)
        elastic_scores.update(en_fold_scores)
        outer_artifacts[str(outer_number)] = {
            "baseline": base_artifact, "elastic_net": en_artifact,
            "test_serials": sorted(test_ids),
            "baseline_warnings": base_warnings, "elastic_net_warnings": en_warnings,
        }
        outer_fit_notes[str(outer_number)] = {
            "baseline_warnings": base_warnings,
            "elastic_net_warnings": en_warnings,
        }

    # Select deployable settings using grouped CV on all available data, then refit.
    final_splits = grouped_splits(data, INNER_FOLDS, args.seed + 1000)
    final_candidate_scores = {(penalty, l1): [] for penalty in PENALIZERS for l1 in L1_RATIOS}
    for fold_number, (fit_ids, valid_ids) in enumerate(final_splits, start=1):
        fit_data = data[data.serial_number.isin(fit_ids)]
        valid_data = data[data.serial_number.isin(valid_ids)]
        for penalty, l1 in final_candidate_scores:
            trial = {"stage": "final_model_tuning", "inner_fold": fold_number,
                     "penalizer": penalty, "l1_ratio": l1}
            try:
                scores, _, fit_warnings = fit_and_score(fit_data, valid_data, penalty, l1)
                trial["warnings"] = fit_warnings
                score = mean_score(scores)
                if did_not_converge(fit_warnings):
                    trial["result"] = "rejected: optimizer did not converge"
                elif score is None:
                    trial["result"] = "negative: no comparable event-bearing validation serials"
                else:
                    final_candidate_scores[(penalty, l1)].append(score)
                    trial["mean_validation_c_index"] = score
                    trial["result"] = "scored"
            except Exception as exc:
                trial["result"] = "failed"
                trial["error"] = f"{type(exc).__name__}: {exc}"
            experiment_trials.append(trial)
    final_means = {params: float(np.mean(values)) for params, values in final_candidate_scores.items()
                   if len(values) == len(final_splits)}
    if not final_means:
        raise RuntimeError("No Elastic Net candidate completed final grouped tuning")
    final_params = max(final_means, key=final_means.get)
    full_x, _, final_transforms = prepare(data, data)
    final_model = CoxPHFitter(penalizer=final_params[0], l1_ratio=final_params[1])
    with warnings.catch_warnings(record=True) as final_warnings:
        warnings.simplefilter("always")
        final_model.fit(full_x, duration_col="duration", event_col="event")
    if did_not_converge([str(w.message) for w in final_warnings]):
        raise RuntimeError("Final full-data model did not converge")
    final_artifact = {**final_transforms, "model": final_model}

    common = sorted(set(baseline_scores) & set(elastic_scores))
    if not common:
        raise RuntimeError("No common event-bearing serials were scored for both models")
    base_values = np.array([baseline_scores[s] for s in common])
    en_values = np.array([elastic_scores[s] for s in common])
    delta = en_values - base_values
    result = {
        "input": str(args.input.resolve()),
        "model": "Nested grouped Cox Elastic Net",
        "n_serials": int(data.serial_number.nunique()),
        "n_observations": int(len(data)),
        "event_serials": int(data.loc[data.event.eq(1), "serial_number"].nunique()),
        "censored_serials": int(data.loc[data.event.eq(0), "serial_number"].nunique()),
        "outer_validation": f"{len(outer_splits)}-fold stratified/grouped by serial",
        "inner_validation": f"up to {INNER_FOLDS}-fold grouped by serial",
        "hyperparameter_grid": {"penalizer": list(PENALIZERS), "l1_ratio": list(L1_RATIOS)},
        "selected_by_outer_fold": selected,
        "final_model_parameters": {"penalizer": final_params[0], "l1_ratio": final_params[1],
                                   "inner_mean_c_index": final_means[final_params]},
        "outer_fit_notes": outer_fit_notes,
        "baseline": {
            "penalizer": BASELINE_PENALIZER, "l1_ratio": BASELINE_L1_RATIO,
            "n_scored_serials": len(common), "macro_c_index": float(base_values.mean()),
            "cluster_bootstrap_95_percentile_interval": bootstrap_mean_ci(base_values, args.bootstraps, args.seed),
        },
        "elastic_net": {
            "n_scored_serials": len(common), "macro_c_index": float(en_values.mean()),
            "cluster_bootstrap_95_percentile_interval": bootstrap_mean_ci(en_values, args.bootstraps, args.seed + 1),
            "between_serial_sd": float(en_values.std(ddof=1)) if len(en_values) > 1 else None,
        },
        "paired_difference_elastic_net_minus_baseline": {
            "macro_c_index_delta": float(delta.mean()),
            "cluster_bootstrap_95_percentile_interval": bootstrap_mean_ci(delta, args.bootstraps, args.seed + 2),
        },
        "per_serial_scores": {s: {"baseline": baseline_scores[s], "elastic_net": elastic_scores[s],
                                   "delta": elastic_scores[s] - baseline_scores[s]} for s in common},
        "seed": args.seed, "bootstrap_iterations": args.bootstraps,
        "leakage_checks": {"outer_and_inner_serial_overlap": 0,
                           "preprocessing_fit_within_training_folds": True,
                           "hyperparameters_selected_inside_outer_training": True},
        "experiment_trials": experiment_trials,
    }
    (args.output_dir / "experiment_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    pd.DataFrame(experiment_trials).to_csv(args.output_dir / "inner_trials.csv", index=False)
    joblib.dump({"outer_fold_models": outer_artifacts, "final_model": final_artifact},
                args.output_dir / "cox_elastic_net_models.joblib")
    print(json.dumps({k: v for k, v in result.items() if k != "experiment_trials"}, indent=2))


if __name__ == "__main__":
    main()
