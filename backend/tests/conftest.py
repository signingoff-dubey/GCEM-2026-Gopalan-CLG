import os

# Tests never call an LLM for model labelling; the geometry and name passes still run.
os.environ.setdefault("ROOTLENS_AI_LABEL", "0")
