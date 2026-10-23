"""Savings model. Always returns a {low, mid, high} range labelled 'model estimate'."""
from dataclasses import asdict, dataclass

# Defaults are illustrative assumptions for the demo; the UI exposes them as sliders.
DEFAULTS = {
    "volume_per_day": 1000,
    "scrap_cost_per_part": 500.0,   # INR, cost of an escaped / scrapped defective part
    "false_alarm_cost": 50.0,       # INR, cost of inspecting a part flagged in error
    "days_per_month": 26,
}
RANGES = {
    "volume_per_day": (10, 100_000),
    "scrap_cost_per_part": (1.0, 100_000.0),
    "false_alarm_cost": (0.0, 10_000.0),
    "days_per_month": (1, 31),
}

# used for picking the classification threshold
COST_FN = DEFAULTS["scrap_cost_per_part"]
COST_FP = DEFAULTS["false_alarm_cost"]


@dataclass
class CostInputs:
    volume_per_day: float = DEFAULTS["volume_per_day"]
    scrap_cost_per_part: float = DEFAULTS["scrap_cost_per_part"]
    false_alarm_cost: float = DEFAULTS["false_alarm_cost"]
    days_per_month: float = DEFAULTS["days_per_month"]
    baseline_fail_rate: float = 0.066
    # relative reduction in fail rate, e.g. 0.2 = 20 % fewer defects
    reduction_low: float = 0.0
    reduction_mid: float = 0.0
    reduction_high: float = 0.0
    # extra parts flagged per day if the model gates production (0 if advisory only)
    false_alarms_per_day: float = 0.0

    def validate(self) -> None:
        for k, (lo, hi) in RANGES.items():
            v = getattr(self, k)
            if not lo <= v <= hi:
                raise ValueError(f"{k}={v} outside allowed range [{lo}, {hi}]")
        if not 0 <= self.baseline_fail_rate <= 1:
            raise ValueError("baseline_fail_rate must be in [0, 1]")
        for k in ("reduction_low", "reduction_mid", "reduction_high"):
            if not -1 <= getattr(self, k) <= 1:
                raise ValueError(f"{k} must be in [-1, 1]")
        if self.false_alarms_per_day < 0:
            raise ValueError("false_alarms_per_day must be >= 0")


def monthly_savings(inp: CostInputs) -> dict:
    inp.validate()
    reductions = sorted([inp.reduction_low, inp.reduction_mid, inp.reduction_high])
    fa_cost = inp.false_alarms_per_day * inp.false_alarm_cost * inp.days_per_month

    def one(r):
        avoided_per_day = inp.volume_per_day * inp.baseline_fail_rate * r
        return {
            "avoided_scrap_parts_per_month": avoided_per_day * inp.days_per_month,
            "savings_per_month": avoided_per_day * inp.scrap_cost_per_part * inp.days_per_month - fa_cost,
        }

    low, mid, high = (one(r) for r in reductions)
    return {
        "low": low, "mid": mid, "high": high,
        "false_alarm_cost_per_month": fa_cost,
        "currency": "INR",
        "label": "model estimate",
        "assumptions": asdict(inp),
    }
