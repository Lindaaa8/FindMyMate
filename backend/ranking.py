"""AI compatibility ranking for Discover.

Must-match requirements (see meets_requirements): gender, age range, minimum height, minimum education,
ethnicity, and nothing from "Not want" in their profile.

Discover order (no duplicates):
  1. Two-way matches: they meet your must-match requirements AND you meet theirs,
     ranked by two-way compatibility = average of your score for them and their score for you.
  2. Matches your requirements only: they meet your requirements but you don't meet theirs,
     ranked by your compatibility score for them.
People who don't meet your must-match requirements are not shown.

The compatibility score (0-100) blends:
  bio & hobby text similarity (TF-IDF cosine), shared hobbies, your "Other requirement" terms,
  location, MBTI fit, age fit, education / ethnicity / occupation preferences, verification,
  minus a penalty for your "Not want" items.
"""
import math
import re
from collections import Counter

STOPWORDS = set("""a an and are as at be but by for from has have i i'm im in is it its love loves me my of on or our
so that the their them they this to too very we what when who will with you your yours am been being do does just
like looking someone something who whom more most can get got make makes than then also really much many""".split())

WEIGHTS = {
    "text": 0.22, "hobbies": 0.14, "other": 0.16, "location": 0.10, "mbti": 0.10,
    "age": 0.10, "prefs": 0.12, "verified": 0.06,
}

REGIONS = {
    "west coast": ("ca", "california", "or", "oregon", "wa", "washington", "san francisco", "los angeles", "seattle",
                   "portland", "san diego", "vancouver", "bc"),
    "east coast": ("ny", "new york", "nj", "ma", "boston", "dc", "philadelphia", "pa", "ct", "miami", "fl"),
    "canada": ("toronto", "vancouver", "montreal", "ottawa", "calgary", "on", "bc", "qc", "canada"),
    "europe": ("london", "uk", "paris", "berlin", "madrid", "amsterdam", "europe"),
}

OCCUPATION_GROUPS = {
    "tech": ("engineer", "developer", "software", "data", "analyst", "product", "designer", "it", "programmer", "scientist"),
    "creative": ("designer", "writer", "editor", "artist", "architect", "photographer", "musician", "creative"),
    "professional": ("doctor", "lawyer", "consultant", "accountant", "manager", "physician", "dentist"),
    "finance": ("finance", "banker", "analyst", "consultant", "accountant", "investment"),
    "design": ("designer", "architect", "ux", "product"),
}


# ------------------------------------------------------------------ text ---

def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z'-]+", (text or "").lower())
    out = []
    for w in words:
        w = w.strip("'-")
        if len(w) < 3 or w in STOPWORDS:
            continue
        for suf in ("ing", "es", "s"):  # tiny stemmer: hiking -> hik, dogs -> dog
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def build_idf(docs: list[list[str]]) -> dict[str, float]:
    n = len(docs) or 1
    df = Counter(t for d in docs for t in set(d))
    return {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}


