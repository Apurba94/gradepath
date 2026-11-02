"""Grading logic: weighted scores, competency mastery and class statistics.

A competency-based course asks "what can this learner do?" and not only "what is the average?".
So each assessment task can map to competencies, and mastery rests on recent evidence.
"""
from dataclasses import dataclass

DEFAULT_SCALE = [(80, "A+", 5.0), (75, "A", 4.75), (70, "A-", 4.5), (65, "B+", 4.0), (60, "B", 3.5), (55, "B-", 3.0), (50, "C", 2.5), (45, "D", 2.0), (0, "F", 0.0)]
MASTERY_LEVELS = [(85, "Mastered"), (70, "Competent"), (50, "Developing"), (0, "Beginning")]


@dataclass
class Task:
    id: int
    name: str
    category: str
    out_of: float
    competencies: tuple = ()
    position: int = 0


def letter(percent, scale=DEFAULT_SCALE):
    for cut, name, points in scale:
        if percent >= cut:
            return name, points
    return scale[-1][1], scale[-1][2]


def check_weights(weights):
    total = sum(weights.values())
    if abs(total - 100) > 1e-9:
        raise ValueError(f"category weights add up to {total:g}, not 100")


def weighted_percent(tasks, scores, weights, drop_lowest=None, missing="zero"):
    """Final percentage for one learner. scores: {task id: mark or None}.

    missing: "zero" counts a missed task as 0. "exclude" leaves it out, which suits excused absences.
    Weights of empty categories are shared across the rest, so a term in progress still gives a fair figure.
    drop_lowest: {category: how many of the worst scores to ignore}.
    """
    check_weights(weights)
    drop_lowest = drop_lowest or {}
    by_cat = {}
    for t in tasks:
        v = scores.get(t.id)
        if v is None:
            if missing == "exclude":
                continue
            v = 0.0
        if v > t.out_of or v < 0:
            raise ValueError(f"{t.name}: {v} is outside 0 to {t.out_of}")
        by_cat.setdefault(t.category, []).append((v / t.out_of, t.out_of))
    total_weight = achieved = 0.0
    breakdown = {}
    for cat, w in weights.items():
        items = sorted(by_cat.get(cat, []))
        items = items[drop_lowest.get(cat, 0):] if len(items) > drop_lowest.get(cat, 0) else items[-1:]
        if not items:
            continue
        points = sum(f * o for f, o in items)
        possible = sum(o for _, o in items)
        pct = points / possible * 100
        breakdown[cat] = pct
        achieved += pct * w
        total_weight += w
    return (achieved / total_weight if total_weight else None), breakdown


def mastery(evidence, method="decaying", decay=0.65):
    """evidence: percentages in time order. Returns the current level of a competency.

    decaying: later evidence counts for more, because a learner who improved has improved.
    latest: the most recent result only. highest: the best result. mean: all equally.
    """
    if not evidence:
        return None
    if method == "latest":
        return evidence[-1]
    if method == "highest":
        return max(evidence)
    if method == "mean":
        return sum(evidence) / len(evidence)
    if method == "decaying":
        value = evidence[0]
        for e in evidence[1:]:
            value = decay * e + (1 - decay) * value
        return value
    raise ValueError(f"unknown method {method}")


def mastery_label(value):
    if value is None:
        return "No evidence"
    for cut, name in MASTERY_LEVELS:
        if value >= cut:
            return name
    return MASTERY_LEVELS[-1][1]


def competency_profile(tasks, scores, method="decaying"):
    """{competency: (level, label, pieces of evidence)} for one learner."""
    evidence = {}
    for t in sorted(tasks, key=lambda t: t.position):
        v = scores.get(t.id)
        if v is None:
            continue
        for c in t.competencies:
            evidence.setdefault(c, []).append(v / t.out_of * 100)
    out = {}
    for c, e in evidence.items():
        level = mastery(e, method)
        out[c] = (level, mastery_label(level), len(e))
    return out


def rubric_score(levels, weights=None, top=4):
    """Criteria scored 1 to top. Returns a percentage. weights default to equal."""
    if not levels:
        raise ValueError("a rubric needs at least one criterion")
    weights = weights or [1] * len(levels)
    if len(weights) != len(levels):
        raise ValueError("one weight per criterion is needed")
    for v in levels:
        if not 1 <= v <= top:
            raise ValueError(f"level {v} is outside 1 to {top}")
    return sum(v * w for v, w in zip(levels, weights)) / (top * sum(weights)) * 100


def rank(values):
    """Standard competition ranks: ties share a rank, and the next rank is skipped. Highest first."""
    order = sorted(values, key=lambda k: -values[k])
    out, last, place = {}, None, 0
    for i, k in enumerate(order, 1):
        if values[k] != last:
            place, last = i, values[k]
        out[k] = place
    return out


def distribution(percents, scale=DEFAULT_SCALE):
    out = {name: 0 for _, name, _ in scale}
    for p in percents:
        out[letter(p, scale)[0]] += 1
    return out


def at_risk(history, pass_mark=50, drop=10):
    """history: {learner: [percent per task, in order]}. Flags low scores and sudden falls."""
    out = {}
    for name, h in history.items():
        reasons = []
        if h and sum(h) / len(h) < pass_mark:
            reasons.append("average below the pass mark")
        if len(h) >= 4:
            early = sum(h[:len(h) // 2]) / (len(h) // 2)
            late = sum(h[len(h) // 2:]) / (len(h) - len(h) // 2)
            if early - late >= drop:
                reasons.append(f"fell {early - late:.0f} points in the second half")
        if reasons:
            out[name] = reasons
    return out


def comment(percent, profile):
    """A short, specific starting point for a report card. The teacher should edit it."""
    if percent is None:
        return "Not enough work to report on yet."
    strengths = [c for c, (lvl, _, _) in profile.items() if lvl >= 85]
    gaps = [c for c, (lvl, _, _) in profile.items() if lvl < 60]
    parts = ["Excellent work this term." if percent >= 80 else "Good progress this term." if percent >= 60 else "Passed with room to grow." if percent >= 50 else "Needs extra support next term."]
    if strengths:
        parts.append("Strong in " + ", ".join(sorted(strengths)[:3]) + ".")
    if gaps:
        parts.append("Should focus on " + ", ".join(sorted(gaps)[:3]) + ".")
    return " ".join(parts)
