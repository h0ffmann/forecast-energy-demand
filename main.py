"""
baseline.py — TCC Energy Load Forecasting
Baseline: SeasonalNaive with walk-forward cross-validation and MLflow tracking.

Usage:
    uv run baseline.py                          # uses synthetic data
    uv run baseline.py --data data/pjm.parquet  # uses real PJM data
    uv run baseline.py --help
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import mlflow
import numpy as np
import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import SeasonalNaive

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Experiment parameters."""

    data_path: Path | None = None

    # PJM regions to use (None = all available, up to max_regions)
    regions: list[str] | None = None
    max_regions: int = 10

    # Forecast horizon and training window in hours
    horizon_h: int = 168          # 1 week
    train_window_h: int = 4 * 7 * 24  # 4 weeks

    # Seasonality: 168 = weekly (24h × 7)
    season_length: int = 168

    # MLflow
    mlflow_uri: str = "http://localhost:5000"
    experiment_name: str = "energy-forecast"

    # Random seed for synthetic data
    random_seed: int = 42

    # Expected column names in input DataFrame (Nixtla format)
    col_id: str = "unique_id"
    col_ds: str = "ds"
    col_y: str = "y"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Metrics(NamedTuple):
    rmse: float
    mae: float
    smape: float


@dataclass
class FoldResult:
    fold: int
    region: str
    metrics_no_exog: Metrics
    n_train: int
    n_test: int


@dataclass
class ExperimentResult:
    model_name: str
    config: Config
    fold_results: list[FoldResult] = field(default_factory=list)

    def summary(self) -> pd.DataFrame:
        """Return a DataFrame with metrics per fold and region."""
        rows = [
            {
                "fold": r.fold,
                "region": r.region,
                "rmse": r.metrics_no_exog.rmse,
                "mae": r.metrics_no_exog.mae,
                "smape": r.metrics_no_exog.smape,
                "n_train": r.n_train,
                "n_test": r.n_test,
            }
            for r in self.fold_results
        ]
        return pd.DataFrame(rows)

    def aggregate(self) -> Metrics:
        """Aggregate metrics as a simple mean across all folds and regions."""
        df = self.summary()
        return Metrics(
            rmse=float(df["rmse"].mean()),
            mae=float(df["mae"].mean()),
            smape=float(df["smape"].mean()),
        )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Metrics:
    """Compute RMSE, MAE and sMAPE."""
    if len(y_true) == 0 or len(y_pred) == 0:
        raise ValueError("Arrays vazios passados para compute_metrics")

    residuals = y_true - y_pred
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    mae = float(np.mean(np.abs(residuals)))

    denom = (np.abs(y_true) + np.abs(y_pred)) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        smape_vals = np.where(denom == 0, 0.0, np.abs(residuals) / denom)
    smape = float(np.mean(smape_vals) * 100)

    return Metrics(rmse=rmse, mae=mae, smape=smape)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_pjm(path: Path, cfg: Config) -> pd.DataFrame:
    """
    Load PJM data and convert to Nixtla long format (unique_id, ds, y).

    Accepts two layouts produced by download_pjm.py:

    A) Directory of per-region files (download_pjm.py default output):
         data/raw/COMED_hourly.csv   → columns: Datetime, COMED_MW
         data/raw/DAYTON_hourly.csv  → columns: Datetime, DAYTON_MW
         Pass --data data/raw

    B) Single wide CSV (all regions as columns):
         Datetime, COMED_MW, DAYTON_MW, ...
         Pass --data pjm_all.csv

    C) Single Parquet file (any of the above, pre-processed).
    """
    if path.is_dir():
        return _load_pjm_directory(path, cfg)

    log.info("Loading PJM data from %s", path)
    if path.suffix == ".parquet":
        raw = pd.read_parquet(path)
    else:
        raw = pd.read_csv(path)

    return _parse_pjm_wide(raw, cfg)


