"""Score backend.assembly's damage finder on labelled GLBs.

Usage: python -m scripts.inspector_eval <dir with *.glb and *.json ground truth>

Two passes per file:
  tagged    the GLB as exported (carries rootlens_* custom properties)
  stripped  every rootlens_* property removed, so only object names and geometry are available
Ground truth is `<name>.json` written next to each GLB by the generator. The AI labeller is not used.
"""
import copy
import json
import sys
from collections import defaultdict
from pathlib import Path

from backend.assembly.gltf import read_glb
from backend.assembly.inspect import summarize


def strip_tags(doc: dict) -> dict:
    doc = copy.deepcopy(doc)
    for coll in ("nodes", "meshes"):
        for item in doc.get(coll, []):
            ex = item.get("extras")
            if isinstance(ex, dict):
                for k in [k for k in ex if k.startswith("rootlens_")]:
                    ex.pop(k)
    return doc


def score(found: set, truth: set) -> tuple:
    tp = len(found & truth)
    return tp, len(found - truth), len(truth - found)


def main(folder: str) -> dict:
    rows = []
    for glb in sorted(Path(folder).glob("*.glb")):
        gt = json.loads(glb.with_suffix(".json").read_text(encoding="utf-8"))
        truth = {f["object"] for f in gt["faults"]}
        doc, binary = read_glb(glb.read_bytes())
        for mode, d in (("tagged", doc), ("stripped", strip_tags(doc))):
            s = summarize(d, binary)
            found = {p["name"] for p in s["parts"] if p.get("damage")}
            tp, fp, fn = score(found, truth)
            rows.append({"file": glb.stem, "mode": mode, "truth": len(truth), "found": len(found),
                         "tp": tp, "fp": fp, "fn": fn,
                         "file_has_fault": bool(truth), "file_flagged": bool(found)})
    out = {}
    for mode in ("tagged", "stripped"):
        r = [x for x in rows if x["mode"] == mode]
        tp, fp, fn = (sum(x[k] for x in r) for k in ("tp", "fp", "fn"))
        by_family = defaultdict(lambda: [0, 0, 0])
        for x in r:
            fam = x["file"].rsplit("_v", 1)[0]
            for i, k in enumerate(("tp", "fp", "fn")):
                by_family[fam][i] += x[k]
        out[mode] = {
            "objects_tp": tp, "objects_fp": fp, "objects_fn": fn,
            "precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1),
            "files_with_fault_flagged": sum(x["file_has_fault"] and x["file_flagged"] for x in r),
            "files": len(r),
            "by_family": {f: {"tp": v[0], "fp": v[1], "fn": v[2], "recall": v[0] / max(v[0] + v[2], 1)}
                          for f, v in by_family.items()},
            "per_file": [{k: x[k] for k in ("file", "truth", "found", "tp", "fp", "fn")} for x in r],
        }
    return out


if __name__ == "__main__":
    res = main(sys.argv[1])
    Path(sys.argv[2] if len(sys.argv) > 2 else "inspector_eval.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for mode, v in res.items():
        print(f"== {mode}: precision {v['precision']:.2f}  recall {v['recall']:.2f}  "
              f"(tp {v['objects_tp']}, fp {v['objects_fp']}, fn {v['objects_fn']}); "
              f"files flagged {v['files_with_fault_flagged']}/{v['files']}")
        for fam, f in v["by_family"].items():
            print(f"   {fam:15s} recall {f['recall']:.2f}  tp {f['tp']} fp {f['fp']} fn {f['fn']}")
