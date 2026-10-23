"""Printable demo run sheet built from a real SECOM row (a staged stand-in for a line's
parameter sheet). Large, high-contrast, gridded so a camera or vision model reads it reliably."""
import io
import json

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from backend.api.state import state
from backend.config import CAPTURES_DIR

N_FIELDS = 15
W, H = 1240, 1754  # A4 at 150 dpi


def fields() -> list[str]:
    """The top-ranked raw parameters, in rank order."""
    feats = [f["feature"] for f in state.json("ranking.json")["features"]]
    cols = set(state.bundle["feature_columns"])
    return [f for f in feats if f in cols][:N_FIELDS]


def _font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fmt(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.6g}"


def sheet_values(index: int) -> dict:
    X, y, ts, _ = state.data
    row = X.loc[index]
    return {"run_id": f"R-{index:04d}", "index": index, "timestamp": str(ts.loc[index]),
            "values": {f: (None if pd.isna(row[f]) else float(row[f])) for f in fields()}}


def render(index: int) -> bytes:
    info = sheet_values(index)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((80, 70), "PROCESS RUN SHEET", font=_font(64, True), fill="black")
    d.text((80, 160), f"Run ID: {info['run_id']}", font=_font(44, True), fill="black")
    d.text((80, 220), f"Logged: {info['timestamp']}", font=_font(32), fill="black")
    top, row_h, x0, x1, x2 = 320, 76, 80, 560, 1160
    d.rectangle([x0, top, x2, top + row_h], fill="#e8e8e8", outline="black", width=3)
    d.text((x0 + 24, top + 18), "PARAMETER", font=_font(36, True), fill="black")
    d.text((x1 + 24, top + 18), "VALUE", font=_font(36, True), fill="black")
    for i, (f, v) in enumerate(info["values"].items(), start=1):
        y0 = top + i * row_h
        d.rectangle([x0, y0, x2, y0 + row_h], outline="black", width=2)
        d.text((x0 + 24, y0 + 16), f, font=_font(40, True), fill="black")
        d.text((x1 + 24, y0 + 16), _fmt(v), font=_font(40), fill="black")
    d.line([x1, top, x1, top + (len(info["values"]) + 1) * row_h], fill="black", width=3)
    d.text((80, H - 120), "Staged demo sheet generated from a public SECOM dataset row.",
           font=_font(26), fill="#444444")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    _remember(data, info)
    return data


def _remember(png: bytes, info: dict) -> None:
    """Exact-file cache: uploading this same PNG later still works with every provider down."""
    import hashlib
    cache = CAPTURES_DIR / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{hashlib.sha256(png).hexdigest()}.json").write_text(json.dumps(
        {"run_id": info["run_id"], "values": {k: v for k, v in info["values"].items() if v is not None},
         "unreadable": [k for k, v in info["values"].items() if v is None]}))