def _load_pjm_directory(directory: Path, cfg: Config) -> pd.DataFrame:
    """
    Load all *_hourly.csv files from a directory and concatenate them.

    Each file has columns: Datetime, {REGION}_MW
    """
    csv_files = sorted(directory.glob("*_hourly.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No *_hourly.csv files found in {directory}. "
            "Run download_pjm.py first."
        )

    log.info("Loading %d region file(s) from %s", len(csv_files), directory)
    frames: list[pd.DataFrame] = []

    for f in csv_files:
        raw = pd.read_csv(f)
        # Derive region name from filename: COMED_hourly.csv → COMED
        region = f.stem.replace("_hourly", "")
        mw_col = next(
            (c for c in raw.columns if c.upper().endswith("_MW")), None
        )
        date_col = next(
            (c for c in raw.columns if c.lower() in {"datetime", "ds", "date"}), None
        )
        if mw_col is None or date_col is None:
            log.warning("Skipping %s — expected Datetime and *_MW columns", f.name)
            continue

        chunk = pd.DataFrame({
            "unique_id": region,
            "ds": pd.to_datetime(raw[date_col]),
            "y": pd.to_numeric(raw[mw_col], errors="coerce"),
        })
        frames.append(chunk)
        log.info("  Loaded: %s  (%d rows)", f.name, len(chunk))

    if not frames:
        raise ValueError("No valid region files could be parsed.")

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["y"]).sort_values(["unique_id", "ds"])
    return _select_regions(combined, cfg)


