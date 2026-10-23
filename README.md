# RootLens

> Root-cause analysis of manufacturing quality deviations from process data. It finds where the line breaks, suggests what to change, estimates the savings, and checks each of those answers before trusting it.

PS #30, Digital Manufacturing. Software only.

## Latest Release: v0.1.0 (backend)

## What it answers
1. **Where.** It ranks parameters (SECOM) and stations (Bosch) by mean |SHAP| over 50 bootstrap refits. A parameter is flagged *stable* only when it reappears in the top 10 **and** beats a label-permutation null.
2. **What to change.** It recommends a "safe window" for each stable parameter, always inside the observed p5–p95 operating range, with Wilson CIs. Each window is re-checked on a held-out, later time window.
3. **How much it saves.** It returns a savings *range* (low / mid / high), labelled as a model estimate.

## What makes it different
| Feature | Why it matters |
|---|---|
| **Planted-fault benchmark** | Real data has no ground truth. We plant known causes in real SECOM inputs and check how many RootLens recovers, compared with naive SHAP. Under a null scenario (labels that are pure noise), naive SHAP still returns 10 suspects. RootLens returns 0. |
| **AI4I rule check** | AI4I is a synthetic dataset whose failure modes are defined by explicit rules. RootLens recovers the rule inputs for each failure mode. |
| **Pilot planner** | For each fix, a power analysis gives the number of parts, days and cost needed to confirm the fix on the real line. |
| **Data-grounded counterfactuals** | For a failing run, it finds the nearest real low-risk passing runs and shows what differed. Nothing is extrapolated. |
| **Root-cause timeline** | Rolling-window attribution shows which driver led in which period, and flags drift. |
| **Bosch station view** | Station fail rates (re-weighted from a subsample), Sankey route links, and a station-level stability ranking. |
| **Honest evaluation** | Chronological split only. PR-AUC and MCC are reported with bootstrap CIs, plus lift over random, a capture curve and an adversarial drift check. A random-split number is shown alongside to expose leakage inflation. |

## Tech Stack
| Layer | Technology |
|---|---|
| ML | Python 3.12, pandas, scikit-learn, LightGBM, SHAP, statsmodels |
| API | FastAPI, uvicorn |
| Frontend | teammate's dashboard (`frontend-dashboard` branch) |

## File Structure
```
backend/
├── config.py            # paths, thresholds
├── ml/
│   ├── load.py          # SECOM load + chronological split
│   ├── features.py      # train-only drop / flag / impute, correlation groups
│   ├── metrics.py       # PR-AUC, MCC, CIs, Wilson, capture curve
│   ├── train.py         # LightGBM + logistic baseline, model selection, drift
│   ├── rank.py          # bootstrap SHAP + permutation null + L1 stability
│   ├── safe_window.py   # corrective ranges + held-out check
│   ├── cost.py          # savings range
│   ├── pilot.py         # power-analysis pilot planner
│   ├── counterfactual.py
│   ├── timeline.py      # rolling root-cause timeline
│   ├── planted.py       # planted-fault benchmark + AI4I check
│   ├── bosch.py         # Bosch subsample, stations, routes
│   └── pipeline.py      # end-to-end run -> artifacts/
├── api/                 # FastAPI app (main.py, state.py)
└── tests/
```

## Setup & Installation
```bash
pip install -r requirements.txt
```
Data goes under `data/`, which is gitignored:
- `secom.zip` at the repo root (included), auto-extracted to `data/secom/`
- `data/ai4i/ai4i2020.csv`, from UCI dataset 601
- `data/bosch-production-line-performance/train_numeric.csv.zip` and `train_date.csv.zip`, from Kaggle. Then run `make bosch-sample`.

## Environment Variables
| Variable | Description | Required |
|---|---|---|
| `CORS_ORIGINS` | comma-separated allowed origins (default `*`) | No |

## How to Run
```bash
make train        # ~8 min full run; `make train-quick` for a smoke run
make api          # http://localhost:8000/docs
make test
```

## API
`GET /api/overview`, `/api/metrics`, `/api/ranking`, `/api/safe-windows`, `/api/pilots`, `/api/timeline`, `/api/validation/planted`, `/api/validation/ai4i`, `/api/stations`, `/api/runs`, `/api/runs/{index}`, `/api/operating-ranges`
`POST /api/savings`, `/api/pilot`, `/api/score`

## What we claim and what we don't
SECOM features are anonymized and the data is observational. Rankings are **statistically suspected, stability-checked** associations, not proven causes. Accuracy is never reported. Every savings figure is a range and a model estimate. Anything derived from the model's own predictions is labelled *model-estimated*. A pilot on the real line confirms or rejects each fix.

## Changelog
### v0.1.0 — 2026-10-23
- Backend ML pipeline, validation suite and REST API

## License
MIT
