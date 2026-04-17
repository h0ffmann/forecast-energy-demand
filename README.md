# forecast-energy-demand

Undergraduate thesis (TCC) — UFRJ / Escola Politécnica  
Systematic comparison of 10 time-series forecasting algorithms applied to hourly electricity demand across PJM Interconnection regions.

## What it does

Trains and evaluates 10 models under an identical walk-forward cross-validation protocol, each run twice — without and with weather covariates — to isolate the incremental gain of exogenous variables per algorithm family. Results are benchmarked against GEFCom2014 (MAPE 2.6–4.1%).

## Algorithms

| # | Model | Family | Exogenous |
|---|-------|--------|-----------|
| 1 | SeasonalNaive | Baseline | — |
| 2 | AutoARIMA | Statistical | ARIMAX |
| 3 | AutoETS | Statistical | — |
| 4 | LSTM | Deep learning | past covariates |
| 5 | TFT | Deep learning | future covariates |
| 6 | LightGBM | ML | lag features |
| 7 | XGBoost | ML | lag features |
| 8 | N-HiTS | Neural | yes |
| 9 | PatchTST | Neural | yes |
| 10 | TimeGPT-1 | Foundation | zero-shot + fine-tune |

Plus one ablation: **Fed-LSTM** (Flower/FedProx) vs centralised LSTM.

## Data

- **Load**: PJM Hourly Energy Consumption — 12 regions, hourly MW  
  Mirror: `github.com/panambY/Hourly_Energy_Consumption` (no auth required)
- **Weather**: OpenMeteo historical + forecast API (free, no key)  
  Variables: `temperature_2m`, `apparent_temperature`, `relative_humidity_2m`, `wind_speed_10m`, `shortwave_radiation`, `cloud_cover`
- **Period**: 2015–2018 (Kaggle dataset) or 2022–2024 via PJM Data Miner 2 — see `DATA-001` in `issues.json`

## Evaluation protocol

```
training window : 672 h (4 weeks, sliding)
forecast horizon: 168 h (1 week)
step size       : 168 h
metrics         : RMSE (primary), MAE, sMAPE
tracking        : MLflow
```

## Stack

| Layer | Tool |
|-------|------|
| Package management | uv workspaces |
| Orchestration | Prefect 3 |
| Statistical models | StatsForecast |
| ML models | MLForecast + LightGBM/XGBoost |
| Deep learning | Darts + NeuralForecast |
| Foundation model | Nixtla SDK (TimeGPT) |
| Federated learning | Flower (flwr) |
| Experiment tracking | MLflow |

## Quickstart

```bash
# install all packages
uv sync

# download PJM load data (no credentials needed)
just download

# run baseline
just baseline

# start MLflow UI
just mlflow-server       # → http://localhost:5000

# run a single model
just train seasonal-naive
just train lightgbm

# run all models (takes a while)
just train-all
```

## Environment variables

```bash
NIXTLA_API_KEY=...            # required for TimeGPT
KAGGLE_USERNAME=...           # optional — enables Kaggle download path
KAGGLE_KEY=...                # optional
MLFLOW_TRACKING_URI=http://localhost:5000
```

## Project layout

```
forecast-energy-demand/
├── packages/
│   ├── core/           # pure functions: metrics, cv, evaluation, types
│   ├── data/           # loaders, OpenMeteo client, feature engineering
│   ├── models/
│   │   ├── statistical/
│   │   ├── ml/
│   │   ├── deep/
│   │   ├── neural/
│   │   └── foundation/
│   ├── pipeline/       # Prefect flows + model registry
│   └── tracking/       # MLflow adapter
├── docs/               # LaTeX thesis (PT-BR + EN-US via CI)
├── issues.json         # task backlog with interface-first ordering
├── main.py             # SeasonalNaive baseline (reference implementation)
└── pyproject.toml      # uv workspace root
```

## Thesis

PDF built automatically on push to `main` via GitHub Actions (Tectonic + GitHub Models translation PT-BR → EN-US). Latest build available under **Actions → Build Thesis PDFs**.

---

UFRJ / Escola Politécnica — Electronic and Computer Engineering  
Author: Matheus Hoffmann Fernandes Santos · Advisor: Claudio Miceli de Farias, Dr.