def _parse_pjm_wide(raw: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Parse a wide CSV where each region is a column (e.g., COMED_MW, DAYTON_MW)."""
    date_col = next(
        (c for c in raw.columns if c.lower() in {"datetime", "ds", "date"}), None
    )
    if date_col is None:
        raise ValueError(f"Date column not found. Columns: {list(raw.columns)}")

    raw = raw.rename(columns={date_col: "ds"})
    raw["ds"] = pd.to_datetime(raw["ds"])

    mw_cols = [c for c in raw.columns if c.upper().endswith("_MW")]
    if not mw_cols:
        raise ValueError("No *_MW columns found in file.")

    long = raw.melt(id_vars="ds", value_vars=mw_cols, var_name="unique_id", value_name="y")
    long["unique_id"] = long["unique_id"].str.replace("_MW", "", case=False, regex=False)
    long = long.dropna(subset=["y"]).sort_values(["unique_id", "ds"])
    return _select_regions(long, cfg)


def _select_regions(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Select regions according to configuration."""
    if cfg.regions:
        available = set(df["unique_id"].unique())
        missing = set(cfg.regions) - available
        if missing:
            log.warning("Regions not found in data: %s", missing)
        df = df[df["unique_id"].isin(cfg.regions)]
    else:
        # Top N by total volume
        top = (
            df.groupby("unique_id")["y"]
            .sum()
            .nlargest(cfg.max_regions)
            .index.tolist()
        )
        df = df[df["unique_id"].isin(top)]
        log.info("Selected regions (top %d by volume): %s", cfg.max_regions, top)

    return df.reset_index(drop=True)


def generate_synthetic(cfg: Config) -> pd.DataFrame:
    """
    Generate synthetic hourly electricity consumption series for testing.

    Includes:
    - Daily seasonality (peak around 18h)
    - Weekly seasonality (lower on weekends)
    - Mild linear trend
    - Gaussian noise
    """
    rng = np.random.default_rng(cfg.random_seed)
    n_hours = cfg.train_window_h + cfg.horizon_h * 4  # train window + 4 test folds

    regions = ["COMED", "DAYTON", "EKPC"]
    records: list[dict] = []

    start = pd.Timestamp("2022-01-01")
    dates = pd.date_range(start, periods=n_hours, freq="h")

    for region in regions:
        base_load = rng.uniform(3_000, 15_000)
        for i, dt in enumerate(dates):
            hour_effect = np.sin((dt.hour - 6) * np.pi / 12) * 0.2 * base_load
            day_effect = -0.1 * base_load if dt.dayofweek >= 5 else 0.0
            trend = i * 0.5
            noise = rng.normal(0, base_load * 0.03)
            y = max(0.0, base_load + hour_effect + day_effect + trend + noise)
            records.append({"unique_id": region, "ds": dt, "y": y})

    df = pd.DataFrame(records)
    log.info(
        "Synthetic data generated: %d regions × %d hours = %d records",
        len(regions), n_hours, len(df),
    )
    return df


# ---------------------------------------------------------------------------
# Walk-forward split
# ---------------------------------------------------------------------------

def walk_forward_splits(
    df: pd.DataFrame,
    region: str,
    train_h: int,
    horizon_h: int,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """
    Generate walk-forward (sliding window) folds for a single region.

    Each fold:
        train: window of train_h hours
        test:  window of horizon_h hours immediately after train

    Returns a list of (df_train, df_test) tuples.
    """
    region_df = df[df["unique_id"] == region].sort_values("ds").reset_index(drop=True)
    total = len(region_df)
    step = horizon_h  # slide forward by horizon_h each fold
    folds: list[tuple[pd.DataFrame, pd.DataFrame]] = []

    start = 0
    while start + train_h + horizon_h <= total:
        train = region_df.iloc[start : start + train_h]
        test = region_df.iloc[start + train_h : start + train_h + horizon_h]
        folds.append((train, test))
        start += step

    log.debug("Region %s: %d folds generated", region, len(folds))
    return folds


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def run_seasonal_naive(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    season_length: int,
    horizon_h: int,
) -> np.ndarray:
    """
    Fit SeasonalNaive and return forecasts for the horizon.

    SeasonalNaive repeats the last observed seasonal cycle.
    With season_length=168 it repeats exactly the previous week.
    """
    sf = StatsForecast(
        models=[SeasonalNaive(season_length=season_length)],
        freq="h",
        n_jobs=1,
        verbose=False,
    )
    sf.fit(df_train[["unique_id", "ds", "y"]])
    forecast = sf.predict(h=horizon_h)

    region = df_train["unique_id"].iloc[0]
    preds = forecast[forecast["unique_id"] == region]["SeasonalNaive"].values
    return preds


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_experiment(cfg: Config) -> ExperimentResult:
    """
    Run the baseline experiment (SeasonalNaive) with walk-forward CV.

    For each region and each fold:
    1. Fit SeasonalNaive on the training window
    2. Forecast the test horizon
    3. Compute RMSE, MAE, sMAPE
    4. Log metrics to MLflow
    """
    # Load data
    if cfg.data_path and cfg.data_path.exists():
        df = load_pjm(cfg.data_path, cfg)
    else:
        if cfg.data_path:
            log.warning("File %s not found — using synthetic data", cfg.data_path)
        else:
            log.info("No file specified — using synthetic data")
        df = generate_synthetic(cfg)

    regions = df["unique_id"].unique().tolist()
    log.info("Regions: %s", regions)

    model_name = f"SeasonalNaive_s{cfg.season_length}"
    result = ExperimentResult(model_name=model_name, config=cfg)

    # Configure MLflow
    _setup_mlflow(cfg)

    with mlflow.start_run(run_name=model_name) as run:
        _log_params(cfg, model_name)

        all_fold_results: list[FoldResult] = []

        for region in regions:
            log.info("Processing region: %s", region)

            folds = walk_forward_splits(
                df, region, cfg.train_window_h, cfg.horizon_h
            )

            if not folds:
                log.warning("Region %s: not enough data for any fold — skipping", region)
                continue

            for fold_idx, (train, test) in enumerate(folds):
                preds = run_seasonal_naive(
                    train, test, cfg.season_length, cfg.horizon_h
                )
                y_true = test["y"].values
                n_preds = min(len(y_true), len(preds))
                metrics = compute_metrics(y_true[:n_preds], preds[:n_preds])

                fold_result = FoldResult(
                    fold=fold_idx,
                    region=region,
                    metrics_no_exog=metrics,
                    n_train=len(train),
                    n_test=len(test),
                )
                all_fold_results.append(fold_result)

                log.info(
                    "  fold %02d | RMSE=%.1f  MAE=%.1f  sMAPE=%.2f%%",
                    fold_idx,
                    metrics.rmse,
                    metrics.mae,
                    metrics.smape,
                )

                # Log per-fold metrics to MLflow
                step = fold_idx * len(regions) + regions.index(region)
                mlflow.log_metrics(
                    {
                        f"{region}/rmse": metrics.rmse,
                        f"{region}/mae": metrics.mae,
                        f"{region}/smape": metrics.smape,
                    },
                    step=step,
                )

        result.fold_results = all_fold_results

        # Aggregated metrics
        agg = result.aggregate()
        log.info(
            "\nFINAL RESULT — %s\n"
            "  mean RMSE : %.2f\n"
            "  mean MAE  : %.2f\n"
            "  mean sMAPE: %.2f%%",
            model_name, agg.rmse, agg.mae, agg.smape,
        )

        mlflow.log_metrics({
            "agg/rmse": agg.rmse,
            "agg/mae": agg.mae,
            "agg/smape": agg.smape,
        })

        # Save results CSV as MLflow artifact
        summary_df = result.summary()
        summary_path = Path("results") / f"{model_name}_results.csv"
        summary_path.parent.mkdir(exist_ok=True)
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))
        log.info("Results saved to %s", summary_path)
        log.info("MLflow run id: %s", run.info.run_id)

    return result


