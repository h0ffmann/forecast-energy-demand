# AGENTS.md — AI Automation Layers

TCC — Comparação de Algoritmos de Previsão de Séries Temporais para Demanda de Energia Elétrica  
Author: Matheus Hoffmann Fernandes Santos  
Advisor: Claudio Miceli de Farias, Dr.

This document catalogues every AI touchpoint in the project, from already-running
pipelines to planned agents. Each entry includes: what it does, implementation
complexity, and a cost-benefit rating (C×B: complexity × benefit, where low
complexity + high benefit = best ROI).

---

## Status legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented and running in CI |
| 🔨 | Ready to build (clear spec, no blockers) |
| 🔬 | Requires experimentation (API, prompt tuning) |
| 💡 | Concept (needs design before implementation) |

## C×B rating

Complexity: 1 (a script) → 5 (multi-step agentic loop)  
Benefit: 1 (nice to have) → 5 (saves hours per week)  
**ROI = Benefit / Complexity** — higher is better.

---

## Phase 1 · Code

### ✅ Claude chat — architecture, debugging, review

**What it does**: Ad-hoc consultation via claude.ai with Repomix-packed
context. Used for architecture decisions, debugging model code, reviewing
`baseline.py` structure, and planning the experiment framework.

**How to use**: Run `just repomix` to pack the repo, paste into claude.ai,
ask questions.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 1 | 5 | **5.0** |

**Notes**: Already the primary development loop. Zero setup cost.

---

### ✅ Repomix → context packing

**What it does**: Packs the entire repository into a single markdown file
(`repomix-output.md`) suitable for pasting into an LLM context window.
Enables Claude to reason about the full codebase, not just individual files.

**How to use**: `just repomix` — output is gitignored.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 1 | 4 | **4.0** |

**Notes**: Already configured in `justfile`. Re-run before every major
consultation session.

---

### 🔨 Experiment agent — skip existing MLflow runs

**What it does**: Before running any model, queries the MLflow tracking
server to check whether a run with identical hyperparameters already
exists. Skips completed runs and resumes from the last successful fold.
Prevents re-running expensive GPU jobs (LSTM, TFT, PatchTST) after a
CI timeout or partial failure.

**Implementation sketch**:
```python
# in each model script, before run_experiment()
existing = mlflow.search_runs(
    experiment_names=["energy-forecast"],
    filter_string=f"params.model = '{model_name}' AND params.horizon_h = '{cfg.horizon_h}'"
)
if not existing.empty and existing["status"].iloc[0] == "FINISHED":
    log.info("Run already exists — skipping")
    sys.exit(0)
```

**No LLM needed** — pure MLflow SDK logic.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 2 | 4 | **2.0** |

**Notes**: Becomes essential once LSTM/TFT are running (each fold ~10 min).
Implement before adding any deep learning model.

---

### 🔬 Hyperparameter debug agent

**What it does**: Given a model whose sMAPE is above the GEFCom2014
benchmark, reads the per-fold results CSV and reasons about *why* it is
underperforming. Outputs a structured set of suggested hyperparameter
changes with rationale.

**Example reasoning**:
- sMAPE high on weekends only → `season_length` likely wrong
- Error grows across folds → model overfitting, reduce `max_depth` or add dropout
- High variance between regions → try per-region scaling

**Implementation sketch**:
```python
system = """You are an ML engineer reviewing time-series forecasting results.
Given per-fold RMSE/MAE/sMAPE and model hyperparameters, identify the most
likely cause of underperformance and suggest 1-3 concrete hyperparameter changes.
Output JSON: {"diagnosis": str, "suggestions": [{"param": str, "current": any, "suggested": any, "rationale": str}]}"""

user = f"Model: {model_name}\nHyperparams: {json.dumps(cfg.__dict__)}\nFold results:\n{summary_df.to_csv()}"
```

**Requires**: Claude API or GitHub Models. Input: `results/{model}_results.csv`.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 3 | 3 | **1.0** |

**Notes**: High value later in the project when tuning matters. Low priority
until all 10 models have baseline runs.

---

