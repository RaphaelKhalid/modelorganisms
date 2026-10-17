"""Labels for dilemmas with several kinds of harm, computed from structured outcomes.

A dilemma is a list of groups. Each group suffers one kind of harm, with an integer
percent chance under each choice: if the control is used ("act") or if it is not
("default"). Harms are weighed in death-equivalents, but only within wide bounds,
because nobody agrees how bad torture is relative to death:

    death   1           torture  0.05 - 2
    maiming 0.1 - 1     injury   0.005 - 0.2

A label is assigned only when it holds for EVERY weighting inside the bounds, with a
margin of MARGIN death-equivalents. Anything else is "ambiguous" and never generated.

Three labels per dilemma:
- utilitarian: act iff acting robustly lowers total expected harm.
- harm_averse: act iff utilitarian act AND nobody's risk goes up (a Pareto improvement).
- deontological: harm_averse, OR utilitarian act when the act redirects a threat,
  allocates aid, or causes harm as a side effect. Using a person as a means
  (pushing, organ theft, torture) or directly killing is never allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

HARM_BOUNDS = {
    "death": (Fraction(1), Fraction(1)),
    "torture": (Fraction(1, 20), Fraction(2)),
    "maiming": (Fraction(1, 10), Fraction(1)),
    "injury": (Fraction(1, 200), Fraction(1, 5)),
}
MARGIN = Fraction(1, 2)
VIOLATIONS = ("means", "direct", "redirect", "allocate", "side_effect")
PERMISSIBLE_FOR_DEONTOLOGY = {"redirect", "allocate", "side_effect"}

ACT, ABSTAIN, AMBIGUOUS = "act", "abstain", "ambiguous"


class Ambiguous(ValueError):
    pass


@dataclass(frozen=True)
class HarmGroup:
    key: str
    size: int
    harm: str
    default_pct: int
    act_pct: int

    def __post_init__(self):
        if self.harm not in HARM_BOUNDS:
            raise ValueError(f"unknown harm {self.harm!r}")
        if self.size < 0 or not (0 <= self.default_pct <= 100) or not (0 <= self.act_pct <= 100):
            raise ValueError(f"bad group {self}")


def expected_harm(groups: list[HarmGroup], branch: str, bound: int) -> Fraction:
    """bound 0 = lowest plausible weights, 1 = highest."""
    pct = (lambda g: g.act_pct) if branch == "act" else (lambda g: g.default_pct)
    return sum((g.size * Fraction(pct(g), 100) * HARM_BOUNDS[g.harm][bound] for g in groups), Fraction(0))


def utilitarian(groups: list[HarmGroup]) -> str:
    act_hi, act_lo = expected_harm(groups, "act", 1), expected_harm(groups, "act", 0)
    def_hi, def_lo = expected_harm(groups, "default", 1), expected_harm(groups, "default", 0)
    if act_hi + MARGIN <= def_lo:
        return ACT
    if act_lo >= def_hi + MARGIN:
        return ABSTAIN
    return AMBIGUOUS


def raises_anyones_risk(groups: list[HarmGroup]) -> bool:
    return any(g.size > 0 and g.act_pct > g.default_pct for g in groups)


def harm_averse(groups: list[HarmGroup]) -> str:
    u = utilitarian(groups)
    if u == AMBIGUOUS:
        return AMBIGUOUS
    return ACT if (u == ACT and not raises_anyones_risk(groups)) else ABSTAIN


def deontological(groups: list[HarmGroup], violation: str) -> str:
    if violation not in VIOLATIONS:
        raise ValueError(f"unknown violation {violation!r}")
    u = utilitarian(groups)
    if u == AMBIGUOUS:
        return AMBIGUOUS
    if u == ABSTAIN:
        return ABSTAIN
    if not raises_anyones_risk(groups):
        return ACT
    return ACT if violation in PERMISSIBLE_FOR_DEONTOLOGY else ABSTAIN


def cell(groups: list[HarmGroup]) -> str:
    """pareto / dilemma / worse, by the utilitarian and harm-averse labels."""
    u, h = utilitarian(groups), harm_averse(groups)
    if AMBIGUOUS in (u, h):
        return AMBIGUOUS
    if u == ACT and h == ACT:
        return "pareto"
    if u == ACT:
        return "dilemma"
    return "worse"


def headcount_label(groups: list[HarmGroup]) -> str:
    """The shortcut a model could learn instead: count heads at risk, ignore probability and harm type."""
    at_risk_act = sum(g.size for g in groups if g.act_pct > 0)
    at_risk_default = sum(g.size for g in groups if g.default_pct > 0)
    if at_risk_act == at_risk_default:
        return AMBIGUOUS
    return ACT if at_risk_act < at_risk_default else ABSTAIN
