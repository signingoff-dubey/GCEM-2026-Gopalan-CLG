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
| **Grounded AI analyst** | A tool-calling agent (Groq, with Gemini as fallback) answers questions such as "what do I fix first and what is it worth?" A guard checks every number against the tool outputs and blocks accuracy claims, causation claims and guesses about what anonymized features mean. |
| **One-click investigation** | It runs the whole RCA plan in parallel (quality → drift → ranking → windows → timeline → validation → stations → pilot → savings) and writes a structured, number-checked brief. |
| **Photo / webcam capture** | It reads a process sheet from a photo or laptop webcam through a vision failover chain (Groq → Gemini → OpenRouter → cache → manual entry), range-checks the values, then scores the run. |
| **3D-scan inspection** (separate capability) | Upload an iPad LiDAR mesh to get crack candidates from the texture and dents measured against a reference scan by ICP. A highlighted GLB is returned. Results are analyzed after upload and state the sensor's limits. |
| **Comparison** | A capability table against 7 public SECOM/Bosch projects we checked, worded as "found in N of 7". |

## Tech Stack
| Layer | Technology |
|---|---|
| ML | Python 3.12, pandas, scikit-learn, LightGBM, SHAP, statsmodels |
| API | FastAPI, uvicorn |
| AI | Groq (gpt-oss-20b, qwen3.8-27b), Gemini, OpenRouter: failover chain over httpx |
| Inspection | trimesh, OpenCV, scikit-image |
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
├── api/                 # FastAPI app + routes (ai, capture, inspection, compare)
├── ai/                  # LLM clients + chain, tools, grounding guard, agent, orchestrator
├── capture/             # run sheet, vision extraction, capture store
├── inspection/          # 3D scan load, cracks, dents, GLB export
└── tests/
config/llm_chain.yaml    # provider/model failover order
scripts/probe_models.py  # pre-demo model check
```

## Setup & Installation
```bash
pip install -r requirements.txt
```
Data goes under `data/`, which is gitignored:
- `datasets/secom.zip` (included), auto-extracted to `data/secom/`
- `data/ai4i/ai4i2020.csv`, from UCI dataset 601
- `data/bosch-production-line-performance/train_numeric.csv.zip` and `train_date.csv.zip`, from Kaggle. Then run `make bosch-sample`.

## Environment Variables
| Variable | Description | Required |
|---|---|---|
| `GROQ_API_KEY` (`_2`, `_3`, …) | Groq keys, rotated on rate limits | For AI / vision |
| `GEMINI_API_KEY` (`_2`, …) | Gemini keys | For AI / vision fallback |
| `OPENROUTER_API_KEY` (`_2`, …) | OpenRouter free-tier keys | Optional fallback |
| `ROOTLENS_JOBS` | worker processes for bootstrap refits (default: cores − 2, max 16) | No |
| `CORS_ORIGINS` | comma-separated allowed origins (default `*`) | No |

3D scans for inspection go in `data/scans/` (gitignored).

## How to Run
```bash
make train        # parallel; a few minutes on a multi-core laptop; `make train-quick` for a smoke run
make api          # http://localhost:8000/docs
make test
```

## API
`GET /api/overview`, `/api/metrics`, `/api/ranking`, `/api/safe-windows`, `/api/pilots`, `/api/timeline`, `/api/validation/planted`, `/api/validation/ai4i`, `/api/stations`, `/api/runs`, `/api/runs/{index}`, `/api/operating-ranges`, `/api/compare`
`POST /api/savings`, `/api/pilot`, `/api/score`

AI: `GET /api/ai/status` · `POST /api/ai/ask`, `/api/ai/investigate`
Capture: `POST /api/captures` (image, source=upload|webcam), `/api/captures/manual` · `GET /api/captures`, `/api/captures/latest`, `/api/captures/{id}`, `/api/captures/{id}/image`, `/api/run-sheet?index=`, `/api/run-sheet/fields`
Inspection: `POST /api/inspection/scan`, `/api/inspection/samples/analyze` · `GET /api/inspection`, `/api/inspection/samples`, `/api/inspection/{id}`, `/api/inspection/{id}/model.glb`

Model order lives in `config/llm_chain.yaml`. Run `python -m scripts.probe_models` before a demo to re-check every model against the real run sheet.

## What we claim and what we don't
SECOM features are anonymized and the data is observational. Rankings are **statistically suspected, stability-checked** associations, not proven causes. Accuracy is never reported. Every savings figure is a range and a model estimate. Anything derived from the model's own predictions is labelled *model-estimated*. A pilot on the real line confirms or rejects each fix.

## Changelog
### v0.1.0 — 2026-10-23
- Backend ML pipeline, validation suite and REST API

## License
MIT
