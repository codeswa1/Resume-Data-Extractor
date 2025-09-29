# tools/schema_mapper.py
"""
Auto-generate mapping from internal keys -> Airtable column names.

Provides:
- suggest_mapping(internal_keys, remote_fields) -> basic suggestions (no scores)
- auto_generate_mapping(internal_keys, remote_fields, thresholds...) -> detailed suggestions with confidence and a simple final mapping
- helpers to load/save mapping files
"""
import re
import json
from difflib import get_close_matches, SequenceMatcher
from typing import List, Dict, Tuple, Any
from pathlib import Path

def _normalize(s: str) -> str:
    if s is None:
        return ""
    # lowercase, remove non-alphanumeric characters
    s = str(s).lower()
    s = re.sub(r"[\W_]+", "", s)  # remove non-alphanumeric
    return s.strip()

def _similarity(a: str, b: str) -> float:
    # use SequenceMatcher ratio on normalized strings
    return SequenceMatcher(None, a, b).ratio()

def suggest_mapping(internal_keys: List[str], remote_fields: List[str]) -> Dict[str, str]:
    """
    Simple mapping suggestion (no scores) — retains earlier behavior.
    """
    remote_norm = {rf: _normalize(rf) for rf in remote_fields}
    remote_by_norm = {v: k for k, v in remote_norm.items()}

    mapping = {}
    for ik in internal_keys:
        ik_norm = _normalize(ik)
        # exact case-insensitive
        found = False
        for rf in remote_fields:
            if rf.lower() == ik.lower():
                mapping[ik] = rf
                found = True
                break
        if found:
            continue
        # normalized exact
        if ik_norm in remote_by_norm:
            mapping[ik] = remote_by_norm[ik_norm]
            continue
        # fuzzy
        choices = list(remote_norm.values())
        matches = get_close_matches(ik_norm, choices, n=1, cutoff=0.6)
        if matches:
            chosen_norm = matches[0]
            mapping[ik] = remote_by_norm.get(chosen_norm, "")
        else:
            mapping[ik] = ""
    return mapping

def _keyword_score(internal: str, remote: str) -> float:
    """
    Boost score if keywords match (email, phone, skill, year, salary).
    Returns a small bonus to add to fuzzy score.
    """
    internal_l = internal.lower()
    remote_l = remote.lower()
    score = 0.0
    kws = [
        ("email", 0.25),
        ("phone", 0.25),
        ("mobile", 0.25),
        ("contact", 0.2),
        ("skill", 0.2),
        ("skillset", 0.2),
        ("year", 0.2),
        ("yrs", 0.18),
        ("experience", 0.2),
        ("salary", 0.2),
        ("pay", 0.15),
        ("amount", 0.12),
    ]
    for kw, bonus in kws:
        if kw in internal_l and kw in remote_l:
            score += bonus
        # also if remote contains token and internal contains similar semantically
        if kw in remote_l and kw in internal_l:
            score += bonus
    return score

def _find_best_candidate(internal: str, remote_fields: List[str]) -> Tuple[str, float, str]:
    """
    Return (best_field_or_empty, score, method)
    method in {"exact","normalized","keyword","fuzzy"}
    """
    ik_norm = _normalize(internal)
    # exact (case-insensitive)
    for rf in remote_fields:
        if rf.lower() == internal.lower():
            return rf, 1.0, "exact"

    # normalized exact
    remote_norm_map = {rf: _normalize(rf) for rf in remote_fields}
    for rf, rn in remote_norm_map.items():
        if rn == ik_norm and rn != "":
            return rf, 0.98, "normalized"

    # keyword heuristic
    keyword_matches = []
    for rf in remote_fields:
        if any(tok in rf.lower() for tok in internal.lower().split()):
            # give a base score from similarity and add keyword bonus
            sim = _similarity(ik_norm, _normalize(rf))
            bonus = _keyword_score(internal, rf)
            keyword_matches.append((rf, min(1.0, sim + bonus), "keyword"))
    if keyword_matches:
        keyword_matches.sort(key=lambda t: t[1], reverse=True)
        return keyword_matches[0]

    # fuzzy
    best = ("", 0.0, "")
    for rf in remote_fields:
        sim = _similarity(ik_norm, _normalize(rf))
        # add small keyword boost
        sim = sim + _keyword_score(internal, rf)
        if sim > best[1]:
            best = (rf, sim, "fuzzy")
    if best[1] > 0:
        return best
    return "", 0.0, ""

def auto_generate_mapping(
    internal_keys: List[str],
    remote_fields: List[str],
    auto_apply_threshold: float = 0.85,
    accept_threshold: float = 0.65,
) -> Dict[str, Any]:
    """
    Generate mapping suggestions with scores and produce a final simplified mapping.

    Returns a dict:
    {
      "suggestions": {
         "name": {"field":"Full Name", "score":0.98, "method":"normalized"},
         ...
      },
      "final_mapping": { "name": "Full Name", ... }  # only one-to-one mapping
      "summary": {"min_score": 0.90, "avg_score": 0.93, "all_mapped": True/False}
    }
    """
    # build candidate list
    candidates = {}
    for ik in internal_keys:
        field, score, method = _find_best_candidate(ik, remote_fields)
        candidates[ik] = {"field": field or "", "score": round(float(score), 3), "method": method}

    # Resolve collisions: ensure one remote field maps to only one internal key. If collisions occur,
    # keep the mapping with higher score and unset others.
    field_to_iks: Dict[str, List[Tuple[str, float]]] = {}
    for ik, info in candidates.items():
        fld = info["field"]
        if not fld:
            continue
        field_to_iks.setdefault(fld, []).append((ik, info["score"]))

    # For each field with multiple iks, keep highest score
    for fld, iks in field_to_iks.items():
        if len(iks) <= 1:
            continue
        # sort by score desc
        iks_sorted = sorted(iks, key=lambda t: t[1], reverse=True)
        # keep the first, unset rest
        keep_ik = iks_sorted[0][0]
        for ik, _ in iks_sorted[1:]:
            candidates[ik]["field"] = ""
            candidates[ik]["score"] = 0.0
            candidates[ik]["method"] = "conflict"

    # Build final_mapping only including suggestions that meet accept_threshold
    final_mapping = {}
    scores = []
    for ik, info in candidates.items():
        scores.append(info["score"])
        if info["field"] and info["score"] >= accept_threshold:
            final_mapping[ik] = info["field"]

    summary = {
        "min_score": min(scores) if scores else 0.0,
        "avg_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "all_mapped": all((candidates[ik]["field"] and candidates[ik]["score"] >= accept_threshold) for ik in internal_keys)
    }

    return {"suggestions": candidates, "final_mapping": final_mapping, "summary": summary}

def load_mapping_file(path: str) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mapping file not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))

def save_mapping_file(mapping: Dict[str, str], path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
