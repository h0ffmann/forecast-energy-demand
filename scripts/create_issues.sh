#!/bin/bash
set -e

REPO="h0ffmann/forecast-energy-demand"

echo "🏷️  Creating labels..."
for label in "data-research:0075ca" "interface:e4e669" "infra:d93f0b" "implementation:0e8a16" "docs:fef2c0" "p0:b60205" "p1:d93f0b" "p2:e4e669" "p3:0075ca"; do
  name="${label%%:*}"
  color="${label##*:}"
  gh label create "$name" --color "$color" --repo "$REPO" 2>/dev/null || true
done

echo "✅ Labels ready."
echo ""
echo "📋 Creating issues..."

# ────────────────────────────────────────────────
# DATA-001
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[DATA-001] Characterise PJM dataset: regions, date coverage, DST handling, gap analysis" \
  --label "data-research,p0" \
  --body "## Type
\`data-research\` | Priority: \`p0\`

## Depends on
_none_

## Description
Before writing any loader, document the exact shape of each region file. The dataset has critical edge cases:
1. EST timestamps with no DST — one hour is repeated each November fall-back, which will break hourly frequency validation.
2. Regions have different start dates.
3. Some regions were reorganised mid-period (DEOK starts 2012).

This task produces a characterisation JSON consumed by IFACE-004 and IFACE-010.

## ⚠️ Critical Finding
The Kaggle/GitHub dataset covers **2001–2018**. The thesis proposes **2022–2024**. These do NOT overlap.
Must decide before any other data work:
- (a) Use PJM Data Miner 2 API (\`pjm.com/markets-and-operations/etools/data-miner-2\`) for recent data
- (b) Revise thesis scope to 2015–2018

## Scope
- **Touch:** \`docs/data/pjm_characterisation.md\`
- **Read-only:** all CSV files in \`data/raw/\`
- **Do not touch:** any \`src/\` or \`packages/\` file

## Findings to Document
- Per-region: first timestamp, last timestamp, total rows, null count, min/max MW
- DST fall-back duplicate rows: which years, which hours, how to deduplicate (keep first)
- Structural breaks: DEOK (2012), any others
- Recommended train period for thesis scope
- Centroid coordinates per region for OpenMeteo fetch (REGION_COORDINATES dict)

## Acceptance Criteria
- [ ] \`docs/data/pjm_characterisation.md\` committed
- [ ] Data source decision documented (Data Miner 2 vs revised scope)
- [ ] DST deduplication strategy decided
- [ ] \`REGION_COORDINATES\` dict with lat/lon for all 12 regions drafted"

echo "✔ DATA-001"

# ────────────────────────────────────────────────
# IFACE-001
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-001] Define ExogConfig dataclass" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #DATA-001

## File
\`packages/core/src/core/types.py\`

## Description
Single source of truth for exogenous variable configuration. Column names must match exactly the feature names defined in the feature catalog. ExogConfig is constructed by the pipeline per-model; \`build_features()\` uses it to decide which columns to compute.

## Interface
\`\`\`python
@dataclass(frozen=True)
class ExogConfig:
    enabled: bool = False
    past_columns: tuple[str, ...] = ()
    future_known_columns: tuple[str, ...] = ()
    graph_edges: tuple[tuple[str, str], ...] | None = None

# Pre-built named configs
EXOG_NONE = ExogConfig()  # SeasonalNaive, AutoETS

EXOG_TIER1 = ExogConfig(
    enabled=True,
    past_columns=('temperature_2m', 'apparent_temperature', 'relative_humidity_2m', 'wind_speed_10m'),
    future_known_columns=('temperature_2m', 'apparent_temperature', 'relative_humidity_2m', 'wind_speed_10m'),
)

EXOG_TIER1_DERIVED = ExogConfig(
    enabled=True,
    past_columns=(
        'temperature_2m', 'apparent_temperature', 'relative_humidity_2m', 'wind_speed_10m',
        'temperature_2m_sq', 'hdd', 'cdd', 'cold_wind', 'hot_wind',
        'shortwave_radiation', 'cloud_cover',
    ),
    future_known_columns=(
        'temperature_2m', 'apparent_temperature', 'relative_humidity_2m', 'wind_speed_10m',
        'temperature_2m_sq', 'hdd', 'cdd', 'cold_wind', 'hot_wind',
        'shortwave_radiation', 'cloud_cover',
    ),
)
\`\`\`

## Acceptance Criteria
- [ ] Immutable frozen dataclass
- [ ] \`EXOG_NONE\`, \`EXOG_TIER1\`, \`EXOG_TIER1_DERIVED\` exported from \`core.types\`
- [ ] \`to_dict()\` method for MLflow param logging
- [ ] All column names match feature_catalog keys exactly"

echo "✔ IFACE-001"

# ────────────────────────────────────────────────
# IFACE-002
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-002] Define Forecaster Protocol" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #IFACE-001
- #IFACE-003

## File
\`packages/core/src/core/protocols.py\`

## Description
Structural subtyping contract (\`typing.Protocol\`) that all 10 model implementations must satisfy.

## Interface
\`\`\`python
@runtime_checkable
class Forecaster(Protocol):
    name: ClassVar[str]
    supports_exog: ClassVar[bool]
    def fit(self, train: pd.DataFrame, exog: ExogConfig) -> Self: ...
    def predict(self, horizon: int, future_exog: pd.DataFrame | None = None) -> np.ndarray: ...
\`\`\`

## Acceptance Criteria
- [ ] \`@runtime_checkable\` applied
- [ ] \`fit()\` returns \`Self\`
- [ ] \`predict()\` returns \`np.ndarray\` of shape \`(horizon,)\`"

echo "✔ IFACE-002"

# ────────────────────────────────────────────────
# IFACE-003
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-003] Define shared result types: Metrics, FoldResult, ExperimentResult" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
_none_

## File
\`packages/core/src/core/types.py\`

## Description
Migrate and extend the three result types from \`main.py\`. \`FoldResult\` now carries \`exog_config_name\` so the incremental gain of each ExogConfig tier can be computed from a single \`ExperimentResult\`.

## Interface
\`\`\`python
class Metrics(NamedTuple):
    rmse: float
    mae: float
    smape: float

@dataclass(frozen=True)
class FoldResult:
    fold: int
    region: str
    model_name: str
    exog_config_name: str   # 'EXOG_NONE' | 'EXOG_TIER1' | 'EXOG_TIER1_DERIVED'
    metrics: Metrics
    n_train: int
    n_test: int

@dataclass(frozen=True)
class ExperimentResult:
    model_name: str
    exog_config: ExogConfig
    fold_results: tuple[FoldResult, ...]
    def summary(self) -> pd.DataFrame: ...
    def aggregate(self) -> Metrics: ...
\`\`\`

## Acceptance Criteria
- [ ] All types frozen and immutable
- [ ] Exported from \`core.__init__\`
- [ ] \`ExperimentResult.aggregate()\` is pure — no side effects"

echo "✔ IFACE-003"

# ────────────────────────────────────────────────
# IFACE-004
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-004] Define DatasetSchema and validate_dataset" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #IFACE-001
- #DATA-001

## File
\`packages/core/src/core/schema.py\`

## Description
Formal validation of the DataFrame that flows through the entire pipeline. DST deduplication strategy from DATA-001 is encoded here.

## Interface
\`\`\`python
REQUIRED_COLS: frozenset[str] = frozenset({'unique_id', 'ds', 'y'})

def validate_dataset(
    df: pd.DataFrame,
    exog: ExogConfig,
    freq: str = 'h',
    allow_dst_duplicates: bool = False,
) -> pd.DataFrame:
    \"\"\"
    Pure. Raises ValueError with column name on any violation:
      - missing required columns
      - exog columns declared but not present
      - ds is not datetime64[ns, UTC] or naive EST
      - y contains NaN
      - frequency does not match freq (after DST dedup if allow_dst_duplicates=False)
    Returns unchanged DataFrame on success.
    \"\"\"
\`\`\`

## Acceptance Criteria
- [ ] Pure — zero side effects
- [ ] DST duplicate detection raises \`ValueError\` when \`allow_dst_duplicates=False\`
- [ ] Called at loader output and at pipeline cv_split entry"

echo "✔ IFACE-004"

# ────────────────────────────────────────────────
# IFACE-005
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-005] Define ModelConfig and PipelineConfig" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #IFACE-001

## File
\`packages/core/src/core/config.py\`

## Description
Replace the monolithic \`Config\` dataclass. \`PipelineConfig.from_yaml()\` reads \`params.yaml\` (DVC-compatible). Adds \`exog_configs\` list so a single pipeline run sweeps multiple ExogConfig conditions automatically.

## Interface
\`\`\`python
@dataclass(frozen=True)
class ModelConfig:
    name: str
    hyperparams: dict[str, Any]
    finetune_steps: int = 0

@dataclass(frozen=True)
class PipelineConfig:
    horizon_h: int = 168
    train_window_h: int = 672
    step_h: int = 168
    regions: tuple[str, ...] | None = None
    max_regions: int = 10
    random_seed: int = 42
    mlflow_experiment: str = 'energy-forecast'
    exog_configs: tuple[str, ...] = ('EXOG_NONE', 'EXOG_TIER1')
    @classmethod
    def from_yaml(cls, path: Path) -> 'PipelineConfig': ...
\`\`\`

## Acceptance Criteria
- [ ] Both frozen
- [ ] \`PipelineConfig.from_yaml()\` parses a \`params.yaml\`
- [ ] \`exog_configs\` names resolved via \`EXOG_REGISTRY\` dict in \`core.types\`"

echo "✔ IFACE-005"

# ────────────────────────────────────────────────
# IFACE-006
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-006] Define walk_forward_splits function signature" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #IFACE-004
- #IFACE-005

## File
\`packages/core/src/core/cross_validation.py\`

## Description
Pure generator-based walk-forward splitter. Exogenous columns pass through in both train and test DataFrames. For \`future_known_columns\`, the test DataFrame includes ground-truth weather values (simulating a perfect weather forecast — OpenMeteo 7-day ahead covers the 168h horizon exactly).

## Interface
\`\`\`python
def walk_forward_splits(
    df: pd.DataFrame,
    region: str,
    cfg: PipelineConfig,
) -> Iterator[tuple[pd.DataFrame, pd.DataFrame]]:
    \"\"\"
    Yields (train, test) for a single region.
    Both DataFrames retain all columns (y + all exog).
    \"\"\"
\`\`\`

## Acceptance Criteria
- [ ] Pure — no side effects
- [ ] Returns \`Iterator\`, not \`list\`
- [ ] Correct non-overlapping fold date ranges"

echo "✔ IFACE-006"

# ────────────────────────────────────────────────
# IFACE-007
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-007] Define compute_metrics and evaluate_model" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #IFACE-003
- #IFACE-006

## File
\`packages/core/src/core/evaluation.py\`

## Interface
\`\`\`python
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Metrics: ...

def evaluate_model(
    model: Forecaster,
    folds: Iterator[tuple[pd.DataFrame, pd.DataFrame]],
    region: str,
    exog: ExogConfig,
) -> tuple[FoldResult, ...]: ...
\`\`\`

## Acceptance Criteria
- [ ] \`compute_metrics\` pure with zero non-numpy imports
- [ ] \`evaluate_model\` does not import mlflow
- [ ] \`evaluate_model\` passes \`future_exog\` to \`model.predict()\` when \`exog.future_known_columns\` is non-empty"

echo "✔ IFACE-007"

# ────────────────────────────────────────────────
# IFACE-008
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-008] Define TrackingAdapter Protocol and NoOpAdapter" \
  --label "interface,p1" \
  --body "## Type
\`interface\` | Priority: \`p1\`

## Depends on
- #IFACE-003
- #IFACE-005

## File
\`packages/tracking/src/tracking/protocols.py\`

## Description
Isolate MLflow behind a Protocol so the core evaluation logic never imports mlflow directly.

## Interface
\`\`\`python
class TrackingAdapter(Protocol):
    def start_run(self, run_name: str) -> AbstractContextManager: ...
    def log_params(self, params: dict[str, Any]) -> None: ...
    def log_metrics(self, metrics: dict[str, float], step: int) -> None: ...
    def log_artifact(self, path: Path) -> None: ...

class NoOpAdapter:
    def start_run(self, run_name): return nullcontext()
    def log_params(self, params): pass
    def log_metrics(self, metrics, step=0): pass
    def log_artifact(self, path): pass
\`\`\`

## Acceptance Criteria
- [ ] \`NoOpAdapter\` passes \`isinstance(x, TrackingAdapter)\` check at runtime
- [ ] No mlflow import in this file"

echo "✔ IFACE-008"

# ────────────────────────────────────────────────
# IFACE-009
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-009] Define build_features signature and FeatureCatalog" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #IFACE-001
- #IFACE-004
- #DATA-001

## File
\`packages/data/src/data/features.py\`

## Description
Single entry point for all feature engineering. Column names and derivation formulas must match the feature catalog exactly. Decomposed into pure sub-functions per tier so each can be tested independently.

## Interface
\`\`\`python
def build_features(
    df: pd.DataFrame,
    exog: ExogConfig,
    add_lag_features: bool = False,
    lag_hours: tuple[int, ...] = (24, 48, 168, 336),
    rolling_windows: tuple[int, ...] = (24, 168),
    holidays_country: str = 'US',
) -> pd.DataFrame: ...

# Sub-functions (exported for testing)
def add_calendar_features(df: pd.DataFrame, holidays_country: str) -> pd.DataFrame: ...
def add_derived_weather_features(df: pd.DataFrame, exog: ExogConfig) -> pd.DataFrame: ...
def add_lag_features(df: pd.DataFrame, lag_hours: tuple[int, ...], rolling_windows: tuple[int, ...]) -> pd.DataFrame: ...
\`\`\`

## Acceptance Criteria
- [ ] All column names match feature_catalog keys exactly
- [ ] Pure — no HTTP, no file I/O
- [ ] Idempotent — calling twice produces the same result
- [ ] Statistical models (\`exog.past_columns == ()\`) receive calendar features only
- [ ] ML models receive lag + rolling + calendar + weather tier-1 + derived tier-2
- [ ] TFT receives \`future_known_columns\` aligned to forecast horizon in test DataFrame"

echo "✔ IFACE-009"

# ────────────────────────────────────────────────
# IFACE-010
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-010] Define OpenMeteo client interface and REGION_COORDINATES" \
  --label "interface,p0" \
  --body "## Type
\`interface\` | Priority: \`p0\`

## Depends on
- #IFACE-001
- #DATA-001

## File
\`packages/data/src/data/openmeteo.py\`

## Description
Contract for fetching historical and forecast weather. Uses archive API for training data and forecast API for \`future_known_columns\`.

## Interface
\`\`\`python
REGION_COORDINATES: dict[str, tuple[float, float]] = {
    'AEP': (40.4, -82.9), 'COMED': (41.8, -87.7), 'DAYTON': (39.8, -84.2),
    'DEOK': (39.1, -84.5), 'DOM': (37.5, -77.4), 'DUQ': (40.4, -80.0),
    'EKPC': (38.2, -84.9), 'FE': (41.1, -81.5), 'NI': (41.8, -87.6),
    'PJME': (39.9, -75.2), 'PJMW': (40.4, -80.0), 'PJM_Load': (39.9, -77.0),
}

OPENMETEO_HOURLY_VARS: tuple[str, ...] = (
    'temperature_2m', 'apparent_temperature', 'relative_humidity_2m',
    'wind_speed_10m', 'shortwave_radiation', 'cloud_cover', 'is_day',
)

def fetch_weather(
    regions: Sequence[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    variables: tuple[str, ...] = OPENMETEO_HOURLY_VARS,
    model: str = 'best_match',
    cache_dir: Path | None = None,
) -> pd.DataFrame: ...
\`\`\`

## Acceptance Criteria
- [ ] Returns DataFrame joinable to \`load_pjm()\` on \`(unique_id, ds)\`
- [ ] Switches between archive API and forecast API based on date range
- [ ] Cache avoids re-fetching on second run
- [ ] Columns match \`OPENMETEO_HOURLY_VARS\` exactly
- [ ] \`REGION_COORDINATES\` covers all 12 PJM regions"

echo "✔ IFACE-010"

# ────────────────────────────────────────────────
# IFACE-011
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-011] Define uv workspace structure and package boundaries" \
  --label "infra,p0" \
  --body "## Type
\`infra\` | Priority: \`p0\`

## Depends on
_none_

## Files
\`pyproject.toml\` + \`packages/*/pyproject.toml\`

## Description
Set up the uv workspace so each package has its own dependency set.

## Package → Dependencies
| Package | Key deps |
|---|---|
| \`core\` | pandas>=2.2, numpy>=1.26, holidays>=0.45 |
| \`data\` | pandas>=2.2, pyarrow>=15, requests>=2.31, openmeteo-requests>=1.2 |
| \`models/statistical\` | statsforecast>=1.7 |
| \`models/ml\` | mlforecast>=0.13, lightgbm>=4.3, xgboost>=2.0 |
| \`models/deep\` | darts>=0.30, torch>=2.2 |
| \`models/neural\` | neuralforecast>=1.7, torch>=2.2 |
| \`models/foundation\` | nixtla>=0.5 (**no torch**) |
| \`pipeline\` | prefect>=3.0 |
| \`tracking\` | mlflow>=2.12 |

## Acceptance Criteria
- [ ] \`uv sync --package models/foundation\` does NOT install torch
- [ ] \`uv sync --package core\` installs in under 5 seconds
- [ ] Each package is importable independently"

echo "✔ IFACE-011"

# ────────────────────────────────────────────────
# IFACE-012
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-012] Define Prefect flow and task signatures" \
  --label "interface,p1" \
  --body "## Type
\`interface\` | Priority: \`p1\`

## Depends on
- #IFACE-005
- #IFACE-006
- #IFACE-007
- #IFACE-008
- #IFACE-011

## File
\`packages/pipeline/src/pipeline/flows.py\`

## Description
Five Prefect \`@task\` signatures. The main flow sweeps \`exog_configs\` so one pipeline run produces both \`EXOG_NONE\` and \`EXOG_TIER1\` results for every model×region pair.

## Interface
\`\`\`python
@task(name='ingest')
def ingest_task(cfg: PipelineConfig) -> pd.DataFrame: ...

@task(name='features')
def features_task(df: pd.DataFrame, exog: ExogConfig, add_lag: bool) -> pd.DataFrame: ...

@task(name='cv_split')
def cv_split_task(df: pd.DataFrame, region: str, cfg: PipelineConfig) -> list[tuple[pd.DataFrame, pd.DataFrame]]: ...

@task(name='train_eval')
def train_eval_task(model_cfg: ModelConfig, folds: list, region: str, exog: ExogConfig) -> tuple[FoldResult, ...]: ...

@task(name='track')
def track_task(results: tuple[FoldResult, ...], adapter: TrackingAdapter) -> None: ...

@flow(name='energy-forecast')
def forecast_flow(pipeline_cfg: PipelineConfig, model_cfg: ModelConfig, adapter: TrackingAdapter | None = None) -> list[ExperimentResult]: ...
\`\`\`

## Acceptance Criteria
- [ ] \`forecast_flow\` sweeps \`exog_configs\` from \`pipeline_cfg.exog_configs\`
- [ ] \`adapter\` defaults to \`NoOpAdapter\` when \`None\`
- [ ] \`features_task\` sets \`add_lag=True\` only for model family \`'ml'\`"

echo "✔ IFACE-012"

# ────────────────────────────────────────────────
# IFACE-013
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IFACE-013] Define model registry and dynamic model resolution" \
  --label "interface,p1" \
  --body "## Type
\`interface\` | Priority: \`p1\`

## Depends on
- #IFACE-002
- #IFACE-005

## File
\`packages/pipeline/src/pipeline/registry.py\`

## Interface
\`\`\`python
ModelFactory = Callable[[dict[str, Any]], Forecaster]
MODEL_REGISTRY: dict[str, ModelFactory] = {}
def register(name: str) -> Callable[[ModelFactory], ModelFactory]: ...
def get_model(name: str, hyperparams: dict[str, Any]) -> Forecaster: ...
\`\`\`

## Acceptance Criteria
- [ ] \`get_model\` raises \`KeyError\` with helpful message for unknown model names
- [ ] \`@register\` decorator works as \`@register('seasonal-naive')\`
- [ ] Registry is populated at import time via each model package's \`__init__.py\`"

echo "✔ IFACE-013"

# ────────────────────────────────────────────────
# IMPL-001
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-001] Implement core package" \
  --label "implementation,p0" \
  --body "## Type
\`implementation\` | Priority: \`p0\`

## Depends on
- #IFACE-001
- #IFACE-002
- #IFACE-003
- #IFACE-004
- #IFACE-005
- #IFACE-006
- #IFACE-007
- #IFACE-011

## Scope
- **Touch:** \`packages/core/src/core/\` (all files)
- **Do not touch:** any other package

## Description
Concrete implementation of all interfaces defined in IFACE-001 through IFACE-007. All logic must be pure — no HTTP, no file I/O, no MLflow imports.

## Acceptance Criteria
- [ ] \`from core import ExogConfig, Metrics, FoldResult, ExperimentResult, PipelineConfig\` works
- [ ] \`validate_dataset\` raises on all documented violations
- [ ] \`walk_forward_splits\` produces non-overlapping folds
- [ ] 100% unit test coverage on \`compute_metrics\`"

echo "✔ IMPL-001"

# ────────────────────────────────────────────────
# IMPL-002
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-002] Implement data package (PJM loader, OpenMeteo client, feature engineering)" \
  --label "implementation,p0" \
  --body "## Type
\`implementation\` | Priority: \`p0\`

## Depends on
- #IFACE-004
- #IFACE-009
- #IFACE-010
- #IMPL-001
- #DATA-001

## Scope
- **Touch:** \`packages/data/src/data/\` (all files)
- **Do not touch:** any other package

## Description
Implement \`load_pjm()\`, \`fetch_weather()\`, and \`build_features()\`. Also implement \`scripts/download_pjm.py\` CLI (currently missing from repo). Resolve the 2022–2024 data source issue from DATA-001.

## Acceptance Criteria
- [ ] \`load_pjm()\` handles DST deduplication as decided in DATA-001
- [ ] \`fetch_weather()\` returns all \`OPENMETEO_HOURLY_VARS\` for each region
- [ ] \`build_features()\` produces all tier-1, tier-2, tier-3 columns per catalog
- [ ] \`validate_dataset()\` passes on the joined load + weather DataFrame
- [ ] \`openmeteo-requests\` SDK used (FlatBuffers binary encoding, faster than JSON)"

echo "✔ IMPL-002"

# ────────────────────────────────────────────────
# IMPL-003
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-003] Implement models/statistical (SeasonalNaive, AutoARIMA, AutoETS)" \
  --label "implementation,p1" \
  --body "## Type
\`implementation\` | Priority: \`p1\`

## Depends on
- #IFACE-002
- #IFACE-001
- #IMPL-001

## Scope
- **Touch:** \`packages/models/statistical/src/\`
- **Do not touch:** any other package

## Description
- **SeasonalNaive:** \`EXOG_NONE\` only. Baseline model.
- **AutoARIMA:** \`exog.past_columns\` passed as \`X\` to statsforecast ARIMAX. Receives only \`temperature_2m + hdd + cdd + temperature_2m_sq\` (statistical models cannot absorb 10+ correlated features).
- **AutoETS:** \`EXOG_NONE\` only.

## Acceptance Criteria
- [ ] All three implement the \`Forecaster\` Protocol
- [ ] \`@register\` decorator applied in \`__init__.py\`
- [ ] AutoARIMA \`supports_exog = True\`, AutoETS/SeasonalNaive \`supports_exog = False\`"

echo "✔ IMPL-003"

# ────────────────────────────────────────────────
# IMPL-004
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-004] Implement models/ml (LightGBM, XGBoost via MLForecast)" \
  --label "implementation,p1" \
  --body "## Type
\`implementation\` | Priority: \`p1\`

## Depends on
- #IFACE-002
- #IFACE-001
- #IMPL-001
- #IMPL-002

## Scope
- **Touch:** \`packages/models/ml/src/\`
- **Do not touch:** any other package

## Description
Receive pre-built DataFrame from \`features_task\` (\`add_lag=True\`). All tier-1, tier-2, tier-3, and tier-4 columns available as flat features. Tree models do not need cyclic encodings but they are harmless.

## Acceptance Criteria
- [ ] Both LightGBM and XGBoost implement \`Forecaster\` Protocol
- [ ] \`supports_exog = True\`
- [ ] \`@register\` applied in \`__init__.py\`
- [ ] Hyperparams passed via \`ModelConfig.hyperparams\`"

echo "✔ IMPL-004"

# ────────────────────────────────────────────────
# IMPL-005
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-005] Implement models/deep (LSTM, TFT via Darts)" \
  --label "implementation,p2" \
  --body "## Type
\`implementation\` | Priority: \`p2\`

## Depends on
- #IFACE-002
- #IFACE-001
- #IMPL-001
- #IMPL-002

## Scope
- **Touch:** \`packages/models/deep/src/\`
- **Do not touch:** any other package

## Description
- **LSTM:** \`exog.past_columns\` as \`past_covariates\`.
- **TFT:** \`exog.future_known_columns\` as \`future_covariates\`. OpenMeteo 7-day forecast covers the 168h horizon exactly — this is a structural advantage of TFT in this project.

## Acceptance Criteria
- [ ] Both implement \`Forecaster\` Protocol
- [ ] TFT \`supports_exog = True\`, uses \`future_known_columns\`
- [ ] torch in dependency tree only for this package"

echo "✔ IMPL-005"

# ────────────────────────────────────────────────
# IMPL-006
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-006] Implement models/neural (N-HiTS, PatchTST via NeuralForecast)" \
  --label "implementation,p2" \
  --body "## Type
\`implementation\` | Priority: \`p2\`

## Depends on
- #IFACE-002
- #IFACE-001
- #IMPL-001

## Scope
- **Touch:** \`packages/models/neural/src/\`
- **Do not touch:** any other package

## Acceptance Criteria
- [ ] Both implement \`Forecaster\` Protocol
- [ ] \`@register\` applied for both models
- [ ] torch dependency only in this package"

echo "✔ IMPL-006"

# ────────────────────────────────────────────────
# IMPL-007
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-007] Implement models/foundation (TimeGPT-1 via Nixtla SDK)" \
  --label "implementation,p2" \
  --body "## Type
\`implementation\` | Priority: \`p2\`

## Depends on
- #IFACE-002
- #IFACE-001
- #IMPL-001

## Scope
- **Touch:** \`packages/models/foundation/src/\`
- **Do not touch:** any other package

## Acceptance Criteria
- [ ] torch NOT in dependency tree (\`uv sync --package models/foundation\` must not install torch)
- [ ] \`finetune_steps=0\` default
- [ ] \`NIXTLA_API_KEY\` read from environment variable
- [ ] Implements \`Forecaster\` Protocol"

echo "✔ IMPL-007"

# ────────────────────────────────────────────────
# IMPL-008
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-008] Implement pipeline flows (Prefect)" \
  --label "implementation,p1" \
  --body "## Type
\`implementation\` | Priority: \`p1\`

## Depends on
- #IFACE-012
- #IFACE-013
- #IMPL-001
- #IMPL-002

## Scope
- **Touch:** \`packages/pipeline/src/pipeline/\`
- **Do not touch:** any model package directly — interact only via registry

## Acceptance Criteria
- [ ] \`forecast_flow\` runs end-to-end with \`NoOpAdapter\`
- [ ] Sweeps both \`EXOG_NONE\` and \`EXOG_TIER1\` in a single run
- [ ] Prefect UI shows task names matching the \`@task(name=...)\` decorators"

echo "✔ IMPL-008"

# ────────────────────────────────────────────────
# IMPL-009
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-009] Implement tracking package (MLflow adapter)" \
  --label "implementation,p1" \
  --body "## Type
\`implementation\` | Priority: \`p1\`

## Depends on
- #IFACE-008
- #IMPL-001

## Scope
- **Touch:** \`packages/tracking/src/tracking/\`
- **Do not touch:** any other package

## Description
\`MLflowAdapter\` is the only file in the codebase that imports mlflow. Logs both \`EXOG_NONE\` and \`EXOG_TIER1\` metrics as separate tagged runs.

## Acceptance Criteria
- [ ] \`MLflowAdapter\` satisfies \`isinstance(x, TrackingAdapter)\`
- [ ] mlflow imported only in this package
- [ ] Logs \`exog_config_name\` as an MLflow tag for run filtering"

echo "✔ IMPL-009"

# ────────────────────────────────────────────────
# IMPL-010
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-010] Fix CI: implement scripts/translate_latex.py" \
  --label "infra,p1" \
  --body "## Type
\`infra\` | Priority: \`p1\`

## Depends on
_none_

## Scope
- **Touch:** \`scripts/translate_latex.py\`, \`.github/workflows/thesis-pdf.yml\`
- **Do not touch:** any \`packages/\` file

## Description
CI has been broken since the workflow was committed. Implement \`translate_latex.py\` using the GitHub Models API as declared in \`thesis-pdf.yml\`.

## Acceptance Criteria
- [ ] CI pipeline passes on \`main\`
- [ ] \`translate_latex.py\` uses GitHub Models API (not hardcoded key)
- [ ] Script is idempotent — running twice produces the same output"

echo "✔ IMPL-010"

# ────────────────────────────────────────────────
# IMPL-011
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-011] Update refs.bib with all 18 thesis references" \
  --label "docs,p2" \
  --body "## Type
\`docs\` | Priority: \`p2\`

## Depends on
_none_

## Scope
- **Touch:** \`docs/thesis/refs.bib\`
- **Do not touch:** any \`src/\` or \`packages/\` file

## References to include
- GEFCom2014 (Hong et al. IJF 2016)
- PJM Load Forecasting White Paper (Itron model)
- PJM 2026 Long-Term Load Forecast Report
- OpenMeteo documentation
- Correa et al. 2023 (precipitation relevance)
- All model family papers (N-HiTS, PatchTST, TFT, TimeGPT-1, LightGBM)

## Acceptance Criteria
- [ ] All 18 entries valid BibTeX (no broken fields)
- [ ] Compiles without warnings in the thesis LaTeX build"

echo "✔ IMPL-011"

# ────────────────────────────────────────────────
# IMPL-012
# ────────────────────────────────────────────────
gh issue create --repo "$REPO" \
  --title "[IMPL-012] Write thesis chapter skeletons" \
  --label "docs,p3" \
  --body "## Type
\`docs\` | Priority: \`p3\`

## Depends on
- #IMPL-011

## Scope
- **Touch:** \`docs/thesis/*.tex\`
- **Do not touch:** any \`src/\` or \`packages/\` file

## Chapters to scaffold
1. Introduction (motivation, problem statement, contributions)
2. Related Work (load forecasting literature, model families)
3. Data (PJM dataset, OpenMeteo, feature catalog)
4. Methodology (pipeline architecture, experimental design)
5. Results (model comparison, exog ablation)
6. Conclusion

## Acceptance Criteria
- [ ] Each chapter file exists with section headings
- [ ] LaTeX compiles to PDF without errors
- [ ] \`\\cite{}\` calls reference valid keys from \`refs.bib\`"

echo "✔ IMPL-012"

echo ""
echo "🎉 All issues created at https://github.com/$REPO/issues"
echo ""
echo "Critical path reminder:"
echo "  DATA-001 → IFACE-001 → IFACE-009 → IFACE-010 → IMPL-001 → IMPL-002 → IMPL-003 → IMPL-008"