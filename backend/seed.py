"""First-start seeding for the deployed API: copies the analysis results and sample files that ship with
the function into Firestore and Cloud Storage, so every row the dashboard shows is read from Firebase.

Runs from the function itself (its service account already has access), once per content version:
the version is a hash of what ships, so a redeploy with new results seeds again.
"""
import hashlib
import json
import logging
import threading
from pathlib import Path

from backend import cloud
from backend.config import ROOT

SEED_DIR = ROOT / "seed"          # filled by scripts/build_functions.py
ARTIFACTS = ROOT / "artifacts"
TYPES = {".glb": "model/gltf-binary", ".obj": "text/plain", ".ply": "application/octet-stream",
         ".stl": "model/stl", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".zip": "application/zip"}
CORS = [{"origin": ["*"], "method": ["GET", "HEAD"], "responseHeader": ["Content-Type", "Range"], "maxAgeSeconds": 3600}]
_done = threading.Event()
_lock = threading.Lock()
log = logging.getLogger("rootlens.seed")


def _files() -> list[tuple[str, Path]]:
    """(storage key, local file) for every sample that ships with the function."""
    out = []
    for sub, prefix in (("scans", "samples/scans"), ("blender", "samples/blender"), ("models", "samples/models")):
        folder = SEED_DIR / sub
        if folder.exists():
            out += [(f"{prefix}/{p.relative_to(folder).as_posix()}", p) for p in sorted(folder.rglob("*")) if p.is_file()]
    return out


def version() -> str:
    h = hashlib.sha1()
    for p in sorted(ARTIFACTS.glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    for key, p in _files():
        h.update(f"{key}:{p.stat().st_size}".encode())
    return h.hexdigest()[:16]


def run() -> dict:
    v = version()
    n_art = 0
    for p in sorted(ARTIFACTS.glob("*.json")):
        cloud.doc_set("artifacts", p.stem, {"json": p.read_text(encoding="utf-8"), "file": p.name})
        n_art += 1
    files = _files()
    for key, p in files:
        cloud.blob_put(key, p, TYPES.get(p.suffix.lower(), "application/octet-stream"))
    b = cloud.bucket()
    b.cors = CORS                    # the browser loads models and photos straight from Storage
    b.patch()
    cloud.doc_set("meta", "seed", {"version": v, "artifacts": n_art, "files": len(files)})
    return {"version": v, "artifacts": n_art, "files": len(files)}


def ensure() -> None:
    """Seed once per instance start if Firestore holds an older version."""
    if _done.is_set() or not cloud.CLOUD:
        return
    with _lock:
        if _done.is_set():
            return
        current = (cloud.doc_get("meta", "seed") or {}).get("version")
        if current != version():
            log.info("seeding Firebase: %s", json.dumps(run()))
        _done.set()
