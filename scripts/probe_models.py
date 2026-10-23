"""Probe every model in config/llm_chain.yaml before a demo.

    python -m scripts.probe_models            # vision + text
    python -m scripts.probe_models --vision   # vision only

Vision: sends the real demo run sheet and counts values read exactly. Text: a short grounded
reply. Prints reachable / valid JSON / correct values / latency per model. Keep only models
that read every value correctly.
"""
import argparse
import json
import time

import yaml

from backend.ai import llm
from backend.capture import run_sheet, vision


def probe_vision(entries, index=None):
    _, _, _, s = run_sheet.state.data
    index = index if index is not None else int(s.y_test[s.y_test == 1].index[0])
    png = run_sheet.render(index)
    truth = {k: v for k, v in run_sheet.sheet_values(index)["values"].items() if v is not None}
    img = vision.prepare(png)
    msg = [{"role": "user", "content": vision.PROMPT.replace("{fields}", ", ".join(run_sheet.fields())),
            "images": [("image/jpeg", img)]}]
    rows = []
    for e in entries:
        t0 = time.time()
        row = {"provider": e["provider"], "model": e["model"]}
        try:
            r = llm.chat(msg, provider=e["provider"], model=e["model"], json_mode=True, temperature=0.0,
                         max_tokens=e.get("max_tokens", 2048), retries=0)
            parsed = vision._parse(r.content)
            row["reachable"] = True
            row["valid_json"] = parsed is not None
            got = (parsed or {}).get("values", {})
            row["correct"] = sum(1 for k, v in truth.items() if k in got and abs(got[k] - v) <= abs(v) * 1e-6 + 1e-9)
            row["expected"] = len(truth)
        except Exception as ex:  # noqa: BLE001
            row.update(reachable=False, valid_json=False, correct=0, expected=len(truth), error=str(ex)[:120])
        row["seconds"] = round(time.time() - t0, 2)
        row["keep"] = row["correct"] == row["expected"]
        rows.append(row)
    return rows


def probe_text(entries):
    rows = []
    msg = [{"role": "user", "content": 'Return JSON {"ok": true, "value": 0.118} exactly.'}]
    for e in entries:
        t0 = time.time()
        row = {"provider": e["provider"], "model": e["model"]}
        try:
            r = llm.chat(msg, provider=e["provider"], model=e["model"], json_mode=True, max_tokens=e.get("max_tokens", 512), retries=0)
            j = json.loads(r.content)
            row.update(reachable=True, valid_json=True, keep=j.get("value") == 0.118)
        except Exception as ex:  # noqa: BLE001
            row.update(reachable=False, valid_json=False, keep=False, error=str(ex)[:120])
        row["seconds"] = round(time.time() - t0, 2)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vision", action="store_true")
    ap.add_argument("--text", action="store_true")
    a = ap.parse_args()
    cfg = yaml.safe_load(llm.CHAIN_FILE.read_text())
    both = not (a.vision or a.text)
    for task, fn in (("vision", probe_vision), ("text", probe_text)):
        if not (both or getattr(a, task)):
            continue
        print(f"\n== {task} ==")
        for r in fn([e for e in cfg[task] if llm.available().get(e["provider"])]):
            extra = f" {r.get('correct')}/{r.get('expected')} correct" if task == "vision" else ""
            print(f"{'KEEP' if r['keep'] else 'drop':4}  {r['provider']}:{r['model']:45} reach={r['reachable']} "
                  f"json={r['valid_json']}{extra}  {r['seconds']}s  {r.get('error', '')}")


if __name__ == "__main__":
    main()