# ---------------------------------------------------------------------------
# MLflow helpers
# ---------------------------------------------------------------------------

def _setup_mlflow(cfg: Config) -> None:
    """Set tracking URI and create experiment if it does not exist."""
    mlflow.set_tracking_uri(cfg.mlflow_uri)
    mlflow.set_experiment(cfg.experiment_name)


def _log_params(cfg: Config, model_name: str) -> None:
    mlflow.log_params({
        "model": model_name,
        "season_length": cfg.season_length,
        "horizon_h": cfg.horizon_h,
        "train_window_h": cfg.train_window_h,
        "max_regions": cfg.max_regions,
    })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="SeasonalNaive baseline — TCC Energy Load Forecasting"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Path to PJM CSV or Parquet file (omit for synthetic data)",
    )
    parser.add_argument(
        "--regions",
        nargs="+",
        default=None,
        help="Specific regions (e.g. COMED DAYTON). Default: top 10 by volume.",
    )
    parser.add_argument(
        "--max-regions",
        type=int,
        default=10,
        help="Maximum number of regions (default: 10)",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=168,
        help="Forecast horizon in hours (default: 168 = 1 week)",
    )
    parser.add_argument(
        "--train-window",
        type=int,
        default=4 * 7 * 24,
        help="Training window in hours (default: 672 = 4 weeks)",
    )
    parser.add_argument(
        "--season-length",
        type=int,
        default=168,
        help="Seasonality length (default: 168 = weekly)",
    )
    parser.add_argument(
        "--mlflow-uri",
        type=str,
        default="http://localhost:5000",
        help="MLflow tracking server URI (default: http://localhost:5000)",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default="energy-forecast",
        help="MLflow experiment name",
    )

    args = parser.parse_args()
    return Config(
        data_path=args.data,
        regions=args.regions,
        max_regions=args.max_regions,
        horizon_h=args.horizon,
        train_window_h=args.train_window,
        season_length=args.season_length,
        mlflow_uri=args.mlflow_uri,
        experiment_name=args.experiment,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = parse_args()
    result = run_experiment(cfg)
    agg = result.aggregate()
    print(f"\n{'='*50}")
    print(f"  {result.model_name}")
    print(f"  RMSE  : {agg.rmse:.2f} MW")
    print(f"  MAE   : {agg.mae:.2f} MW")
    print(f"  sMAPE : {agg.smape:.2f}%")
    print(f"{'='*50}")