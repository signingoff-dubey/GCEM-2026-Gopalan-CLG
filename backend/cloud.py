"""Firebase storage for the deployed API: rows in Firestore, files in Cloud Storage.

Locally (ROOTLENS_STORE unset) nothing here runs and every module keeps its files under data/.
On Cloud Functions ROOTLENS_STORE=firebase, and the services call these helpers instead:
- docs: one Firestore document per capture, inspection, model, alert setting or analysis artifact;
- blobs: models, photos and scan outputs in the project's default bucket, publicly readable
  (storage.rules) so the browser can load them straight from Storage.
Credentials come from the function's own service account; nothing is stored in the code.
"""
import os
import urllib.parse
from functools import lru_cache
from pathlib import Path

CLOUD = os.getenv("ROOTLENS_STORE") == "firebase"


@lru_cache(maxsize=1)
def _app():
    import firebase_admin
    bucket = os.getenv("ROOTLENS_BUCKET") or f"{os.getenv('GCLOUD_PROJECT', 'rootlens-hb')}.firebasestorage.app"
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(options={"storageBucket": bucket})


def db():
    from firebase_admin import firestore
    return firestore.client(_app())


def bucket():
    from firebase_admin import storage
    return storage.bucket(app=_app())


# ---------- documents ----------
def doc_get(col: str, did: str) -> dict | None:
    snap = db().collection(col).document(did).get()
    return snap.to_dict() if snap.exists else None


def doc_set(col: str, did: str, data: dict, merge: bool = False) -> None:
    db().collection(col).document(did).set(data, merge=merge)


def doc_add(col: str, data: dict) -> None:
    db().collection(col).add(data)


def doc_delete(col: str, did: str) -> None:
    db().collection(col).document(did).delete()


def doc_list(col: str, order: str = "created", limit: int = 500, fields: list[str] | None = None) -> list[dict]:
    from google.cloud.firestore_v1 import Query
    q = db().collection(col).order_by(order, direction=Query.DESCENDING).limit(limit)
    if fields:
        q = q.select(fields)
    return [d.to_dict() for d in q.stream()]


# ---------- files ----------
def blob_url(key: str) -> str:
    """Public download URL (storage.rules allow reads); the browser fetches it directly."""
    b = bucket().name
    return f"https://firebasestorage.googleapis.com/v0/b/{b}/o/{urllib.parse.quote(key, safe='')}?alt=media"


def blob_put(key: str, src: Path | bytes, content_type: str = "application/octet-stream") -> str:
    blob = bucket().blob(key)
    if isinstance(src, bytes | bytearray):
        blob.upload_from_string(bytes(src), content_type=content_type)
    else:
        blob.upload_from_filename(str(src), content_type=content_type)
    return blob_url(key)


def blob_get(key: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        bucket().blob(key).download_to_filename(str(dest))
    return dest


def blob_delete_prefix(prefix: str) -> int:
    blobs = list(bucket().list_blobs(prefix=prefix))
    for b in blobs:
        b.delete()
    return len(blobs)


def blob_list(prefix: str) -> list[dict]:
    return [{"key": b.name, "size": b.size} for b in bucket().list_blobs(prefix=prefix) if not b.name.endswith("/")]


def blob_exists(key: str) -> bool:
    return bucket().blob(key).exists()


def put_tree(prefix: str, folder: Path, types: dict[str, str]) -> None:
    """Upload every file of a folder under prefix/ (e.g. a model with its textures)."""
    for p in folder.rglob("*"):
        if p.is_file():
            blob_put(f"{prefix}/{p.relative_to(folder).as_posix()}", p, types.get(p.suffix.lower(), "application/octet-stream"))


# ---------- records: queryable summary fields + the full JSON (Firestore has no nested arrays) ----------
def record_put(col: str, rid: str, record: dict, summary: dict) -> None:
    import json
    doc_set(col, rid, {**summary, "id": rid, "created": record.get("created"), "payload": json.dumps(record, default=str)})


def record_get(col: str, rid: str) -> dict | None:
    import json
    d = doc_get(col, rid)
    return json.loads(d["payload"]) if d and d.get("payload") else None


def record_list(col: str, limit: int = 500) -> list[dict]:
    """Summaries only (the payload is not read back)."""
    from google.cloud.firestore_v1 import Query
    q = db().collection(col).order_by("created", direction=Query.DESCENDING).limit(limit)
    return [{k: v for k, v in d.to_dict().items() if k != "payload"} for d in q.stream()]
