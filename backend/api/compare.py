"""How RootLens compares with public projects on the same datasets.

Based on a README / code review on 2026-10-23 of the sources below. Phrased as what we found
in the sources we checked, never as a claim about what anyone else lacks."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["compare"])

SOURCES = [
    {"name": "liamculligan/bosch-production-line-performance", "url": "https://github.com/liamculligan/bosch-production-line-performance"},
    {"name": "jiaruxu233/Bosch-Production-Line-Performance", "url": "https://github.com/jiaruxu233/Bosch-Production-Line-Performance"},
    {"name": "jaycheng0118/secom-defect-prediction", "url": "https://github.com/jaycheng0118/secom-defect-prediction"},
    {"name": "henryliu513436/SECOM-Yield-Detection", "url": "https://github.com/henryliu513436/SECOM-Yield-Detection"},
    {"name": "swathibmadhuranath/secom-yield-prediction", "url": "https://github.com/swathibmadhuranath/secom-yield-prediction"},
    {"name": "Sharanuganji/secom-yield-dashboard", "url": "https://github.com/Sharanuganji/secom-yield-dashboard"},
    {"name": "nitishsjsucs/Semiconductor-Equipment-Data-Analysis-Platform", "url": "https://github.com/nitishsjsucs/Semiconductor-Equipment-Data-Analysis-Platform"},
]
CHECKED = len(SOURCES)

# (capability, rootlens status, rootlens evidence, found_in, note)
ROWS = [
    ("Chronological train/test split (no shuffling across time)", "yes",
     "70/15/15 by timestamp; random-split number shown only as a leakage contrast", 1, None),
    ("Imbalance-aware metrics instead of accuracy", "yes", "PR-AUC and MCC with bootstrap CIs, lift over random", 6,
     "most projects we checked report PR-AUC, ROC-AUC, MCC or balanced accuracy"),
    ("Confidence intervals on model metrics", "yes", "bootstrap CIs on PR-AUC and MCC", 1, None),
    ("SHAP or similar per-parameter explanations", "yes", "TreeSHAP, missingness flags folded into their parameter", 2, None),
    ("Ranking stability across resamples", "yes", "50 bootstrap refits, stable if top-10 in >=70%", 1,
     "one project used stability selection over bootstrap models"),
    ("Permutation-null check against false discoveries", "yes", "pooled null importances from 20 label permutations", 0, None),
    ("Ground-truth validation of the ranking (planted faults, null labels)", "yes",
     "planted-fault benchmark on real SECOM inputs + AI4I rule recovery", 0, None),
    ("Corrective parameter values", "yes", "safe windows inside the observed p5-p95 range with Wilson CIs", 0,
     "one project lists deviating sensors per alert"),
    ("Corrections re-checked on a later held-out window", "yes", "observed in/out fail rate on the test window", 0, None),
    ("Savings estimate as a range", "yes", "low / mid / high, labelled model estimate", 0, None),
    ("Pilot sizing to confirm a fix (power analysis)", "yes", "parts per arm, days and cost per window", 0, None),
    ("Drift detection", "yes", "adversarial validation AUC + rolling root-cause timeline", 2,
     "one project reports adversarial validation; one uses SPC excursion rules"),
    ("Counterfactuals from real passing runs", "yes", "nearest low-risk passing runs, no extrapolation", 0, None),
    ("Station-level analysis on Bosch", "yes", "station fail rates, route Sankey, station stability ranking", 2, None),
    ("Interactive dashboard", "yes", "React dashboard over a FastAPI backend", 2, None),
    ("LLM assistant over the results", "yes", "tool-calling agent; every number checked against tool output", 2,
     "we did not find a numeric grounding check in the sources we checked"),
    ("Reading process values from a photo or webcam", "yes", "vision chain with range checks and manual fallback", 0, None),
    ("SPC control charts / Cpk", "no", "not built", 1, None),
    ("Leaderboard-tuned predictive score (Kaggle MCC)", "partial",
     "not tuned for leaderboard; out-of-time evaluation instead", 1, "one project reports a Kaggle private-LB MCC of 0.487"),
]

WORDING = (f"Counts are how many of the {CHECKED} public projects we checked show the capability in their README "
           "or code (review on 2026-10-23; one further source, IEEE 7840826, could not be retrieved). "
           "'0' means we did not find it in the sources we checked, not that it does not exist elsewhere.")


@router.get("/compare")
def compare():
    rows = []
    for cap, status, evidence, found, note in ROWS:
        others_note = note or ("we did not find this in the sources we checked" if found == 0 else None)
        rows.append({"capability": cap, "rootlens": {"status": status, "evidence": evidence},
                     "others": {"found_in": found, "checked": CHECKED, "note": others_note}})
    summary = {
        "rootlens_yes": sum(r[1] == "yes" for r in ROWS),
        "capabilities": len(ROWS),
        "not_found_in_checked_sources": sum(r[3] == 0 for r in ROWS if r[1] == "yes"),
        "matched_common_practice": sum(r[3] >= 2 for r in ROWS if r[1] == "yes"),
    }
    return {"rows": rows, "summary": summary, "sources": SOURCES, "wording": WORDING}
