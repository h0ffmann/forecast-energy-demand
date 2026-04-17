# Undergraduate Thesis Proposal

**Federal University of Rio de Janeiro**
Escola Politécnica — Department of Electronic and Computer Engineering

| |                                   |
|---|-----------------------------------|
| **Student** | Matheus Hoffmann Fernandes Santos |
| **Email** | hoffmann [at] poli.ufrj.br        |
| **Advisor** | Claudio Miceli de Farias, Dr.     |

---

## 1. Title

Comparison of Time Series Forecasting Algorithms for Electricity Demand: from Statistical Models to Foundation Models

---

## 2. Emphasis

Electronic and Computer Engineering — Computational Statistics, Data Science, and Software Development

---

## 3. Topic

Short-term electricity demand forecasting — commonly referred to as load forecasting — is one of the most extensively studied time series problems in engineering and machine learning literature. Power system operators rely on accurate hourly forecasts to plan generation, avoid grid imbalances, and reduce operational costs. The relevance of this problem has motivated international competitions such as GEFCom2014 [9] and the development of standardised benchmarks that enable direct algorithm comparisons across multiple datasets and forecast horizons.

The relationship between temperature and electricity load is one of the most thoroughly documented exogenous covariates in the time series literature: consumption peaks on hot days (air conditioning) and cold days (electric heating) create a non-linear dependency on temperature that purely historical models cannot adequately capture [10]. This covariate is therefore a productive setting for comparing algorithm families: while statistical models such as AutoARIMA can incorporate it as an external regressor (ARIMAX), machine learning models such as LightGBM learn its interaction with hour of day and day of week implicitly, and foundation models such as TimeGPT [16] accept temperature as an exogenous variable without any manual feature engineering.

The topic of this work is the experimental comparison of ten time series forecasting algorithms — spanning statistical, machine learning, deep learning, spatiotemporal graph, and foundation model families — applied to hourly electricity demand forecasting by region, assessing the incremental effect of temperature as an exogenous covariate for each algorithm family. The dataset used is the PJM Hourly Energy Consumption [8], publicly available and widely used in comparative energy forecasting studies. Results will be benchmarked against published literature, including neural network models applied to the Brazilian National Interconnected System (SIN) in recent Escola Politécnica UFRJ theses [12, 13].

---

## 4. Scope

The scope of this work encompasses the implementation, training, and comparative evaluation of ten time series forecasting algorithms applied to hourly electricity demand forecasting by PJM operator region [8], with hourly temperature as an exogenous covariate obtained via the OpenMeteo API. Evaluation is performed both with and without temperature to quantify the incremental gain per algorithm family.

The following are explicitly out of scope:

- Development of any software component for model serving or deployment; the work concludes at algorithm evaluation and comparative analysis
- Energy price forecasting, renewable generation forecasting, or any variable other than load demand (MWh per hour per region)
- Generation dispatch optimisation or any downstream application of the forecasts
- Use of the ONS dataset — while relevant to the Brazilian context, its public granularity is lower than PJM for international benchmark comparison purposes

---

## 5. Rationale

Electricity demand forecasting is one of the richest domains in standardised benchmarks within the time series literature. The GEFCom2014 competition [9] produced comparative performance tables with over 30 teams and multiple model families, providing MAPE by region and horizon — exactly the type of reference this work can use to position its results. This level of benchmark standardisation is rare in other demand forecasting domains such as urban transportation.

Within Escola Politécnica UFRJ, two recent theses addressed electricity load forecasting but with methodological limitations this work aims to overcome. Costa (2024) [12] compared Holt-Winters, Box-Jenkins, and neural networks for daily load curves using ONS data; Pessoa (2023) [13] applied Box-Jenkins and classical models to the SIN. Both predate the widespread adoption of modern frameworks such as the Nixtla ecosystem (StatsForecast, MLForecast) and neither evaluates foundation models such as TimeGPT [16]. Lima (2018) [14] and Santos (2020) [15] from Electronic and Computer Engineering applied non-linear models to electricity consumption profiles, but without a systematic comparative protocol across families. This thesis fills that gap by bringing together, under the same experimental protocol, statistical algorithms, lag-feature machine learning models, deep learning models, and TimeGPT — the first foundation model for time series [16].

