"""Retrieval for the AI assistant (context engineering for Groq and Gemini).

Before a question goes to the model, the most relevant passages from RootLens's own knowledge are retrieved and
handed over as numbered sources [S1], [S2] ... The model is told to cite them. Numbers in retrieved passages count
as evidence for the number guard, like tool results.

Knowledge base, rebuilt whenever the analysis results change:
- the corrective windows and why each is or is not recommended; the ranking; stations to start with;
- how data was cleaned (missing values, outliers, train-only) and how drift is handled;
- validation results; the honesty rules the answers follow;
- the defect reference (causes, checks, fixes per defect type);
- the latest inspected 3D model or scan and its damaged parts.

Retrieval is TF-IDF with word 1-2 grams and cosine similarity (scikit-learn): no extra service or key, the same
in the cloud and on a laptop, and fast on a few hundred passages.
"""
import hashlib
import json
import threading

from backend.api.state import ArtifactMissing, state

TOP_K = 6
_SUFFIXES = ("ations", "ation", "ing", "ness", "ed", "es", "ly", "s")


def _stem(word: str) -> str:
    """Tiny suffix stripper so 'drifting', 'drifted' and 'drift' meet (no extra dependency)."""
    for suf in _SUFFIXES:
        if len(word) > len(suf) + 3 and word.endswith(suf):
            return word[: -len(suf)]
    return word


def _analyze(text: str) -> list[str]:
    import re
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    words = [_stem(w) for w in re.findall(r"[a-z0-9_]+", text.lower()) if w not in ENGLISH_STOP_WORDS]
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]
_lock = threading.Lock()
_cache = {"key": None, "docs": None, "vec": None, "mat": None}

RULES = [
    "RootLens ranks statistically suspected drivers, stability-checked over 50 bootstrap refits; it never claims a "
    "root cause is proven. The data is anonymised and observational; a pilot on the line confirms a change.",
    "Model quality is reported as PR-AUC and MCC on a later held-out time window, never accuracy, because failures are rare.",
    "Corrective values always stay inside the range the line has already run (5th to 95th percentile).",
    "Savings are always a low-to-high range labelled model estimate. Anything from the model scoring its own suggestion is model-estimated.",
    "SECOM sensors (F33, F59 ...) are anonymised: never say what they physically measure.",
    "Inspection (3D models and scans) is a separate capability: it does not feed the ranking, windows or savings. "
    "Temperatures in the 3D view are simulated. Damage comes from rootlens tags, object names, a geometry check "
    "against identical sibling parts, or AI suggestions marked unverified.",
]


def _art(name):
    try:
        return state.json(name)
    except ArtifactMissing:
        return None


def _docs() -> list[dict]:
    docs = [{"source": "honesty rules", "text": t} for t in RULES]
    from backend.api.solutions import solutions
    sol = solutions()
    for s in sol["line"]:
        docs.append({"boost": 1.6 if s["do"] else 1.0, "source": f"corrective window {s['parameter']}",
                     "text": f"What to change on the line, fix, action for {s['parameter']}: {s['action']}. {'Recommended' if s['do'] else 'Not recommended: ' + str(s['reason_not'])}. "
                             f"{s['why']} Next step: {s['next_step']}."})
    for s in sol["stations"]:
        docs.append({"source": f"Bosch station {s['station']}",
                     "text": f"Where to start on the Bosch line: {s['action']}. Fail rate {s['fail_rate']}, {s['vs_line']} times the line average."})
    r = _art("ranking.json")
    if r:
        top = r.get("features", [])[:10]
        docs.append({"source": "ranking", "text": "Ranked suspected parameters: " + "; ".join(
            f"{f['feature']} mean rank {f.get('mean_rank')} {'stable' if f.get('stable') else 'unstable'}" for f in top)})
    dq = _art("data_quality.json")
    if dq:
        docs.append({"source": "data cleaning", "text": " ".join(dq["steps"])})
        sc = dq["shape_check"]
        docs.append({"source": "data cleaning check", "text":
                     f"After cleaning, sensor means moved by a median of {sc['median_mean_shift_sd']} standard deviations "
                     f"and kept {sc['median_std_ratio']} of their spread, across {sc['features']} sensors."})
    d = _art("drift.json")
    if d:
        rep, ex = d["report"], d["experiment"]
        docs.append({"source": "drift", "text":
                     f"SECOM runs were recorded from {rep['data_period']['first_run']} to {rep['data_period']['last_run']}. "
                     f"Train and test windows are separable with AUC {round(rep['adversarial']['auc'], 3)}; "
                     f"{rep['sensors_shifted_psi_gt_0_25']} of {rep['sensors_checked']} sensors shifted. "
                     "Data drift, distribution shift and process change are handled by a time-only split, re-checking windows on the later test window and rolling-origin evaluation."})
        docs.append({"source": "drift experiment", "text": ex["decision"] + " " + ex["note"]})
    v = _art("planted_benchmark.json")
    if v:
        docs.append({"source": "validation", "text": "Planted-fault benchmark: RootLens versus naive SHAP ranking. " +
                     json.dumps(v.get("summary", v))[:600]})
    from backend.assembly import remedies
    for keys, e in remedies.TABLE:
        docs.append({"source": f"defect reference: {keys[0]}", "text":
                     f"{', '.join(keys)} defects ({e['stage']}). Causes: {'; '.join(e['causes'])}. "
                     f"Check: {'; '.join(e['checks'])}. Fix: {'; '.join(e['actions'])}."})
    from backend.ai.tools import get_latest_inspection
    li = get_latest_inspection()
    if li.get("damage"):
        for dmg in li["damage"]:
            docs.append({"source": f"latest inspection {li['label']}", "text":
                         f"{dmg['display_name']} in {li['label']}: {dmg['type']}, severity {dmg['severity']}"
                         f"{', internal' if dmg.get('internal') else ''}. {dmg.get('description') or ''} "
                         f"Found by {dmg.get('source') or 'tags'}. Fix: {'; '.join(dmg.get('fix') or [])}."})
    return docs


def _index():
    docs = _docs()
    key = hashlib.sha1(json.dumps(docs, sort_keys=True, default=str).encode()).hexdigest()
    with _lock:
        if _cache["key"] != key:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vec = TfidfVectorizer(analyzer=_analyze, sublinear_tf=True)
            _cache.update(key=key, docs=docs, vec=vec, mat=vec.fit_transform([f"{d['source']} {d['text']}" for d in docs]))
        return _cache["docs"], _cache["vec"], _cache["mat"]


def retrieve(question: str, k: int = TOP_K) -> list[dict]:
    docs, vec, mat = _index()
    scores = (mat @ vec.transform([question]).T).toarray().ravel() * [d.get("boost", 1.0) for d in docs]
    order = scores.argsort()[::-1]
    picked = [i for i in order[:k] if scores[i] > 0] or list(order[:2])
    rules = [i for i, d in enumerate(docs) if d["source"] == "honesty rules"][:1]   # always remind the rules
    return [{"id": f"S{n + 1}", **{k: v for k, v in docs[i].items() if k != "boost"}, "score": round(float(scores[i]), 3)}
            for n, i in enumerate(dict.fromkeys(picked + rules))]


def context_message(question: str) -> tuple[dict, list[dict]]:
    hits = retrieve(question)
    body = "\n".join(f"[{h['id']}] ({h['source']}) {h['text']}" for h in hits)
    return ({"role": "system", "content":
             "Retrieved RootLens context for this question. Use it for explanations and fixes and cite it as [S1], [S2]. "
             "Prefer tool results for numbers; if the context and a tool disagree, the tool wins.\n" + body}, hits)
