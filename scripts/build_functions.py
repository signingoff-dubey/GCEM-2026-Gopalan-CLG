"""Assemble functions/ for `firebase deploy` (runs as the predeploy hook).

Copies the API code, the analysis results, the SECOM archive and the sample models into functions/, and
writes functions/.env with only the keys the API needs (never committed). Run: python scripts/build_functions.py
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FN = ROOT / "functions"
ENV_KEYS = ("GROQ_API_KEY", "GEMINI_API_KEY", "GROQ_APP_", "GEMINI_APP_", "OPENROUTER_API_KEY", "OPENROUTER_VISION_MODEL", "SARVAM_",
            "ALERT_", "TWILIO_", "SMTP_")
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "tests")


def copy_tree(src: Path, dst: Path) -> None:
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=SKIP)


def copy_files(files, dst: Path, base: Path) -> int:
    n = 0
    for p in files:
        target = dst / p.relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        n += 1
    return n


def main() -> None:
    copy_tree(ROOT / "backend", FN / "backend")
    copy_tree(ROOT / "config", FN / "config")

    art = FN / "artifacts"
    shutil.rmtree(art, ignore_errors=True)
    art.mkdir()
    missing = [n for n in ("model.pkl", "metrics.json") if not (ROOT / "artifacts" / n).exists()]
    if missing:
        raise SystemExit(f"artifacts missing ({', '.join(missing)}): run `make train` first")
    for p in (ROOT / "artifacts").iterdir():
        if p.suffix in (".json", ".pkl"):
            shutil.copy2(p, art / p.name)

    (FN / "datasets").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "datasets" / "secom.zip", FN / "datasets" / "secom.zip")

    seed = FN / "seed"
    shutil.rmtree(seed, ignore_errors=True)
    scans = ROOT / "data" / "scans"
    n = copy_files([p for p in scans.rglob("*") if p.is_file()] if scans.exists() else [], seed / "scans", scans)
    blender = ROOT / "assets" / "blender"
    n += copy_files(sorted(blender.rglob("*.glb")), seed / "blender", blender)
    for models in (ROOT / "datasets" / "models", ROOT / "data" / "models"):
        if models.exists():
            n += copy_files([p for p in models.rglob("*") if p.suffix.lower() in (".glb", ".zip")], seed / "models", models)

    lines = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip()
            if "=" in line and not line.lstrip().startswith("#") and key.startswith(ENV_KEYS):
                lines.append(line.strip())
    (FN / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"functions/ ready: backend, {len(list(art.iterdir()))} artifacts, {n} sample files, {len(lines)} env keys")


if __name__ == "__main__":
    main()
