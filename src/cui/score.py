"""8.5 위험도 스코어링 — 항목별 기여도 분해 필수.

raw = sensor_event_strength(0~25) + cable_proximity(0~20) + vessel_behavior(0~20)
    + ais_gap(0~10) + vessel_history(0~5)            # ≤80
normalized = raw / 80 * 100
risk = clamp(normalized - permit_discount - metoc_discount - sensor_discount, 0, 100)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ScoreBreakdown:
    sensor_event_strength: float
    cable_proximity: float
    vessel_behavior: float
    ais_gap: float
    vessel_history: float
    raw: float
    raw_max: float
    normalized: float
    discounts: dict
    risk: float
    components: dict = field(default_factory=dict)  # 각 항목 상한 대비 표기용

    def to_dict(self) -> dict:
        return {
            "contributions": {
                "sensor_event_strength": round(self.sensor_event_strength, 2),
                "cable_proximity": round(self.cable_proximity, 2),
                "vessel_behavior": round(self.vessel_behavior, 2),
                "ais_gap": round(self.ais_gap, 2),
                "vessel_history": round(self.vessel_history, 2),
            },
            "component_max": self.components,
            "raw": round(self.raw, 2),
            "raw_max": self.raw_max,
            "normalized": round(self.normalized, 2),
            "discounts": self.discounts,
            "risk": round(self.risk, 2),
        }


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def compute_score(event, coupling, ctx: dict, discounts, scoring_cfg: dict) -> ScoreBreakdown:
    caps = scoring_cfg["contributions"]
    vb_w = scoring_cfg["vessel_behavior"]
    buffer_m = ctx.get("buffer_m", 500)
    prim = coupling.primary() if coupling else None

    # 1) sensor_event_strength: 수중 이벤트 severity 비례
    sev = float(event.severity)
    sensor_event_strength = sev * caps["sensor_event_strength_max"]

    # 2) cable_proximity: 의심 활동의 케이블 최단거리 기반(가까울수록↑)
    if prim is not None and prim.min_cable_dist_m is not None:
        d = prim.min_cable_dist_m
    else:
        d = event.metadata.get("derived_from", {}).get("cable_distance_m", buffer_m)
    prox_frac = math.exp(-d / (buffer_m * 1.5))   # d=0→1, d=buffer→~0.51
    cable_proximity = prox_frac * caps["cable_proximity_max"]

    # 3) vessel_behavior: 저속 체류 + 횡단 + 급회전(상한 클램프)
    if prim is not None:
        dwell_ind = _clamp(prim.dwell_in_zone_s / 1800.0, 0, 1)   # 30분=1
        cross_ind = _clamp(prim.cable_crossings / 1.0, 0, 1)
        turn_ind = _clamp(prim.max_turn_deg / 90.0, 0, 1)
        vb = (vb_w["slow_dwell_weight"] * dwell_ind
              + vb_w["crossing_weight"] * cross_ind
              + vb_w["sharp_turn_weight"] * turn_ind)
        vessel_behavior = _clamp(vb, 0, caps["vessel_behavior_max"])
    else:
        vessel_behavior = 0.0

    # 4) ais_gap
    if prim is not None and prim.ais_gap_minutes > 0:
        ais_gap = _clamp(prim.ais_gap_minutes / 60.0, 0, 1) * caps["ais_gap_max"]
    else:
        ais_gap = 0.0

    # 5) vessel_history
    vessel_history = caps["vessel_history_max"] if ctx.get("vessel_history") else 0.0

    # 기여도를 2자리로 반올림한 뒤 raw=그 합으로 산출 → 문서상 기여도 합 = raw 정확히 일치
    sensor_event_strength = round(sensor_event_strength, 2)
    cable_proximity = round(cable_proximity, 2)
    vessel_behavior = round(vessel_behavior, 2)
    ais_gap = round(ais_gap, 2)
    vessel_history = round(vessel_history, 2)
    raw = (sensor_event_strength + cable_proximity + vessel_behavior
           + ais_gap + vessel_history)
    raw_max = scoring_cfg["raw_total_max"]
    normalized = round(raw / raw_max * 100.0, 2)
    risk = round(_clamp(normalized - discounts.total(), 0, 100), 2)

    return ScoreBreakdown(
        sensor_event_strength=sensor_event_strength,
        cable_proximity=cable_proximity,
        vessel_behavior=vessel_behavior,
        ais_gap=ais_gap,
        vessel_history=vessel_history,
        raw=raw, raw_max=raw_max, normalized=normalized,
        discounts=discounts.to_dict(), risk=risk,
        components={
            "sensor_event_strength": caps["sensor_event_strength_max"],
            "cable_proximity": caps["cable_proximity_max"],
            "vessel_behavior": caps["vessel_behavior_max"],
            "ais_gap": caps["ais_gap_max"],
            "vessel_history": caps["vessel_history_max"],
        },
    )