## Phase 2 · Results

### 🔨 Results comparison agent

**What it does**: Reads all CSVs in `results/`, builds a unified comparison
table (all models × all regions × RMSE/MAE/sMAPE), and:
1. Ranks models by mean sMAPE
2. Flags any model above the GEFCom2014 threshold (sMAPE > 4.1%)
3. Posts the table as a GitHub PR comment
4. Optionally fails the CI check if no model beats the baseline

**Implementation sketch**:
```python
# aggregate all results
dfs = [pd.read_csv(f).assign(model=f.stem) for f in Path("results").glob("*.csv")]
table = pd.concat(dfs).groupby("model")[["rmse","mae","smape"]].mean().sort_values("smape")

# post to PR via GitHub API
gh_comment = f"## Forecast results\n\n{table.to_markdown()}\n\nGEFCom2014 threshold: 4.1% sMAPE"
requests.post(pr_comments_url, json={"body": gh_comment}, headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"})
```

**No LLM needed** — pandas + GitHub REST API.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 2 | 5 | **2.5** |

**Notes**: Build this before running the second model. The PR comment is
immediately useful and costs nothing to run.

---

## Phase 3 · Plots

### 🔨 `plot_results.py` — deterministic figure generation

**What it does**: Reads `results/*.csv` and generates all thesis figures
as PDF files in `docs/project/shared/fig/generated/`. No LLM involved —
purely deterministic matplotlib/seaborn. Runs in CI before the LaTeX build.

**Output files**:
```
fig/generated/
  rmse_comparison.pdf        # grouped barplot, all models × mean RMSE
  smape_by_region.pdf        # heatmap model × region, sMAPE colour scale
  forecast_vs_actual_*.pdf   # one per model, best fold, 168h horizon
  exog_gain.pdf              # ΔsMAPE with vs without temperature covariate
  federated_vs_central.pdf   # Fed-LSTM ablation
```

**Style contract** (so figures look consistent in the thesis):
```python
STYLE = {
    "figure.figsize": (5.5, 3.2),   # fits \textwidth in the thesis layout
    "font.size": 10,
    "axes.titlesize": 11,
    "savefig.bbox": "tight",
    "savefig.dpi": 300,
    "savefig.format": "pdf",
}
plt.rcParams.update(STYLE)
```

**No title inside the figure** — title goes in the LaTeX `\caption{}`.
**No legend inside for single-series plots** — label goes in caption.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 2 | 5 | **2.5** |

**Notes**: Implement this in parallel with the second model. Every figure
generated here is one less thing to create manually.

---

### 🔬 Figure placement agent

**What it does**: Takes a chapter `.tex` file (written without figures) and
a list of available PDFs in `fig/generated/`, then produces the same chapter
with `\begin{figure}` blocks inserted at the appropriate locations.

**What the LLM decides for each figure**:
- Which paragraph it illustrates
- Placement specifier: `[htbp]` or `[H]`
- Descriptive caption in Portuguese (academic register)
- `\label{fig:...}` consistent with the chapter's naming convention
- Whether to insert a `\ref{fig:...}` in the preceding sentence

**Input / output**:
```
input:  cap5.tex (prose only) + ["rmse_comparison.pdf", "smape_by_region.pdf", ...]
output: cap5.tex with \figure{} environments inserted
```

**Implementation sketch**:
```python
system = """You are a LaTeX editor inserting figures into a thesis chapter.
Given the chapter source and a list of available figure filenames, insert
\begin{figure}[htbp] blocks at appropriate locations.
Rules:
- Insert each figure immediately after the paragraph it illustrates
- Use \includegraphics[width=\textwidth]{../shared/fig/generated/<filename>}
- Write captions in formal Brazilian Portuguese
- Add \label{fig:<chapter>-<descriptor>}
- Add a \ref{} in the preceding paragraph's last sentence
- Never insert two figures consecutively without intervening text
Return only the modified LaTeX source."""
```

**Requires**: Claude API or GitHub Models. Run manually, review output before commit.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 3 | 4 | **1.33** |

