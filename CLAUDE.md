# forecast-energy-demand

TCC (undergraduate thesis) — UFRJ / Escola Politécnica
Author: Matheus Hoffmann Fernandes Santos (hoffmann@poli.ufrj.br)
Advisor: Claudio Miceli de Farias, Dr.

## What this project does

Systematic comparison of **10 time-series forecasting algorithms** applied to
hourly electricity demand forecasting across PJM Interconnection regions (USA).
Evaluates the incremental gain of adding **temperature as an exogenous covariate**
for each algorithm family.

The thesis goal is to position results against published benchmarks:
- GEFCom2014 competition: MAPE 2.6–4.1% (reference for the domain)
- Costa (2024) / Pessoa (2023): prior Poli UFRJ theses using ARIMA and Holt-Winters

## Tech stack

| Purpose | Tool |
|---|---|
| Package / venv management | uv |
| Task runner | just |
| Forecasting — statistical | StatsForecast (Nixtla) |
| Forecasting — ML with lags | MLForecast (Nixtla) |
| Forecasting — deep learning | Darts (Unit8) + NeuralForecast (Nixtla) |
| Forecasting — foundation model | TimeGPT via Nixtla SDK |
| Federated learning experiment | Flower (flwr) |
| Experiment tracking | MLflow |
| Data format | Parquet / CSV via pandas |

## Algorithms (10 total)

| # | Algorithm | Family | Library | Exogenous (temperature) |
|---|---|---|---|---|
| 1 | SeasonalNaive | Baseline | StatsForecast | No |
| 2 | AutoARIMA | Statistical | StatsForecast | Yes (ARIMAX) |
| 3 | AutoETS | Statistical | StatsForecast | No |
| 4 | LSTM | Deep Learning | Darts | Yes (past covariates) |
| 5 | TFT | Deep Learning | Darts | Yes (future covariates) |
| 6 | LightGBM (lags) | ML | MLForecast | Yes (feature column) |
| 7 | XGBoost (lags) | ML | MLForecast | Yes (feature column) |
| 8 | N-HiTS | Deep Learning | NeuralForecast | Yes |
| 9 | PatchTST | Deep Learning | NeuralForecast | Yes |
| 10 | TimeGPT-1 | Foundation Model | Nixtla SDK | Yes |

Plus one **ablation experiment**: Fed-LSTM (FedProx via Flower) vs centralised LSTM —
measures the accuracy cost of federated privacy preservation across PJM regions.

## Dataset

- **Source**: PJM Hourly Energy Consumption (Kaggle: `robikscube/hourly-energy-consumption`)
- **Mirror**: `panambY/Hourly_Energy_Consumption` on GitHub (no auth required)
- **Period**: 2022–2024 (3 years, hourly)
- **Regions**: top 10 by total volume (COMED, DAYTON, PJME, EKPC, FE, NI, ...)
- **Exogenous**: temperature (°C) per region via OpenMeteo API (free, no key)
- **Location**: `data/raw/*.csv` — gitignored, download with `just download`

## Data format (Nixtla long format)

All models expect a DataFrame with these columns:

```python
# Required
unique_id  # str  — region name, e.g. "COMED"
ds         # datetime64 — hourly timestamp
y          # float — load in MW

# Optional (when using exogenous)
temperature  # float — degrees Celsius
```

`load_pjm(path, cfg)` in `baseline.py` handles both:
- A **directory** of `*_hourly.csv` files → auto-concatenates all regions
- A **single CSV/Parquet** with wide format (Datetime, COMED_MW, DAYTON_MW, ...)

## Evaluation protocol

**Walk-forward cross-validation (sliding window)**:
- Training window: 672 hours (4 weeks)
- Forecast horizon: 168 hours (1 week)
- Step size: 168 hours
- Each algorithm is evaluated **twice**: without and with temperature

**Metrics** (computed in `compute_metrics()`):
- RMSE — primary metric, used for ranking
- MAE — secondary
- sMAPE — for comparison with GEFCom2014 benchmarks (reported in MAPE %)

All results are logged to MLflow. Start the server with `just mlflow-server`.

## Project structure

```
forecast-energy-demand/
├── baseline.py          # SeasonalNaive — first model, reference implementation
├── download_pjm.py      # Download PJM CSVs (Kaggle API or GitHub mirror)
├── pyproject.toml       # Dependencies (uv)
├── justfile             # Task runner
├── CLAUDE.md            # This file
├── data/
│   └── raw/             # Downloaded CSVs — gitignored
│       ├── COMED_hourly.csv
│       └── ...
├── results/             # Output CSVs per model — gitignored
└── mlruns/              # MLflow tracking data — gitignored
```

Future scripts will follow the same pattern as `baseline.py`:
- Same `Config` dataclass
- Same `walk_forward_splits()` function
- Same `compute_metrics()` function
- Same MLflow logging structure
- Named `{model_name}.py`, e.g. `autoarima.py`, `lstm.py`, `timegpt.py`

## Key design decisions

**Single-script per model**: each algorithm lives in its own `{model}.py` file.
They share utility functions via direct import from `baseline.py` or a future
`utils.py`. No complex class hierarchy — keep it readable for a thesis codebase.

**No serving**: the project ends at evaluation (MLflow). No FastAPI, no deployment.

**Temperature as the only exogenous variable**: the thesis specifically studies
the incremental gain of temperature (°C). Precipitation was considered but
literature (Correa et al. 2023) shows it adds little beyond what temperature
already captures in energy load.

**TimeGPT cost**: ~1.4M tokens for the full walk-forward experiment.
New accounts get $1,000 USD in free credits — sufficient for the entire TCC.
Use `finetune_steps=0` (zero-shot) for initial runs to minimise token use.

## Common commands

```bash
just install          # uv sync — create .venv
just download         # fetch PJM CSVs (no auth needed)
just baseline         # run SeasonalNaive on downloaded data
just mlflow-server    # start MLflow UI at http://localhost:5000
just repomix          # pack repo into a single file for AI context
just check            # ruff lint + pyright typecheck
just clean-results    # wipe mlruns/ and results/
```

## Environment variables

```bash
KAGGLE_USERNAME=...   # optional — enables Kaggle strategy in download_pjm.py
KAGGLE_KEY=...        # optional — from kaggle.com/settings → API
NIXTLA_API_KEY=...    # required for TimeGPT — from nixtla.io dashboard
MLFLOW_TRACKING_URI=http://localhost:5000  # default, override if needed
```

## MLflow experiment structure

- Experiment name: `energy-forecast`
- Run name: `{ModelName}_s{season_length}` for statistical, `{ModelName}` for others
- Logged params: model name, horizon, train window, max regions, key hyperparams
- Logged metrics: per-region RMSE/MAE/sMAPE per fold + aggregated averages
- Logged artifacts: `results/{model}_results.csv`

## Benchmarks to beat

| Study | Algorithm | MAPE | Notes |
|---|---|---|---|
| GEFCom2014 top teams | Ensemble | 2.6–4.1% | Gold standard for the domain |
| Costa (2024) Poli UFRJ | Holt-Winters / ARIMA | ~5–8% est. | Prior Poli thesis |
| Pessoa (2023) Poli UFRJ | Box-Jenkins | ~5–8% est. | Prior Poli thesis |
| Gramm AI (2025) | PatchTST | ~3–4% | Same PJM grids, recent benchmark |

The thesis aims to show that modern ML/DL frameworks (LightGBM, TFT, PatchTST,
TimeGPT) outperform the statistical baselines from prior Poli theses, and that
temperature covariates provide measurable gain for statistical models but less
so for tree-based models (which absorb the effect via lag features).