The inclusion of TimeGPT as the tenth algorithm is particularly relevant to this work. Unlike the other algorithms, TimeGPT is a model pre-trained on over 100 billion time series data points and operates in zero-shot mode: it generates forecasts without any training on the user's dataset [16]. Nixtla provides an official tutorial using the PJM Hourly Energy Consumption dataset for exactly this use case, which facilitates reproducibility and direct comparative positioning. Assessing whether TimeGPT outperforms models trained specifically on each region's historical data — and under which conditions — is an academically relevant question that remains largely unexplored in Brazilian undergraduate theses.

---

## 6. Objectives

The general objective of this work is to systematically compare ten time series forecasting algorithms — from the statistical, machine learning, deep learning, spatiotemporal, and foundation model families — applied to hourly electricity demand forecasting by region, evaluating the effect of incorporating temperature as an exogenous covariate and benchmarking results against the literature.

Specific objectives are:

- Build the training dataset from PJM Hourly Energy Consumption [8] (2022–2024), covering the major operator regions, and incorporate hourly temperature via the OpenMeteo API for the same period and location of each region
- Implement the ten algorithms described in Section 7 — statistical models via StatsForecast, ML via MLForecast, TFT via Darts, T-GCN via PyTorch Geometric Temporal, and TimeGPT via the Nixtla SDK — and evaluate all of them under the same walk-forward protocol
- Quantify, per algorithm family, the incremental gain in RMSE, MAE, and sMAPE provided by including temperature as an exogenous covariate, separating the climate effect from the algorithmic effect
- Position the obtained results against load forecasting benchmarks in the literature — in particular the MAPE range of 2.6%–4.1% reported by top GEFCom2014 teams [9] — and against prior Poli UFRJ theses that addressed the same problem [12, 13]

---

## 7. Methodology

The work will be organised into three sequential stages.

**Stage 1 — Dataset construction.** The PJM Hourly Energy Consumption dataset [8] will be obtained in CSV format (available on Kaggle and the PJM portal), covering 2022 to 2024 at hourly granularity per operating region. The ten regions with the highest total consumption volume will be selected — analogously to the high-demand zone criterion used in transportation forecasting. Hourly reference temperature for each region will be integrated via the OpenMeteo API using the centroid coordinates of each operating area. An exploratory analysis will document the non-linear relationship between temperature and load (U-curve: peaks in heat and cold), daily, weekly, and annual seasonality, and the presence of outliers associated with extreme weather events or national holidays.

**Stage 2 — Comparative algorithm evaluation.** The ten algorithms listed in Table 1 will be trained and evaluated under the same walk-forward protocol: a four-week training window shifted progressively forward and a one-week forecast horizon (168 hours). Each algorithm is evaluated twice — without and with temperature as an exogenous variable, where supported. RMSE, MAE, and sMAPE metrics are computed per window and aggregated as load-volume-weighted averages across regions.

**Table 1: Evaluated algorithms, families, implementations, and exogenous covariate support.**

| Algorithm | Family | Implementation | Exogenous support |
|---|---|---|---|
| Seasonal Naive | Baseline | StatsForecast | No — lower bound reference |
| AutoARIMA | Statistical | StatsForecast | Yes — exogenous variables as ARIMAX |
| AutoETS | Statistical | StatsForecast | No — exponential smoothing |
| Prophet | Statistical | Darts / prophet | Yes — additional regressors |
| LightGBM (lags) | Machine Learning | MLForecast | Yes — temperature as lag feature |
| XGBoost (lags) | Machine Learning | MLForecast | Yes — same as LightGBM |
| Random Forest (lags) | Machine Learning | MLForecast | Yes — same as LightGBM |
| TFT | Deep Learning | Darts | Yes — past and known future covariates |
| T-GCN | Spatiotemporal Graph | PyTorch Geometric Temporal [15] | No — regional adjacency replaces spatial exogenous |
| TimeGPT-1 | Foundation Model | Nixtla SDK [16] | Yes — fine-tuning with exogenous variables via API |

