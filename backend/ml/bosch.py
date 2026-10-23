"""Bosch Production Line Performance: stage-level (station) analysis on a subsample.

Feature names encode line/station: L3_S29_F3407 -> line 3, station 29. That makes a real
station ranking possible (SECOM only supports anonymous feature groups).

Negatives are downsampled when building the sample; every rate reported here is
re-weighted by the inverse sampling fraction so it reflects the full line.
"""
import json
import re
import zipfile

import numpy as np
import pandas as pd

from backend.config import BOSCH_DIR, SEED

RAW_DIR = BOSCH_DIR.parent / "bosch-production-line-performance"
NEG_FRACTION = 0.06
CHUNK = 50_000
NAME_RE = re.compile(r"^L(\d+)_S(\d+)_[FD](\d+)$")


def station_of(col: str) -> str | None:
    m = NAME_RE.match(col)
    return f"L{m.group(1)}_S{m.group(2)}" if m else None


def station_num(st: str) -> int:
    return int(st.split("_S")[1])


def _open_csv(name):
    z = zipfile.ZipFile(RAW_DIR / f"{name}.csv.zip")
    return z, z.open(z.infolist()[0])


def build_sample(neg_fraction=NEG_FRACTION, seed=SEED, progress=print) -> dict:
    """Stream train_numeric + train_date; keep all failures and a fixed fraction of passes."""
    BOSCH_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    kept, scanned, positives = [], 0, 0
    z, fh = _open_csv("train_numeric")
    with z, fh:
        for chunk in pd.read_csv(fh, chunksize=CHUNK, dtype=np.float32, converters={"Id": int}):
            scanned += len(chunk)
            pos = chunk["Response"] == 1
            positives += int(pos.sum())
            keep = pos.to_numpy() | (rng.random(len(chunk)) < neg_fraction)
            kept.append(chunk[keep])
            if progress:
                progress(f"numeric rows scanned {scanned:,}")
    num = pd.concat(kept, ignore_index=True)
    num["Response"] = num["Response"].astype(np.int8)
    ids = set(num["Id"])

    # date file is reduced on the fly to per-station first/last timestamps
    st_parts = []
    z, fh = _open_csv("train_date")
    with z, fh:
        for chunk in pd.read_csv(fh, chunksize=CHUNK, dtype=np.float32, converters={"Id": int}):
            chunk = chunk[chunk["Id"].isin(ids)]
            if chunk.empty:
                continue
            cols = [c for c in chunk.columns if c != "Id"]
            st = pd.Series({c: station_of(c) for c in cols})
            per = {}
            for s, group in st.groupby(st):
                block = chunk[group.index]
                per[f"{s}_tmin"] = block.min(axis=1)
                per[f"{s}_tmax"] = block.max(axis=1)
            df = pd.DataFrame(per)
            df.insert(0, "Id", chunk["Id"].to_numpy())
            st_parts.append(df)
            if progress:
                progress(f"date rows kept {sum(len(p) for p in st_parts):,}")
    dates = pd.concat(st_parts, ignore_index=True)

    num.to_parquet(BOSCH_DIR / "numeric_sample.parquet", index=False)
    dates.to_parquet(BOSCH_DIR / "station_times_sample.parquet", index=False)
    info = {
        "rows_scanned": scanned, "positives_total": positives,
        "true_fail_rate": positives / scanned,
        "sample_rows": int(len(num)), "sample_positives": int(num["Response"].sum()),
        "negative_fraction": neg_fraction, "negative_weight": 1 / neg_fraction, "seed": seed,
        "rule": "all Response==1 rows plus a uniform random fraction of Response==0 rows",
    }
    (BOSCH_DIR / "sample_info.json").write_text(json.dumps(info, indent=2))
    return info


def load_sample() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    num = pd.read_parquet(BOSCH_DIR / "numeric_sample.parquet")
    times = pd.read_parquet(BOSCH_DIR / "station_times_sample.parquet")
    info = json.loads((BOSCH_DIR / "sample_info.json").read_text())
    df = num.merge(times, on="Id", how="left")
    return df, times, info


def stations(df: pd.DataFrame) -> list[str]:
    s = {station_of(c) for c in df.columns if c.count("_") == 2}
    return sorted((x for x in s if x), key=station_num)