**Notes**: Run once per chapter, after the prose is written. Always review
the output — the LLM occasionally places a figure one paragraph too early.
The `plot_results.py` must be implemented first.

---

## Phase 4 · LaTeX / Thesis

### ✅ Tectonic CI build

**What it does**: On every push to `main` that touches `docs/project/pt/**`,
builds the PT-BR and EN-US PDFs using Tectonic (XeTeX, lazy package
download). Commits both PDFs back to the repo with `[skip ci]`.

**Key files**: `.github/workflows/thesis-pdf.yml`

**Tectonic advantages over `texlive-full`**:
- 50 MB binary vs 7 GB install
- Downloads only required packages (cached across runs)
- First run: ~2 min. Subsequent runs with warm cache: ~20 s.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 2 | 5 | **2.5** |

---

### ✅ Translation agent — PT-BR → EN-US

**What it does**: Translates every `.tex` file in `docs/project/pt/` to
`docs/project/en/` using GitHub Models (Llama 3.3 70B via
`models.github.ai/inference`). Uses SHA-256 content hashes to skip
unchanged files. Logs input/output token counts and % of free daily limit used.

**Key files**: `scripts/translate_latex.py`

**Cost**: Free. Uses `GITHUB_TOKEN` already available in Actions.  
**Rate limit**: 15 req/min → `time.sleep(4)` between files.  
**Daily limit**: 170k tokens. A full thesis (~80 pages) ≈ 120k tokens one-time,
then near-zero per run due to hash caching.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 2 | 4 | **2.0** |

---

### 🔨 Consistency agent

**What it does**: Parses `\begin{table}` environments in `.tex` files,
extracts numeric values, and cross-checks them against the corresponding
`results/*.csv`. Fails the CI build with a precise diff if any number
is stale.

**Example output on failure**:
```
INCONSISTENCY DETECTED in cap5.tex line 142:
  LaTeX says:  LSTM RMSE = 142.3 MW
  results CSV: LSTM RMSE = 138.7 MW  (run 2024-03-15)
  Difference:  3.6 MW (2.5%)
```

**Implementation**: Python script, no LLM. Regex to extract table cells,
pandas to load CSVs, numeric comparison with configurable tolerance (default 0.1%).

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 3 | 5 | **1.67** |

**Notes**: Becomes critical after cap5 is written. A wrong number in the
thesis defence is much worse than a CI failure.

---

### 🔬 cap5 writer agent

**What it does**: Generates a full draft of `cap5.tex` (Resultados
Experimentais) from structured inputs. The LLM writes the prose; you
review and adjust.

**Inputs**:
- `results/*.csv` — all model results
- `CLAUDE.md` — benchmark targets, algorithm descriptions
- `cap2.tex` — theoretical background (for terminology consistency)
- Figure list from `fig/generated/`

**Output**: `docs/project/pt/cap5.tex` with:
- Introduction paragraph contextualising the evaluation protocol
- One subsection per algorithm family (Statistical, ML, Deep Learning, Foundation)
- Comparison table (LaTeX `\begin{table}`) with all 10 models
- Analysis paragraph per family, referencing specific numbers
- Closing section comparing against GEFCom2014 and prior Poli theses

**Requires**: Claude API (Sonnet recommended for long-form academic writing).
Estimated cost: ~$0.10 per full draft.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 3 | 5 | **1.67** |

**Notes**: Highest single-shot value of all agents. Even a 70% draft
saves 4-6 hours of writing. Run after all 10 models have results.

---

### 🔬 PT writing review agent

**What it does**: Reads each chapter and flags:
- Afirmações sem `\cite{}` (factual claims without citation)
- Termos técnicos inconsistentes (e.g. "previsão" vs "predição" vs "forecast" mixed)
- Frases com mais de 40 palavras
- Voz passiva excessiva (more than 30% of sentences)
- Parágrafos com uma única frase
- Anglicismos não estabelecidos no domínio

**Output**: Annotated list with line numbers and suggested fixes. Does not
rewrite — only flags.

**Requires**: GitHub Models (Llama 3.3 70B sufficient for this task). Free.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 3 | 3 | **1.0** |

