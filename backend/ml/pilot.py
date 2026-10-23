"""Pilot planner: how many parts, days and rupees to confirm a suggested window on the real line.

Turns 'association, not proof' into a concrete next step: a two-arm pilot (control at the
current setting vs. treatment inside the window) sized by a two-proportion power analysis.
"""
import math

from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

DEFAULTS = {
    "alpha": 0.05,
    "power": 0.80,
    "volume_per_day": 1000,
    "pilot_share": 0.20,          # fraction of daily output routed into the pilot
    "cost_per_pilot_part": 20.0,  # INR: extra logging / inspection per pilot part
    "scrap_cost_per_part": 500.0,
}


def parts_per_arm(p_control: float, p_treat: float, alpha: float, power: float) -> int | None:
    """One-sided two-proportion sample size per arm. None if no reduction is expected."""
    if not (0 < p_control < 1) or p_treat >= p_control:
        return None
    p_treat = max(p_treat, 1e-4)
    h = abs(proportion_effectsize(p_control, p_treat))
    n = NormalIndPower().solve_power(effect_size=h, alpha=alpha, power=power,
                                     ratio=1.0, alternative="larger")
    return int(math.ceil(n))


def plan(p_control: float, p_treat: float, **kw) -> dict:
    cfg = {**DEFAULTS, **kw}
    n = parts_per_arm(p_control, p_treat, cfg["alpha"], cfg["power"])
    if n is None:
        return {"feasible": False, "reason": "no reduction expected at this effect size",
                "p_control": p_control, "p_treat": p_treat}
    total = 2 * n
    per_day = cfg["volume_per_day"] * cfg["pilot_share"]
    days = total / per_day if per_day > 0 else float("inf")
    expected_scrap_saved = n * (p_control - p_treat)
    return {
        "feasible": True,
        "p_control": p_control,
        "p_treat": p_treat,
        "parts_per_arm": n,
        "total_parts": total,
        "days": round(days, 1),
        "pilot_cost": round(total * cfg["cost_per_pilot_part"], 2),
        "scrap_saved_during_pilot": round(expected_scrap_saved * cfg["scrap_cost_per_part"], 2),
        "alpha": cfg["alpha"],
        "power": cfg["power"],
    }


def plan_for_window(feature: str, window_entry: dict, **kw) -> dict:
    """Pilot sizes for the pessimistic / central / optimistic effect implied by a safe window."""
    fit = window_entry["fit"]
    p_control = fit["rate_out"]
    lo, hi = fit["rate_in_ci"]
    scenarios = {
        "optimistic": plan(p_control, lo, **kw),
        "central": plan(p_control, fit["rate_in"], **kw),
        "pessimistic": plan(p_control, hi, **kw),
    }
    c = scenarios["central"]
    a, b = window_entry["window"]
    if c["feasible"]:
        summary = (
            f"Run {c['parts_per_arm']} parts with {feature} in [{a:.4g}, {b:.4g}] and "
            f"{c['parts_per_arm']} at the current setting (~{c['days']} days at "
            f"{int(kw.get('pilot_share', DEFAULTS['pilot_share']) * 100)}% of output, pilot cost "
            f"INR {c['pilot_cost']:,.0f}) to confirm a drop from {p_control:.1%} to {fit['rate_in']:.1%} "
            f"at {int(c['power'] * 100)}% power."
        )
    else:
        summary = f"No pilot sized for {feature}: the central estimate shows no reduction."
    return {"feature": feature, "window": window_entry["window"], "scenarios": scenarios,
            "summary": summary, "recommended": bool(window_entry.get("recommended")),
            "window_status": window_entry.get("status"),
            "label": "pilot design; confirms or rejects the suspected effect"}


def detectable_rate(p_control: float, budget_per_arm: int, alpha=0.05, power=0.80) -> float:
    """Highest treated fail rate a pilot of budget_per_arm parts can still tell apart from p_control.
    Smaller true effects than this would likely be missed."""
    lo, hi = 0.0, p_control
    for _ in range(50):
        mid = (lo + hi) / 2
        n = parts_per_arm(p_control, mid, alpha, power)
        if n is not None and n <= budget_per_arm:
            lo = mid
        else:
            hi = mid
    return lo
