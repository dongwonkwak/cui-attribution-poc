"""8.4 오탐 억제 — 순수 룰 기반 디스카운트(ML 없음).

체크: 허가 정비 일치 / METOC 자연 노이즈 가능성 / 센서 전원·통신 불안정·반복장애.
각 디스카운트는 상한(scoring.yaml) 내에서 규칙으로 산출하며 근거를 함께 반환한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Discounts:
    maintenance_permit: float = 0.0
    metoc_noise: float = 0.0
    sensor_health: float = 0.0
    rationale: list[str] = field(default_factory=list)

    def total(self) -> float:
        return self.maintenance_permit + self.metoc_noise + self.sensor_health

    def to_dict(self) -> dict:
        return {
            "maintenance_permit": round(self.maintenance_permit, 2),
            "metoc_noise": round(self.metoc_noise, 2),
            "sensor_health": round(self.sensor_health, 2),
            "total": round(self.total(), 2),
            "rationale": self.rationale,
        }


def compute_discounts(ctx: dict, coupling, scoring_cfg: dict) -> Discounts:
    d = Discounts()
    caps = scoring_cfg["discounts"]
    prim = coupling.primary() if coupling else None

    # 1) 허가 정비 일치
    pm = ctx.get("permit_match")
    if pm:
        d.maintenance_permit = caps["maintenance_permit_max"]
        d.rationale.append(
            f"허가 {pm.get('permit_id')} 가 선박/시간/구역 일치 → 정비로 간주, "
            f"-{d.maintenance_permit} 감점"
        )

    # 2) METOC 자연 노이즈 가능성: 파고가 임계 근처 이상 + 의심 선박 행동 약함
    met = ctx.get("metoc_at_event")
    if met:
        wave = met.get("wave_height_m", 0.0)
        thr = ctx.get("metoc_wave_threshold", 2.5)
        weak_vessel = not (prim and prim.entered_zone)
        if wave >= thr:
            frac = min(1.0, (wave - thr) / thr + 0.5)  # 임계 이상이면 0.5~1.0
            base = caps["metoc_noise_max"] * frac
            d.metoc_noise = base if weak_vessel else base * 0.3
            d.rationale.append(
                f"파고 {wave}m(≥{thr}) 악천후"
                + ("·의심 선박 부재" if weak_vessel else "·정박 선박 존재로 METOC 감점 부분 적용")
                + f" → -{round(d.metoc_noise,2)} 감점"
            )

    # 3) 센서 전원/통신 불안정 + 반복 장애 패턴
    node = ctx.get("nearest_node")
    if node and node.get("degraded"):
        base = caps["sensor_health_max"] * 0.6
        rep = caps["sensor_health_max"] * 0.4 if ctx.get("sensor_repeat") else 0.0
        d.sensor_health = min(caps["sensor_health_max"], base + rep)
        d.rationale.append(
            f"최근접 노드 {node.get('node_id')} 전원저하"
            + ("·규칙적 반복 이상값" if ctx.get("sensor_repeat") else "")
            + f" → -{round(d.sensor_health,2)} 감점"
        )

    return d