def visited_matrix(df: pd.DataFrame, sts: list[str]) -> pd.DataFrame:
    """A part visited a station if it has any numeric reading or timestamp there."""
    out = {}
    for s in sts:
        cols = [c for c in df.columns if c.startswith(s + "_")]
        out[s] = df[cols].notna().any(axis=1)
    return pd.DataFrame(out)


def weights(y: pd.Series, info: dict) -> np.ndarray:
    return np.where(y.to_numpy() == 1, 1.0, info["negative_weight"])


def engineered(df: pd.DataFrame, sts: list[str]) -> pd.DataFrame:
    """Route and timing features: visited flags, dwell per station, start time, total span."""
    V = visited_matrix(df, sts)
    feats = {f"{s}_visited": V[s].astype(np.int8) for s in sts}
    tmin = df[[f"{s}_tmin" for s in sts if f"{s}_tmin" in df]]
    tmax = df[[f"{s}_tmax" for s in sts if f"{s}_tmax" in df]]
    for s in sts:
        if f"{s}_tmin" in df:
            feats[f"{s}_dwell"] = df[f"{s}_tmax"] - df[f"{s}_tmin"]
    feats["route_start"] = tmin.min(axis=1)
    feats["route_span"] = tmax.max(axis=1) - tmin.min(axis=1)
    feats["n_stations"] = V.sum(axis=1)
    return pd.DataFrame(feats, index=df.index)


def station_rates(df, y, sts, info) -> list[dict]:
    from backend.ml.metrics import wilson_ci
    V = visited_matrix(df, sts)
    w = weights(y, info)
    out = []
    for s in sts:
        m = V[s].to_numpy()
        if m.sum() == 0:
            continue
        fails = float((y.to_numpy()[m] == 1).sum())
        parts = float(w[m].sum())
        n_eff = int(round(parts))
        out.append({"station": s, "line": int(s[1:s.index("_")]), "parts_est": n_eff,
                    "fails": int(fails), "fail_rate": fails / parts,
                    "fail_rate_ci": wilson_ci(int(fails), n_eff)})
    return out


def route_links(df, y, sts, info, max_links=80) -> dict:
    """Sankey data: consecutive-station transitions with re-weighted failure rates."""
    V = visited_matrix(df, sts).to_numpy()
    yv = y.to_numpy()
    w = weights(y, info)
    counts, fails = {}, {}
    for i in range(len(V)):
        path = [sts[j] for j in np.flatnonzero(V[i])]
        for a, b in zip(path, path[1:]):
            counts[(a, b)] = counts.get((a, b), 0.0) + w[i]
            fails[(a, b)] = fails.get((a, b), 0.0) + (yv[i] == 1)
    links = sorted(counts, key=counts.get, reverse=True)[:max_links]
    used = sorted({n for l in links for n in l}, key=station_num)
    return {
        "nodes": used,
        "links": [{"source": a, "target": b, "parts_est": round(counts[(a, b)]),
                   "fail_rate": fails[(a, b)] / counts[(a, b)]} for a, b in links],
        "label": "Part flow between consecutive stations; width = parts (re-weighted), colour = fail rate.",
    }


def _station_boot(Xtr, ytr, idx, params, seed, shap_rows, col_map) -> pd.Series:
    import lightgbm as lgb
    import shap
    m = lgb.LGBMClassifier(**params, random_state=seed, n_jobs=2).fit(Xtr.iloc[idx], ytr.iloc[idx])
    sv = shap.TreeExplainer(m).shap_values(shap_rows)
    sv = sv[1] if isinstance(sv, list) else sv
    per_col = pd.Series(np.abs(sv).mean(axis=0), index=Xtr.columns)
    return per_col.groupby(col_map).sum()


