"""Does synthetic / interpolated data improve the RootLens model on REAL data?

Run from the repo root:
  python -m scripts.synthetic_eval                                  # SECOM
  python -m scripts.synthetic_eval --dataset mendeley --xlsx modelo.xlsx

Protocol (no leakage): expanding-window folds over the real, time-sorted rows. Inside each
fold the generators are fitted on that fold's TRAIN rows only, synthetic rows are added to
training only, and every score is computed on REAL later rows. Metrics are imbalance-aware
(PR-AUC, MCC, balanced accuracy); plain accuracy is not reported.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from backend.config import ARTIFACTS_DIR
from backend.ml.features import Preprocessor
from backend.ml.load import load_secom
from backend.ml.metrics import mcc, pr_auc
from backend.ml.synthetic import CopulaSynth, smote_fails
from backend.ml.train import fit_logistic, fit_lgbm, predict

N_EST = 300


def score(y, p, thr):
    pred = (p >= thr).astype(int)
    return {"pr_auc": pr_auc(y, p), "mcc": mcc(y, p, thr), "bal_acc": float(balanced_accuracy_score(y, pred))}


def fit_eval(Xtr, ytr, Xva, yva, Xte, yte, kind="lgbm"):
    if kind == "lgbm":
        t = fit_lgbm(Xtr, ytr, Xva, yva, n_estimators=N_EST)
    else:
        t = fit_logistic(Xtr, ytr, Xva, yva)
    return score(yte, predict(t, Xte), t.threshold)


def interp_impute(train, others):
    """Linear interpolation in time for train; causal forward-fill for later blocks."""
    tr = train.interpolate(method="linear", limit_direction="both")
    med = tr.median()
    tr = tr.fillna(med)
    out = []
    prev = tr
    for blk in others:
        joined = pd.concat([prev.tail(1), blk]).ffill().iloc[1:].fillna(med)
        out.append(joined)
        prev = joined
    return tr, out


def load_mendeley(path: str):
    """Real 2023-25 plastics plant data (Mendeley gtnb4j7bfx, CC BY 4.0): one row per production order.
    fail = reject rate in the worst 10 % of orders. Reject counts / kilos / % columns are leaky and excluded;
    zeros in process columns mean 'not used on this machine type' and become NaN."""
    df = pd.read_excel(path, engine="openpyxl").dropna(how="all")
    df = df.sort_values("Fecha_registro", kind="stable").reset_index(drop=True)
    rate = df["Producto_rechazados"] / df["Produccion_total"].replace(0, np.nan)
    y = (rate > rate.quantile(0.90)).astype(int).rename("fail")
    drop = ["Fecha_registro", "Producto_rechazados", "Produccion_total", "Produccion_requerida", "Kilos_defectuosos",
            "%Defectuosos", "%Reproceso", "%Colada", "Kilos_colada", "Consumo_PP_kilos", "Nombre_producto",
            "Maquina", "Turno"]
    X = df.drop(columns=drop).copy()
    X.columns = [c.replace(chr(0xFFFD), "o") for c in X.columns]   # mangled accent in the source header
    X["machine_code"] = df["Maquina"].astype("category").cat.codes
    X["shift_code"] = df["Turno"].astype("category").cat.codes
    keep = ("machine_code", "shift_code", "Peso_producto_gramos", "Peso_prom_bruto", "Cavidades_molde",
            "Consumo_pigmento_kilos")
    proc = [c for c in X.columns if c not in keep]
    X[proc] = X[proc].replace(0, np.nan)
    return X, y, df["Fecha_registro"].rename("timestamp")


def run(seeds: int, data=None):
    X, y, ts = data if data is not None else load_secom()
    n = len(X)
    edges = np.linspace(int(n * 0.4), n, 5).astype(int)
    rows = []
    for fi in range(4):
        tr_end, te_end = edges[fi], edges[fi + 1]
        va0 = int(tr_end * 0.85)
        Xtr, ytr = X.iloc[:va0], y.iloc[:va0]
        Xva, yva = X.iloc[va0:tr_end], y.iloc[va0:tr_end]
        Xte, yte = X.iloc[tr_end:te_end], y.iloc[tr_end:te_end]
        pre = Preprocessor(impute=False).fit(Xtr)
        cols = pre.kept_
        gen = CopulaSynth().fit(Xtr[cols], ytr)
        for kind in ("lgbm", "logistic"):
            base = fit_eval(Xtr, ytr, Xva, yva, Xte, yte, kind)
            rows.append(dict(fold=fi, seed=-1, kind=kind, strategy="real_only", test_pos=int(yte.sum()), **base))
            # interpolation of missing values instead of median impute
            a, (b, c) = interp_impute(Xtr[cols], [Xva[cols], Xte[cols]])
            rows.append(dict(fold=fi, seed=-1, kind=kind, strategy="real_interp_missing", test_pos=int(yte.sum()),
                             **fit_eval(a, ytr, b, yva, c, yte, kind)))
            for s in range(seeds):
                # (1) SMOTE-style interpolation between real fails -> ~20 % prevalence
                n_new = max(int(0.25 * (ytr == 0).sum()) - int(ytr.sum()), 0)
                sm = smote_fails(Xtr[cols], ytr, n_new, seed=s)
                Xa = pd.concat([Xtr[cols], sm], ignore_index=True)
                ya = pd.concat([ytr, pd.Series(np.ones(len(sm), int))], ignore_index=True)
                rows.append(dict(fold=fi, seed=s, kind=kind, strategy="real+interp_fails", test_pos=int(yte.sum()),
                                 **fit_eval(Xa, ya, Xva, yva, Xte, yte, kind)))
                # (2) copula synthetic rows stamped 2026
                Xs, ys, _ = gen.sample(len(Xtr), seed=100 + s)
                Xb = pd.concat([Xtr[cols], Xs], ignore_index=True)
                yb = pd.concat([ytr, ys], ignore_index=True)
                rows.append(dict(fold=fi, seed=s, kind=kind, strategy="real+synth2026", test_pos=int(yte.sum()),
                                 **fit_eval(Xb, yb, Xva, yva, Xte, yte, kind)))
                # (3) both
                Xc = pd.concat([Xb, sm], ignore_index=True)
                yc = pd.concat([yb, pd.Series(np.ones(len(sm), int))], ignore_index=True)
                rows.append(dict(fold=fi, seed=s, kind=kind, strategy="real+synth2026+interp_fails",
                                 test_pos=int(yte.sum()), **fit_eval(Xc, yc, Xva, yva, Xte, yte, kind)))
                # (4) synthetic only -> real test (is the synthetic data realistic?)
                rows.append(dict(fold=fi, seed=s, kind=kind, strategy="synth2026_only", test_pos=int(yte.sum()),
                                 **fit_eval(Xs, ys, Xva, yva, Xte, yte, kind)))
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> dict:
    out = {}
    for kind, g in df.groupby("kind"):
        base = g[g.strategy == "real_only"].set_index("fold")
        res = {}
        for strat, h in g.groupby("strategy"):
            per_fold = h.groupby("fold")[["pr_auc", "mcc", "bal_acc"]].mean()
            d = per_fold["pr_auc"] - base["pr_auc"]
            res[strat] = {
                "pr_auc": float(per_fold["pr_auc"].mean()),
                "mcc": float(per_fold["mcc"].mean()),
                "bal_acc": float(per_fold["bal_acc"].mean()),
                "pr_auc_delta_vs_real_only": float(d.mean()),
                "folds_improved": int((d > 1e-9).sum()),
                "per_fold_pr_auc": [round(float(v), 4) for v in per_fold["pr_auc"]],
            }
        out[kind] = res
    out["test_positives_per_fold"] = [int(v) for v in df[df.strategy == "real_only"].drop_duplicates("fold")
                                      .sort_values("fold").test_pos.iloc[:4]]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--dataset", default="secom", choices=["secom", "mendeley"])
    ap.add_argument("--xlsx", default="")
    ap.add_argument("--out", default=str(ARTIFACTS_DIR / "synthetic_eval.json"))
    a = ap.parse_args()
    t0 = time.time()
    df = run(a.seeds, load_mendeley(a.xlsx) if a.dataset == "mendeley" else None)
    summ = summarise(df)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(summ, indent=2), encoding="utf-8")
    pd.set_option("display.width", 200)
    for kind in ("lgbm", "logistic"):
        print(f"\n== {kind} ==")
        print(pd.DataFrame(summ[kind]).T[["pr_auc", "mcc", "bal_acc", "pr_auc_delta_vs_real_only", "folds_improved"]].round(4))
    print("test positives per fold:", summ["test_positives_per_fold"], f"({time.time() - t0:.0f}s)")
