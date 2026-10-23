"""Store assemblies under data/assemblies/<id>/ and join them with line data for overlays."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from backend import cloud
from backend.api.state import ArtifactMissing, state
from backend.assembly import SIMULATED_NOTE, demo
from backend.assembly.convert import ConvertError, prepare
from backend.assembly.inspect import summarize
from backend.config import ASSEMBLY_DIR, MODELS_DIRS

STATION_RE = re.compile(r"^L\d+_S\d+$")
BUILTIN = {"builtin:power_bank": "Power bank with a simulated internal cell crack (built-in sample)"}


def pretty(stem: str) -> str:
    """'semiconductor_internal_fault' -> 'Semiconductor internal fault'."""
    text = stem.replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:]


def _ai_label(label: str) -> str | None:
    """Unlabelled uploads also go through the AI labeller unless ROOTLENS_AI_LABEL=0 (tests, offline)."""
    return None if os.getenv("ROOTLENS_AI_LABEL", "1") == "0" else label


def _dir(aid: str) -> Path:
    return ASSEMBLY_DIR / Path(aid).name


def content_id(prefix: str, *parts) -> str:
    """Same file (and settings) -> same id, so loading a model twice does not create a second copy."""
    h = hashlib.sha1()
    for p in parts:
        h.update(p.read_bytes() if isinstance(p, Path) else str(p).encode())
    return prefix + h.hexdigest()[:10]


def register(upload: Path, label: str | None = None, aid: str | None = None) -> dict:
    aid = aid or content_id("a_", upload, label or "")
    existing = get(aid)
    if existing:
        return existing
    out = _dir(aid)
    with tempfile.TemporaryDirectory() as tmp:
        prepared = prepare(upload, Path(tmp))
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        if prepared["kind"] == "glb":
            shutil.copyfile(prepared["path"], out / "model.glb")
            model_url = f"/api/assembly/{aid}/model.glb"
        else:
            src_root = prepared["path"].parent
            shutil.copytree(src_root, out / "files")
            model_url = f"/api/assembly/{aid}/files/{prepared['path'].name}"
    manifest = {
        "id": aid, "created": datetime.now().isoformat(timespec="seconds"),
        "label": label or pretty(upload.stem), "source_file": upload.name,
        "source_format": prepared["source_format"], "model_url": model_url,
        **summarize(prepared["doc"], prepared["binary"], ai_label_for=_ai_label(label or pretty(upload.stem))),
    }
    if cloud.CLOUD:
        return _publish(manifest, out)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


TYPES = {".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".bin": "application/octet-stream",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _publish(m: dict, folder: Path) -> dict:
    """Deployed: model files to Storage `assemblies/<id>/`, the manifest to Firestore `assemblies`."""
    aid = m["id"]
    if (folder / "model.glb").exists():
        m["model_url"] = cloud.blob_put(f"assemblies/{aid}/model.glb", folder / "model.glb", TYPES[".glb"])
    else:
        cloud.put_tree(f"assemblies/{aid}/files", folder / "files", TYPES)
        m["model_url"] = cloud.blob_url(f"assemblies/{aid}/files/{m['model_url'].rsplit('/files/', 1)[1]}")
    m.setdefault("mapping", {})
    cloud.record_put("assemblies", aid, m, {"label": m["label"], "source_format": m["source_format"],
                                            "model_url": m["model_url"], "counts": m["counts"]})
    shutil.rmtree(folder, ignore_errors=True)
    return m


def load_builtin(name: str) -> dict:
    if name not in BUILTIN:
        raise ConvertError(f"unknown built-in sample {name}")
    aid = "demo_" + name.split(":", 1)[1]
    existing = get(aid)
    if existing:
        return existing
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "power_bank_sample.glb"
        p.write_bytes(demo.build())
        return register(p, BUILTIN[name], aid=aid)


def get(aid: str) -> dict | None:
    from backend.assembly import remedies
    if cloud.CLOUD:
        m = cloud.record_get("assemblies", aid)
        if m is not None:
            m.setdefault("mapping", {})
        return remedies.attach(m)
    p = _dir(aid) / "manifest.json"
    if not p.exists():
        return None
    m = json.loads(p.read_text())
    mp = _dir(aid) / "mapping.json"
    m["mapping"] = json.loads(mp.read_text()) if mp.exists() else {}
    from backend.assembly import remedies
    return remedies.attach(m)


def listing() -> list[dict]:
    if cloud.CLOUD:
        return [{k: r.get(k) for k in ("id", "created", "label", "source_format", "model_url", "counts")}
                for r in cloud.record_list("assemblies")]
    if not ASSEMBLY_DIR.exists():
        return []
    out = []
    for p in ASSEMBLY_DIR.glob("*/manifest.json"):
        m = json.loads(p.read_text())
        out.append({k: m.get(k) for k in ("id", "created", "label", "source_format", "model_url", "counts")})
    return sorted(out, key=lambda r: r["created"], reverse=True)


def model_file(aid: str, rel: str | None = None) -> Path | None:
    if cloud.CLOUD:
        return None   # served from Storage; the manifest carries the public URL
    base = _dir(aid)
    p = (base / "model.glb") if rel is None else (base / "files" / rel).resolve()
    if rel is not None and (base / "files").resolve() not in p.parents:
        return None
    return p if p.is_file() else None


def samples() -> dict:
    files = [{"name": k, "label": v, "kind": "builtin"} for k, v in BUILTIN.items()]
    if cloud.CLOUD:   # samples/models/... and samples/blender/... uploaded by the seed step
        for b in cloud.blob_list("samples/models/") + cloud.blob_list("samples/blender/"):
            p = Path(b["key"])
            if p.suffix.lower() in (".glb", ".zip"):
                files.append({"name": b["key"].removeprefix("samples/"), "label": pretty(p.stem),
                              "kind": p.suffix.lower().lstrip("."), "size": b["size"]})
        return {"folders": ["Cloud Storage: samples/"], "files": files}
    for root in MODELS_DIRS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() == ".blend" and p.with_suffix(".glb").exists():
                continue                                    # the exported .glb is listed instead
            if p.is_file() and p.suffix.lower() in (".glb", ".blend", ".zip"):
                files.append({"name": f"{root.name}/{p.relative_to(root).as_posix()}", "label": pretty(p.stem),
                              "kind": p.suffix.lower().lstrip("."), "size": p.stat().st_size})
    return {"folders": [str(r) for r in MODELS_DIRS], "files": files}


def sample_path(name: str) -> Path:
    if cloud.CLOUD:
        key = f"samples/{name}"
        if ".." in name or not cloud.blob_exists(key):
            raise ConvertError(f"sample not found: {name}")
        return cloud.blob_get(key, ASSEMBLY_DIR / "_cache" / name)
    top, _, rel = name.partition("/")
    for root in MODELS_DIRS:
        if root.name == top:
            p = (root / rel).resolve()
            if root.resolve() in p.parents and p.is_file():
                return p
    raise ConvertError(f"sample not found: {name}")


def dedupe() -> dict:
    """Remove repeated copies of the same model (same label), keeping the newest."""
    seen, removed = set(), []
    for a in listing():                      # newest first
        if a["label"] in seen:
            removed.append(a["id"])
            if cloud.CLOUD:
                cloud.doc_delete("assemblies", a["id"])
                cloud.blob_delete_prefix(f"assemblies/{a['id']}/")
            else:
                shutil.rmtree(_dir(a["id"]), ignore_errors=True)
        seen.add(a["label"])
    return {"removed": removed}


def set_mapping(aid: str, mapping: dict[str, str | None]) -> dict:
    m = get(aid)
    if m is None:
        raise LookupError("assembly not found")
    parts = {p["name"] for p in m["parts"]}
    clean = {}
    for part, station in mapping.items():
        if part not in parts:
            raise ConvertError(f"unknown part {part}")
        if station in (None, ""):
            continue
        if not STATION_RE.match(station):
            raise ConvertError(f"station must look like L3_S32, got {station}")
        clean[part] = station
    if cloud.CLOUD:
        m["mapping"] = clean
        cloud.record_put("assemblies", aid, m, {"label": m["label"], "source_format": m["source_format"],
                                                "model_url": m["model_url"], "counts": m["counts"]})
        return clean
    (_dir(aid) / "mapping.json").write_text(json.dumps(clean, indent=2))
    return clean


def overlay(aid: str) -> dict:
    """Per part: damage, simulated temperature, and (if mapped) the Bosch station's fail rate."""
    m = get(aid)
    if m is None:
        raise LookupError("assembly not found")
    try:
        bosch = state.json("bosch.json")
    except ArtifactMissing:
        bosch = None
    rates = {r["station"]: r for r in (bosch or {}).get("station_rates", [])}
    ranking = {s["station"]: s for s in (bosch or {}).get("station_ranking", {}).get("stations", [])}
    line_rate = (bosch or {}).get("sample_info", {}).get("true_fail_rate")
    rows = []
    for p in m["parts"]:
        station = m["mapping"].get(p["name"]) or p.get("station")
        r = rates.get(station) if station else None
        rk = ranking.get(station) if station else None
        rows.append({
            "part": p["name"], "display_name": p["display_name"], "role": p["role"],
            "damage": p["damage"], "temp_c": p["temp_c"], "station": station,
            "station_fail_rate": r["fail_rate"] if r else None,
            "station_fail_rate_ci": r["fail_rate_ci"] if r else None,
            "station_vs_line": round(r["fail_rate"] / line_rate, 2) if r and line_rate else None,
            "station_stable_suspect": bool(rk["stable"]) if rk else None,
        })
    return {"id": aid, "parts": rows, "line_fail_rate": line_rate,
            "mapping_label": "Illustrative, user-defined part-to-station mapping. Not derived from data.",
            "note": SIMULATED_NOTE}