def station_ranking(df, y, sts, info, B=20, n_estimators=150, top_k=10, stable_freq=0.7,
                    progress=None) -> dict:
    """LightGBM on station readings + route/timing features; |SHAP| summed per station,
    repeated over bootstrap refits for stability. Fit on the earlier 80 % by route start time."""
    import lightgbm as lgb
    import shap

    from backend.ml.metrics import evaluate, pr_auc

    eng = engineered(df, sts)
    readings = df[[c for c in df.columns if NAME_RE.match(c) and "_F" in c]]
    X = pd.concat([readings, eng], axis=1).astype(np.float32)
    order = np.argsort(eng["route_start"].fillna(np.inf).to_numpy(), kind="stable")
    X, yy = X.iloc[order].reset_index(drop=True), y.iloc[order].reset_index(drop=True)
    cut = int(len(X) * 0.8)
    Xtr, ytr, Xte, yte = X.iloc[:cut], yy.iloc[:cut], X.iloc[cut:], yy.iloc[cut:]

    def col_station(c):
        return station_of(c) or (c.rsplit("_", 1)[0] if c.startswith("L") else "route")

    col_map = pd.Series({c: col_station(c) for c in X.columns})
    params = dict(n_estimators=n_estimators, learning_rate=0.05, num_leaves=15, max_depth=5,
                  min_child_samples=30, colsample_bytree=0.4, subsample=0.8, subsample_freq=1,
                  verbose=-1, scale_pos_weight=float((ytr == 0).sum() / max((ytr == 1).sum(), 1)))
    model = lgb.LGBMClassifier(**params, random_state=SEED).fit(Xtr, ytr)
    p_te = model.predict_proba(Xte)[:, 1]
    test_eval = {"pr_auc_sample": pr_auc(yte, p_te),
                 "prevalence_sample": float(yte.mean()),
                 "note": "Prevalence and PR-AUC are on the downsampled sample, not the full line."}

    from joblib import Parallel, delayed

    from backend.config import N_JOBS
    rng = np.random.default_rng(SEED)
    shap_rows = Xtr.sample(min(5000, len(Xtr)), random_state=SEED)
    draws = [rng.integers(0, len(Xtr), len(Xtr)) for _ in range(B)]
    # fewer workers than SECOM: each holds a copy of the ~300 MB sample
    imps = Parallel(n_jobs=min(N_JOBS, 6))(
        delayed(_station_boot)(Xtr, ytr, idx, params, SEED + b, shap_rows, col_map)
        for b, idx in enumerate(draws))
    if progress:
        progress(B, B)
    ranks = [imp.rank(ascending=False, method="min") for imp in imps]
    R = pd.concat(ranks, axis=1).fillna(len(col_map.unique()))
    I = pd.concat(imps, axis=1).fillna(0.0)
    freq = (R <= top_k).mean(axis=1)
    table = pd.DataFrame({"mean_rank": R.mean(axis=1), "rank_std": R.std(axis=1),
                          "mean_abs_shap": I.mean(axis=1), "top_k_freq": freq})
    table["stable"] = table["top_k_freq"] >= stable_freq
    table = table.sort_values(["top_k_freq", "mean_rank"], ascending=[False, True])

    # top parameters within each of the top stations, from the full fit
    sv = shap.TreeExplainer(model).shap_values(shap_rows)
    sv = sv[1] if isinstance(sv, list) else sv
    per_col = pd.Series(np.abs(sv).mean(axis=0), index=X.columns)
    top_params = {s: [{"feature": c, "mean_abs_shap": float(v)}
                      for c, v in per_col[col_map == s].sort_values(ascending=False).head(5).items()]
                  for s in table.index[:top_k]}
    return {
        "method": f"LightGBM |SHAP| summed per station over {B} bootstrap refits; "
                  f"stable if in top-{top_k} in >= {int(stable_freq * 100)}% of refits",
        "stations": [{"station": s, **{k: (bool(v) if k == "stable" else float(v)) for k, v in r.items()},
                      "top_parameters": top_params.get(s, [])}
                     for s, r in table.iterrows()],
        "holdout": test_eval,
        "label": "Statistically suspected stations, stability-checked. Association, not proven cause.",
    }


def run_bosch(B=20, progress=None) -> dict:
    df, _, info = load_sample()
    y = df["Response"].astype(int)
    sts = stations(df)
    return {
        "sample_info": info,
        "n_stations": len(sts),
        "station_rates": station_rates(df, y, sts, info),
        "route": route_links(df, y, sts, info),
        "station_ranking": station_ranking(df, y, sts, info, B=B, progress=progress),
    }


if __name__ == "__main__":
    print(build_sample())
