"""Paths and global constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SECOM_DIR = DATA_DIR / "secom"
SECOM_ZIP = ROOT / "datasets" / "secom.zip"
BOSCH_DIR = DATA_DIR / "bosch"
ARTIFACTS_DIR = ROOT / "artifacts"
CAPTURES_DIR = DATA_DIR / "captures"
SCANS_DIR = DATA_DIR / "scans"
INSPECTION_DIR = DATA_DIR / "inspection"

SEED = 42

# worker processes for bootstrap / permutation refits; each LightGBM fit then uses 1 thread
import os as _os
N_JOBS = int(_os.getenv("ROOTLENS_JOBS", max(1, min((_os.cpu_count() or 2) - 2, 16))))

# time split fractions (train, val, test) — no shuffling
SPLIT_FRACTIONS = (0.70, 0.15, 0.15)

# missing-data thresholds
MAX_MISSING_FRAC = 0.60
FLAG_MISSING_FRAC = 0.05

# ranking
N_BOOTSTRAP = 50
N_PERMUTATIONS = 20
NULL_PERCENTILE = 99.9
TOP_K = 10
STABLE_FREQ = 0.70
CORR_GROUP_THRESHOLD = 0.80

# safe window
WINDOW_LOW_PCT = 5
WINDOW_HIGH_PCT = 95
MIN_BIN_SUPPORT = 30
N_BINS = 5

DISCLAIMER = "Association-based estimate, not proven cause."