**Notes**: Run once per chapter before submission. Most useful for cap1
(Introdução) and cap6 (Conclusões) where prose quality matters most.

---

## Phase 5 · Literature

### 🔬 Gap analysis agent

**What it does**: Queries the Semantic Scholar API for papers published
in the last 2 years matching the thesis topics. Compares results against
`docs/project/shared/refs.bib` and outputs a list of relevant papers
not yet cited.

**Search queries** (auto-generated from CLAUDE.md):
- "electricity demand forecasting deep learning"
- "PatchTST time series"
- "N-HiTS energy load"
- "TimeGPT electricity"
- "temperature covariate energy forecasting"
- "federated learning time series privacy"

**Output**: Markdown list with title, authors, year, citation count, and
one-sentence relevance summary. Sorted by citation count descending.

**API**: `https://api.semanticscholar.org/graph/v1/paper/search` — free,
no key required for low-volume use.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 3 | 4 | **1.33** |

**Notes**: Run once when starting cap3 (Trabalhos Relacionados) and once
before submission. High value for finding recent PatchTST / TimeGPT papers
that cite the same PJM dataset.

---

### 🔬 Benchmark extractor agent

**What it does**: Given a list of papers cited in `cap3.tex`, fetches
their abstracts (and PDFs where available) and extracts reported metrics
(MAPE, RMSE, MAE) into a structured format. Produces a ready-to-paste
LaTeX comparison table.

**Output**:
```latex
\begin{table}[htbp]
\centering
\caption{Comparação com trabalhos relacionados}
\begin{tabular}{llrrl}
\hline
Trabalho & Algoritmo & MAPE (\%) & Dataset & Notas \\
\hline
GEFCom2014 \cite{gefcom2014} & Ensemble & 2.6--4.1 & GEFCom & Referência do domínio \\
Gramm AI (2025) \cite{gramm2025} & PatchTST & 3.2 & PJM & Benchmark recente \\
...
\hline
\end{tabular}
\end{table}
```

**Requires**: Claude API for PDF parsing + structured extraction.
Estimated cost: ~$0.05 per paper.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 4 | 4 | **1.0** |

**Notes**: High manual effort to build this table by hand. The agent
saves ~2h of reading and formatting. Implement after gap analysis confirms
which papers to include.

---

### 🔨 Citation agent

**What it does**: Scans each chapter for sentences that make factual
or comparative claims without a `\cite{}` command within 50 characters.
Suggests papers from `refs.bib` that could support each uncited claim.

**Example output**:
```
cap2.tex:87 — Uncited claim:
  "Modelos de deep learning superam modelos estatísticos em séries longas"
  Suggested: \cite{zhou2021informer}, \cite{li2023patchTST}

cap3.tex:142 — Uncited claim:
  "A temperatura é o principal fator exógeno para previsão de demanda"
  Suggested: \cite{correa2023temperature}, \cite{hong2016probabilistic}
```

**Implementation**: Rule-based sentence classifier (no LLM needed for
detection) + embedding similarity to find relevant bib entries.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 3 | 4 | **1.33** |

**Notes**: Run before every advisor review meeting. Nothing signals a
weak chapter faster than unsupported claims.

---

## Phase 6 · Forecasting models

### ✅ SeasonalNaive baseline

**What it does**: Walk-forward cross-validation of the seasonal naive
forecast (repeats last observed weekly cycle). Reference implementation
for all other models — same `Config`, `walk_forward_splits()`,
`compute_metrics()`, and MLflow logging structure.

**File**: `main.py`  
**Run**: `just baseline` or `uv run main.py --data data/raw`

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 1 | 5 | **5.0** |

---

### 🔨 9 remaining models

Each follows the same pattern as `main.py`. Estimated implementation
time and AI assistance level per model:

