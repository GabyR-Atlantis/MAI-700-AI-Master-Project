#!/usr/bin/env python3
"""Exploratory Cox baseline evaluated by holding out whole failed HDDs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

FEATURES = ["smart_5_normalized", "smart_187_normalized", "smart_188_normalized",
            "smart_197_normalized", "smart_198_normalized", "smart_199_normalized",
            "smart_9_normalized"]
SEED = 2026


def make_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    required = {"date", "serial_number", "failure", *FEATURES}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} lacks columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["failure"] = pd.to_numeric(df["failure"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["date", "serial_number"])
    df["serial_number"] = df["serial_number"].astype(str)
    records = []
    for serial, group in df.groupby("serial_number", sort=True):
        group = group.sort_values("date")
        failure_dates = group.loc[group.failure.eq(1), "date"]
        if failure_dates.empty:
            raise ValueError(f"{serial} has no failure row; this input should contain failed drives")
        failure_date = failure_dates.min()
        # Only pre-failure snapshots are predictions. The failure-day row is excluded.
        history = group.loc[group.date < failure_date]
        for row in history.itertuples(index=False):
            record = {"serial_number": serial, "date": row.date,
                      "duration": int((failure_date - row.date).days), "event": 1}
            record.update({feature: getattr(row, feature) for feature in FEATURES})
            records.append(record)
    data = pd.DataFrame(records)
    if data.empty or data.serial_number.nunique() < 3:
        raise ValueError("Need at least three failed HDD histories for grouped evaluation")
    if (data.duration <= 0).any() or not data.event.eq(1).all():
        raise RuntimeError("Outcome construction failed: every row must precede a known failure")
    return data


def fit_fold(train: pd.DataFrame, test: pd.DataFrame, seed: int):
    # Drop SMART columns wholly missing or constant in this fold's training HDDs.
    usable = [c for c in FEATURES if train[c].notna().any()]
    if not usable:
        raise ValueError("No SMART features are observed in the training HDDs")
    imputer = SimpleImputer(strategy="median")
    x_train = imputer.fit_transform(train[usable])
    x_test = imputer.transform(test[usable])
    varying = np.nanstd(x_train, axis=0) > 0
    usable = [c for c, keep in zip(usable, varying) if keep]
    x_train, x_test = x_train[:, varying], x_test[:, varying]
    if not usable:
        raise ValueError("All observed SMART features are constant in this fold")
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train)
    x_test = scaler.transform(x_test)
    fit = pd.DataFrame(x_train, columns=usable)
    fit["duration"] = train.duration.to_numpy()
    fit["event"] = train.event.to_numpy()
    model = CoxPHFitter(penalizer=1.0)
    model.fit(fit, duration_col="duration", event_col="event")
    risk = model.predict_partial_hazard(pd.DataFrame(x_test, columns=usable)).to_numpy().ravel()
    score = float(concordance_index(test.duration, -risk, test.event))
    return score, {"model": model, "imputer": imputer, "scaler": scaler, "features": usable}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).parent / "failed_drive_histories.csv")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "baseline_output")
    parser.add_argument("--bootstraps", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.bootstraps < 100:
        parser.error("--bootstraps must be at least 100")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = make_dataset(args.input)
    data.to_csv(args.output_dir / "landmark_dataset.csv", index=False)

    serials = sorted(data.serial_number.unique())
    drive_scores, artifacts = {}, {}
    for held_out in serials:
        train = data.loc[data.serial_number.ne(held_out)]
        test = data.loc[data.serial_number.eq(held_out)]
        if set(train.serial_number) & set(test.serial_number):
            raise RuntimeError("Leakage guard failed: train/test serial overlap")
        score, artifact = fit_fold(train, test, args.seed)
        drive_scores[held_out] = score
        artifacts[held_out] = artifact

    # The independent unit is the HDD, not its repeated daily rows.
    scores = np.array(list(drive_scores.values()), dtype=float)
    rng = np.random.default_rng(args.seed)
    boot_means = np.array([rng.choice(scores, size=len(scores), replace=True).mean()
                           for _ in range(args.bootstraps)])
    low, high = np.quantile(boot_means, [0.025, 0.975])
    result = {
        "model": "Cox proportional hazards (penalizer=1.0)",
        "input": str(args.input.resolve()),
        "n_drives": len(serials), "n_snapshots": int(len(data)),
        "all_drives_failed": True,
        "validation": "leave-one-serial-out; score C-index within each held-out drive",
        "per_drive_c_index": drive_scores,
        "macro_mean_c_index": float(scores.mean()),
        "between_drive_sd": float(scores.std(ddof=1)),
        "between_drive_range": [float(scores.min()), float(scores.max())],
        "cluster_bootstrap_95_percentile_interval": [float(low), float(high)],
        "bootstrap_unit": "whole HDD; resampling the five per-drive scores",
        "bootstrap_iterations": args.bootstraps,
        "seed": args.seed,
        "train_test_serial_overlap_each_fold": 0,
        "leakage_checks": {
            "whole_serials_held_out": True,
            "failure_date_and_identifiers_excluded_from_predictors": True,
            "preprocessor_fit_scope": "training HDDs only within each fold",
            "test_accessed_only_by_transform_and_prediction": True,
        },
        "limitations": ["only five HDDs", "all HDDs failed; no censored/non-failed controls",
                        "interval is exploratory and cannot establish population performance"],
    }
    joblib.dump(artifacts, args.output_dir / "cox_leave_one_drive_out.joblib")
    (args.output_dir / "baseline_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