Machine learning models are implemented via MLForecast with lag features, rolling statistics, and temperature as an additional column. TFT, via Darts, receives the OpenMeteo temperature forecast for the horizon as a known future covariate — a structural advantage over pure lag models, particularly at a 168-hour horizon where diurnal temperature variation is highly predictable. T-GCN is implemented via PyTorch Geometric Temporal: PJM regions are represented as graph nodes with edges based on geographical adjacency between the states of each operating area. TimeGPT is accessed via the Nixtla SDK with 10 fine-tuning steps on each region's historical data, following the protocol documented in the official energy demand forecasting tutorial [16].

**Stage 3 — Analysis and benchmarking.** The third stage consolidates the comparative analysis along two dimensions: absolute algorithm performance (ranking by RMSE/MAPE) and the incremental temperature gain per algorithm. Results are then positioned against the literature benchmarks shown in Table 2. Special attention is given to TimeGPT: as a zero-shot model, its performance without fine-tuning is compared separately, enabling an assessment of how much local historical data contributes relative to general pre-training. All experiments are tracked with MLflow to ensure reproducibility.

**Table 2: Selected hourly electricity load forecasting benchmarks from the literature.**

| Study | Algorithm | Dataset / region | MAPE (%) | Climate exogenous |
|---|---|---|---|---|
| Hong et al. (2016) [9] | Ensemble (GEFCom2014) | GEFCom2014, 8 US regions, 1h | 2.6–4.1 | Temperature + 24 climate variables |
| Bianchini (2024) [11] | LSTM | ONS — SIN Brazil, 1h | < 2% | Historical SIN temperature |
| Bianchini (2024) [11] | MLP | ONS — SIN Brazil, 1h | < 3% | Historical SIN temperature |
| Costa (2024) [12] | Neural Networks | ONS — load curve, 1h | Comparative | Temperature and hour of day |
| Nixtla (2025) [16] | TimeGPT-1 | PJM Energy, 5 regions, 1h | Outperforms N-HiTS | Natively supported |
| Pessoa (2023) [13] | Box-Jenkins / Holt-Winters | ONS — SIN Brazil, daily | Comparative | No |

---

## 8. Schedule

**Table 3: Undergraduate Thesis Schedule.**

| Stage | Timeline |
|---|---|
| Literature review: electricity load forecasting, time series algorithms, temperature effect on demand, and foundation models | Apr 2026 (15 days) |
| Data ingestion and preprocessing: PJM Hourly Energy Consumption (2022–2024) + hourly temperature via OpenMeteo API per region | May 2026 (15 days) |
| Exploratory analysis: temporal patterns, seasonality, temperature–load correlation per region | May 2026 (15 days) |
| Implementation of statistical and machine learning algorithms: Seasonal Naive, AutoARIMA, AutoETS, LightGBM, XGBoost, LSTM, MLP | Jun 2026 (15 days) |
| Implementation of TFT (Darts) with future temperature covariates | Jun – Jul 2026 (1–2 months) |
| Implementation of T-GCN (PyTorch Geometric Temporal) with regional adjacency graph | Jul – Aug 2026 (1–2 months) |
| Implementation and fine-tuning of TimeGPT-1 (Nixtla SDK) on the PJM dataset | Aug – Sep 2026 (1–2 months) |
| Comparative evaluation: walk-forward CV with and without temperature as exogenous covariate for all models | Sep 2026 (15 days) |
| Thesis writing — theoretical background, methodology, results, and conclusion | Oct – Nov 2026 (2 months) |
| Final revision and submission | Dec 2026 (15 days) |
| Defense | Jan – Feb 2027 |