| Model | File | Family | Exog | Est. time | AI assist |
|-------|------|--------|------|-----------|-----------|
| AutoARIMA | `autoarima.py` | Statistical | Yes (ARIMAX) | 2h | Low — StatsForecast handles it |
| AutoETS | `autoets.py` | Statistical | No | 1h | Low |
| LightGBM | `lightgbm_model.py` | ML | Yes | 3h | Medium — feature engineering |
| XGBoost | `xgboost_model.py` | ML | Yes | 2h | Medium — reuse LightGBM features |
| LSTM | `lstm.py` | Deep Learning | Yes | 5h | High — Darts config |
| TFT | `tft.py` | Deep Learning | Yes | 5h | High — Darts config |
| N-HiTS | `nhits.py` | Deep Learning | Yes | 4h | High — NeuralForecast |
| PatchTST | `patchtst.py` | Deep Learning | Yes | 4h | High — NeuralForecast |
| TimeGPT | `timegpt.py` | Foundation | Yes | 2h | Low — Nixtla SDK |

**Recommended order**: AutoARIMA → LightGBM → XGBoost → AutoETS →
TimeGPT → LSTM → N-HiTS → PatchTST → TFT  
(statistical first for fast baseline comparisons; deep learning last
because they need GPU and longer run times)

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 4 | 5 | **1.25** |

---

## Phase 7 · Federated experiment

### 💡 Fed-LSTM vs centralised LSTM

**What it does**: Ablation study measuring the accuracy cost of federated
learning (privacy preservation) vs centralised training. Uses Flower (flwr)
with FedProx aggregation. Each PJM region is a separate federated client.

**Research question**: How much sMAPE do we lose by not sharing raw data
across regions?

**Implementation approach**:
```python
# Server: aggregates model weights via FedProx
# Client: each region runs local LSTM training on its own data slice
# Comparison: centralised LSTM (main.py pattern) vs federated LSTM
```

**Expected result**: 0.5–2% sMAPE degradation for federated vs centralised,
consistent with literature on federated time-series.

| Complexity | Benefit | ROI |
|-----------|---------|-----|
| 5 | 4 | **0.8** |

**Notes**: Implement last. Requires all other models to be complete first
(for context in the thesis). The Flower experiment is the most novel
contribution of the TCC and deserves its own chapter section.

---

## Implementation roadmap

Ordered by ROI (highest first):

```
Now (models 1-3 running):
  ✅ Claude chat + Repomix           ROI 5.0 / 4.0
  🔨 plot_results.py                 ROI 2.5  — do this week
  🔨 Results comparison agent        ROI 2.5  — do this week
  🔨 Experiment agent (skip runs)    ROI 2.0  — before LSTM

Mid-project (all models running):
  🔬 cap5 writer agent               ROI 1.67 — after all 10 models done
  🔨 Consistency agent               ROI 1.67 — before advisor review
  🔬 Figure placement agent          ROI 1.33 — after cap5 draft
  🔬 Gap analysis agent              ROI 1.33 — when writing cap3
  🔬 Citation agent                  ROI 1.33 — before every review

Late (writing phase):
  🔬 Benchmark extractor             ROI 1.0  — for cap3 table
  🔬 Hyperparameter debug agent      ROI 1.0  — if models underperform
  🔬 PT writing review agent         ROI 1.0  — final polish

Final sprint:
  💡 Fed-LSTM experiment             ROI 0.8  — last chapter, most novel
```

---

## Token budget estimate

| Agent | Model | Tokens/run | Cost |
|-------|-------|-----------|------|
| Translation (full thesis) | Llama 3.3 70B | ~120k | Free (GitHub Models) |
| Translation (incremental) | Llama 3.3 70B | ~5k avg | Free |
| cap5 writer | Claude Sonnet | ~15k | ~$0.10 |
| Figure placement (per chapter) | GitHub Models | ~8k | Free |
| PT review (per chapter) | GitHub Models | ~6k | Free |
| Hyperparameter debug | GitHub Models | ~3k | Free |
| Gap analysis | Semantic Scholar API | — | Free |
| Benchmark extractor (per paper) | Claude Sonnet | ~5k | ~$0.03 |
| Citation agent | GitHub Models | ~4k | Free |

**Total estimated cost for full thesis**: < $1 USD  
(only cap5 writer and benchmark extractor use paid API)