def tfidf(doc: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(doc)
    return {t: c * idf.get(t, 1.0) for t, c in tf.items()}


def cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(t, 0.0) for t, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


# --------------------------------------------------------------- helpers ---

def parse_age_range(text):
    if not text:
        return None
    m = re.search(r"(\d{1,2})\s*(?:-|–|—|to)+\s*(\d{1,2})", str(text), re.I)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > 0 and b > 0:
            return min(a, b), max(a, b)
    m = re.search(r"(\d{1,2})", str(text))
    if m:
        a = int(m.group(1))
        return a - 2, a + 2
    return None


def age_of(p) -> int | None:
    try:
        return int(str(p.get("age", "")).strip())
    except ValueError:
        return None


def split_list(text: str) -> list[str]:
    return [s.strip().lower() for s in re.split(r"[,/;]| or ", text or "") if s.strip()]


def is_no_pref(text: str) -> bool:
    t = (text or "").strip().lower()
    return not t or t in {"no preference", "any", "anyone", "open", "none", "n/a"}


def place_parts(loc: str) -> tuple[str, str]:
    parts = [p.strip().lower() for p in (loc or "").split(",")]
    return (parts[0] if parts else ""), (parts[-1] if len(parts) > 1 else "")


def in_region(loc: str, region_text: str) -> bool:
    loc_l = f" {(loc or '').lower().replace(',', ' ')} "
    for want in split_list(region_text):
        if want in loc_l:
            return True
        for key in REGIONS.get(want, ()):
            if f" {key} " in loc_l:
                return True
    return False


# ---------------------------------------------------------- requirements ---

EDU_PATTERNS = [
    (4, r"\b(ph\.?\s?d|doctor(?:'s|s)?|doctorate|doctoral|dphil|md|edd|dba)\b"),
    (3, r"\b(master(?:'s|s)?|msc|m\.sc|meng|mba|ma|ms|mfa|llm|mph|mpa|med)\b"),
    (2, r"\b(bachelor(?:'s|s)?|bsc|b\.sc|ba|bs|beng|bfa|bba|undergrad(?:uate)?)\b"),
    (1, r"\b(college|diploma|associate|high school|secondary)\b"),
]
NEGATIONS = {"non", "no", "not", "never", "don't", "dont", "doesn't", "doesnt", "without", "anti", "zero"}


def education_level(text: str) -> int:
    """0 = unknown, 1 = high school/college, 2 = Bachelor's, 3 = Master's, 4 = Doctor's (PhD, MD...)."""
    t = (text or "").lower()
    for level, pattern in EDU_PATTERNS:
        if re.search(pattern, t):
            return level
    return 0


def height_cm(text) -> float | None:
    """Height in centimetres. Plain numbers 100-250 are cm (what the height fields ask for); older values like
    5'9 / 5 ft 9 / 6.16 (decimal feet) / 66 (inches) are converted. None if unknown."""
    t = str(text or "").strip().lower()
    if not t:
        return None
    m = re.search(r"(\d)\s*(?:'|’|ft|feet|foot)\s*(\d{1,2}(?:\.\d+)?)?", t)
    if m:
        return (int(m.group(1)) * 12 + float(m.group(2) or 0)) * 2.54
    m = re.search(r"\d+(?:\.\d+)?", t)
    if m:
        n = float(m.group(0))
        if 100 <= n <= 250:
            return n                   # centimetres
        if 3 <= n < 9:
            return n * 12 * 2.54       # decimal feet, e.g. 6.16
        if 36 <= n < 100:
            return n * 2.54            # inches (older entries)
    return None


def min_height_cm(text) -> float | None:
    """Minimum of a requirement like "5'4 - 6'0" or "5'6+" (the first height listed)."""
    t = str(text or "")
    if is_no_pref(t):
        return None
    first = re.split(r"\s*(?:-|–|—|to)\s*(?=\d)", t, maxsplit=1)[0]
    return height_cm(first)


def profile_text(p: dict) -> str:
    """Everything a candidate wrote about themselves (introduction and profile data)."""
    return " ".join(str(p.get(k) or "") for k in (
        "bio", "hobbies", "career", "education", "faith", "nationality", "hometown", "location", "ethnicity", "skin"))


def mentions_unwanted(seeker: dict, other: dict) -> str | None:
    """The first item from the seeker's "Not want" list that appears in the other person's profile, else None.
    A mention preceded by a negation ("non-smoker", "never smoke", "no drugs") doesn't count."""
    words = re.findall(r"[a-z][a-z'-]*", profile_text(other).lower())
    for item in split_list(seeker.get("ideal", {}).get("notWant")):
        if is_no_pref(item):
            continue
        roots = tokens(item) or [w for w in re.findall(r"[a-z][a-z'-]+", item.lower())]
        # "smoker" / "drinker" should also catch "smoke", "smoking", "drinks"...
        roots = [r[:-2] if r.endswith("er") and len(r) > 5 else r for r in roots]
        if not roots:
            continue

        def present(root):
            for i, w in enumerate(words):
                if w.startswith("non-") or w.startswith("anti-"):
                    continue
                if w == root or (len(root) >= 4 and w.startswith(root)):
                    prev = words[i - 1] if i else ""
                    prev2 = words[i - 2] if i > 1 else ""
                    if prev not in NEGATIONS and prev2 not in NEGATIONS:
                        return True
            return False

        if all(present(r) for r in roots):
            return item
    return None


def ethnicity_ok(seeker: dict, other: dict) -> bool:
    wanted = seeker.get("ideal", {}).get("ethnicity")
    if is_no_pref(wanted):
        return True
    theirs = (other.get("ethnicity") or "").strip().lower()
    if not theirs:          # candidate didn't say -> not excluded
        return True
    return any(w in theirs or theirs in w for w in split_list(wanted))


EDU_NAMES = {1: "high school / college", 2: "Bachelor's", 3: "Master's", 4: "Doctor's"}


def _fmt_height(cm: float) -> str:
    return f"{round(cm)} cm"


def requirement_report(seeker: dict, other: dict) -> list[str]:
    """Which of `seeker`'s must-match requirements does `other` miss? Empty list = meets them all.

    gender = Looking for · age within range · height >= the listed minimum · education >= the listed level ·
    ethnicity in the listed ones · nothing from "Not want" in their profile.
    Requirements left blank / "No preference" are skipped; a candidate who left height, education or
    ethnicity blank is not excluded for it.
    """
    ideal = seeker.get("ideal", {})
    missed = []
    pref = (ideal.get("genderPreference") or "").strip()
    if pref and pref.lower() != (other.get("gender") or "").strip().lower():
        missed.append(f"Gender {other.get('gender') or 'not given'} — you're looking for {pref}")
    rng = parse_age_range(ideal.get("age"))
    if rng:
        a = age_of(other)
        if a is None or not rng[0] <= a <= rng[1]:
            missed.append(f"Age {a if a is not None else 'not given'} — you want {rng[0]}–{rng[1]}")
    min_h = min_height_cm(ideal.get("height"))
    if min_h is not None:
        h = height_cm(other.get("height"))
        if h is not None and h + 0.25 < min_h:   # small tolerance for rounding
            missed.append(f"Height {_fmt_height(h)} — you want at least {_fmt_height(min_h)}")
    if not is_no_pref(ideal.get("education")):
        need = education_level(ideal.get("education"))
        have = education_level(other.get("education"))
        if need and have and have < need:
            missed.append(f"Education {EDU_NAMES[have]} — you want {EDU_NAMES[need]} or above")
    if not ethnicity_ok(seeker, other):
        missed.append(f"Ethnicity {other.get('ethnicity')} — you listed {ideal.get('ethnicity')}")
    unwanted = mentions_unwanted(seeker, other)
    if unwanted:
        missed.append(f"Profile mentions “{unwanted}”, which is on your Not want list")
    return missed


def meets_requirements(seeker: dict, other: dict) -> bool:
    """Does `other` meet ALL of `seeker`'s must-match requirements? (see requirement_report)"""
    return not requirement_report(seeker, other)


# ----------------------------------------------------------------- score ---

def _other_requirement(seeker, cand_text: str) -> tuple[float | None, list[str]]:
    """Fraction of the seeker's comma-separated "Other requirement" terms the candidate satisfies.

    "no X" / "not X" / "non-X" are satisfied when X is not mentioned; other terms when mentioned.
    """
    terms = split_list(seeker.get("ideal", {}).get("otherRequirement"))
    if not terms:
        return None, []
    cand_tokens = set(tokens(cand_text))
    met, positive = 0, []
    for term in terms:
        negative = re.match(r"^(no|not|non)[\s-]+(.*)$", term)
        if negative:
            if not cand_tokens & set(tokens(negative.group(2))):
                met += 1
        elif cand_tokens & set(tokens(term)):
            met += 1
            positive.append(term)
    return met / len(terms), positive


def _mbti(seeker, cand) -> tuple[float | None, bool]:
    """MBTI letter compatibility (MBTI is no longer part of the Ideal partner questionnaire)."""
    c = (cand.get("mbti") or "").upper().strip()
    s = (seeker.get("mbti") or "").upper().strip()
    if len(c) != 4 or len(s) != 4:
        return None, False
    score = 0.4 * (s[1] == c[1]) + 0.2 * (s[2] == c[2]) + 0.2 * (s[3] == c[3]) + 0.2 * (s[0] != c[0])
    return score, False


def _prefs(seeker, cand) -> tuple[float | None, list[str]]:
    ideal = seeker.get("ideal", {})
    parts, notes = [], []
    if not is_no_pref(ideal.get("education")):
        need = education_level(ideal["education"]) or 2
        have = education_level(cand.get("education"))
        ok = have >= need
        parts.append(1.0 if ok else 0.3)
        if ok and have >= 3:
            notes.append("education fits")
    if not is_no_pref(ideal.get("ethnicity")):
        eth = (cand.get("ethnicity") or "").lower()
        ok = any(e in eth for e in split_list(ideal["ethnicity"])) if eth else False
        parts.append(1.0 if ok else 0.2)
    if not is_no_pref(ideal.get("occupation")):
        career = (cand.get("career") or "").lower()
        ok = False
        for want in split_list(ideal["occupation"]):
            if want in career or any(k in career for k in OCCUPATION_GROUPS.get(want, ())):
                ok = True
        parts.append(1.0 if ok else 0.3)
        if ok:
            notes.append(f"{cand.get('career')} fits your occupation preference")
    return (sum(parts) / len(parts) if parts else None), notes


def score(seeker: dict, cand: dict, idf: dict) -> tuple[float, list[str]]:
    """One-directional compatibility of `cand` for `seeker`, 0-1, with human-readable reasons."""
    s_text = f"{seeker.get('bio', '')} {seeker.get('hobbies', '')}"
    c_text = f"{cand.get('bio', '')} {cand.get('hobbies', '')} {cand.get('career', '')}"
    factors: dict[str, float] = {}
    reasons: list[tuple[float, str]] = []

    sim = cosine(tfidf(tokens(s_text), idf), tfidf(tokens(c_text), idf))
    factors["text"] = min(1.0, sim * 2.5)
    if factors["text"] >= 0.5:
        reasons.append((factors["text"] * WEIGHTS["text"], "Similar values and interests in your bios"))

    s_h = set(tokens(seeker.get("hobbies", "")))
    c_h = set(tokens(cand.get("hobbies", ""))) | set(tokens(cand.get("bio", "")))
    if s_h:
        shared = s_h & c_h
        factors["hobbies"] = min(1.0, len(shared) / max(1, min(len(s_h), 3)))
        if shared:
            names = [h.strip() for h in seeker.get("hobbies", "").split(",")
                     if set(tokens(h)) & shared][:2]
            reasons.append((factors["hobbies"] * WEIGHTS["hobbies"], f"Shared interests: {', '.join(names) or ', '.join(sorted(shared)[:2])}"))

    other, met = _other_requirement(seeker, c_text)
    if other is not None:
        factors["other"] = other
        if met:
            reasons.append((other * WEIGHTS["other"], f"Matches your “{met[0]}”"))

    s_city, s_area = place_parts(seeker.get("location"))
    c_city, c_area = place_parts(cand.get("location"))
    loc = 0.3
    if s_city and s_city == c_city:
        loc = 1.0
        reasons.append((WEIGHTS["location"], f"Also in {cand.get('location')}"))
    elif s_area and s_area == c_area:
        loc = 0.7
    if not is_no_pref(seeker.get("ideal", {}).get("location")) and in_region(cand.get("location"), seeker["ideal"]["location"]):
        loc = max(loc, 0.9)
        if loc < 1.0:
            reasons.append((0.9 * WEIGHTS["location"], f"In your preferred area ({seeker['ideal']['location']})"))
    factors["location"] = loc

    mb, listed = _mbti(seeker, cand)
    if mb is not None:
        factors["mbti"] = mb
        if listed:
            reasons.append((WEIGHTS["mbti"], f"{cand.get('mbti')} is on your MBTI list"))

    rng = parse_age_range(seeker.get("ideal", {}).get("age"))
    a = age_of(cand)
    if rng and a is not None:
        mid, half = (rng[0] + rng[1]) / 2, max(1, (rng[1] - rng[0]) / 2)
        factors["age"] = max(0.0, 1 - 0.5 * abs(a - mid) / half)

    prefs, notes = _prefs(seeker, cand)
    if prefs is not None:
        factors["prefs"] = prefs
        for n in notes[:1]:
            reasons.append((prefs * WEIGHTS["prefs"] * 0.8, n[0].upper() + n[1:]))

    # Education verification is not part of matching; only the selfie and relationship-status checks count.
    factors["verified"] = (bool(cand.get("photoVerified")) + bool(cand.get("marriageVerified"))) / 2

    total_w = sum(WEIGHTS[k] for k in factors)
    raw = sum(WEIGHTS[k] * v for k, v in factors.items()) / total_w if total_w else 0.0

    # "Not want" penalties
    penalty = 0.0
    c_lower = c_text.lower()
    for item in split_list(seeker.get("ideal", {}).get("notWant")):
        if "smok" in item and re.search(r"(?<!non-)(?<!non )smok", c_lower):
            penalty += 0.15
        elif "long" in item and "distance" in item and loc < 0.7:
            penalty += 0.10
        elif not any(k in item for k in ("smok", "distance")) and any(t in tokens(c_lower) for t in tokens(item)):
            penalty += 0.10
    raw = max(0.0, raw - penalty)

    reasons.sort(key=lambda r: -r[0])
    return raw, [r[1] for r in reasons[:3]]


# ------------------------------------------------------------------ rank ---

def rank(viewer: dict, candidates: list[dict], query: str = "") -> list[dict]:
    """`viewer` and each candidate are profile dicts (candidates also carry 'id').

    Returns candidates that meet the viewer's requirements, each annotated with
    tier ('mutual' | 'yours'), matchScore (0-100), reasons and rank.
    """
    idf = build_idf([tokens(f"{c.get('bio', '')} {c.get('hobbies', '')}") for c in candidates]
                    + [tokens(f"{viewer.get('bio', '')} {viewer.get('hobbies', '')}")])
    q = (query or "").strip().lower()
    out = []
    for c in candidates:
        if q and q not in " ".join(str(c.get(k, "")) for k in
                                   ("name", "bio", "ethnicity", "career", "age", "gender", "hobbies", "location")).lower():
            continue
        if not meets_requirements(viewer, c):
            continue
        mine, reasons = score(viewer, c, idf)
        mutual = meets_requirements(c, viewer)
        if mutual:
            theirs, _ = score(c, viewer, idf)
            value = (mine + theirs) / 2
            reasons = [] + reasons
        else:
            value = mine
        out.append({**c, "tier": "mutual" if mutual else "yours", "matchScore": round(value * 100),
                    "reasons": reasons[:3]})
    out.sort(key=lambda c: (c["tier"] != "mutual", -c["matchScore"], c.get("name", "")))
    for i, c in enumerate(out, start=1):
        c["rank"] = i
    return out


def pair_score(viewer: dict, cand: dict, corpus: list[dict]) -> tuple[int, list[str]]:
    """Compatibility of one person for the viewer (0-100), same blend as Discover, without the
    requirement filter, so everyone who liked you gets a score. `corpus` = profiles used for TF-IDF."""
    idf = build_idf([tokens(f"{c.get('bio', '')} {c.get('hobbies', '')}") for c in corpus]
                    + [tokens(f"{viewer.get('bio', '')} {viewer.get('hobbies', '')}")])
    mine, reasons = score(viewer, cand, idf)
    if meets_requirements(viewer, cand) and meets_requirements(cand, viewer):
        theirs, _ = score(cand, viewer, idf)
        return round((mine + theirs) / 2 * 100), reasons[:3]
    return round(mine * 100), reasons[:3]