---

## References

[1] GARZA, A.; MERGENTHALER-CANSECO, M. StatsForecast: lightning-fast forecasting with statistical and econometric models. In: PyCon, Salt Lake City, 2022.

[2] GARZA, A. et al. MLForecast: scalable machine learning for time series forecasting. In: PyCon, Salt Lake City, 2022.

[3] HERZEN, J. et al. Darts: user-friendly modern machine learning for time series. Journal of Machine Learning Research, v. 23, n. 124, p. 1–6, 2022.

[4] LIM, B. et al. Temporal Fusion Transformers for interpretable multi-horizon time series forecasting. International Journal of Forecasting, v. 37, n. 4, p. 1748–1764, 2021.

[5] HYNDMAN, R. J.; ATHANASOPOULOS, G. Forecasting: Principles and Practice. 3rd ed. Melbourne: OTexts, 2021.

[6] MAKRIDAKIS, S. et al. The M5 accuracy competition: results, findings and conclusions. International Journal of Forecasting, v. 38, n. 4, p. 1346–1364, 2022.

[7] ZHAO, L. et al. T-GCN: A Temporal Graph Convolutional Network for Traffic Prediction. IEEE Transactions on Intelligent Transportation Systems, v. 21, n. 9, p. 3848–3858, 2020.

[8] PJM INTERCONNECTION. PJM Hourly Energy Consumption. Kaggle, 2024. Available at: https://www.kaggle.com/datasets/robikscube/hourly-energy-consumption.

[9] HONG, T. et al. Probabilistic electric load forecasting: A tutorial review. International Journal of Forecasting, v. 32, n. 3, p. 914–938, 2016.

[10] HONG, T.; FAN, S. Probabilistic electric load forecasting: A tutorial review. International Journal of Forecasting, v. 32, n. 3, p. 914–938, 2016.

[11] BIANCHINI, A. Application of artificial neural networks for short-term electric load forecasting in Brazil. Undergraduate Thesis — Electrical Engineering, UFSC, Florianópolis, 2024.

[12] COSTA, G. S. Daily Load Curve Forecasting: A Comparative Analysis of Holt-Winters, Box-Jenkins, and Neural Network Models. Undergraduate Thesis — Electrical Engineering, UFRJ / Escola Politécnica, Rio de Janeiro, 2024.

[13] PESSOA, E. F. Daily Load Curve Forecasting Using Data from the National Electric System Operator. Undergraduate Thesis — Electrical Engineering, UFRJ / Escola Politécnica, Rio de Janeiro, 2023.

[14] LIMA, H. P. Consumption Profile Estimation Using Non-Linear Models Applied to Time Series. Undergraduate Thesis — Electronic and Computer Engineering, UFRJ / Escola Politécnica, Rio de Janeiro, 2018.

[15] SANTOS, F. C. S. Estimation of Electricity Market Price Using Non-Linear Models. Undergraduate Thesis — Electronic and Computer Engineering, UFRJ / Escola Politécnica, Rio de Janeiro, 2020.

[16] GARZA, A.; CHALLU, C.; MERGENTHALER-CANSECO, M. TimeGPT-1. arXiv:2310.03589, Oct. 2023. Available at: https://arxiv.org/abs/2310.03589.

[17] ROZEMBERCZKI, B. et al. PyTorch Geometric Temporal: Spatiotemporal Signal Processing with Neural Machine Learning Models. In: Proceedings of the 30th ACM International Conference on Information & Knowledge Management (CIKM 2021), 2021.

[18] DAVIM, J. V. A. Time Series Forecasting with Weightless Neural Networks. Undergraduate Thesis — Computer and Information Engineering, UFRJ / Escola Politécnica, Rio de Janeiro, 2022.

---

Rio de Janeiro, April 2026.

___

Matheus Hoffmann Fernandes Santos — Student

___

Claudio Miceli de Farias — Advisor