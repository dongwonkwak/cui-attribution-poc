"""판단 분기 — alert | suppress | manual_review (근거 텍스트 첨부).

manual_review 조건: 상위 두 후보 점수차 < margin 이고 계열(위협 vs 양성)이 상충,
또는 위협 후보 1순위인데 risk 가 alert/suppress 사이 회색지대.
"""
from __future__ import annotations

from dataclasses import dataclass

THREAT_CANDIDATES = {"specific_vessel", "ais_dark"}
BENIGN_CANDIDATES = {"permitted_maintenance", "legal_fishing", "natural_noise", "sensor_fault"}


@dataclass
class Decision:
    branch: str               # alert | suppress | manual_review
    rationale: str
    top_candidate: str
    second_candidate: str | None
    margin: float

    def to_dict(self) -> dict:
        return {
            "branch": self.branch,
            "top_candidate": self.top_candidate,
            "second_candidate": self.second_candidate,
            "margin": round(self.margin, 4),
            "rationale": self.rationale,
        }


def decide(candidates, risk: float, decision_cfg: dict) -> Decision:
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    margin = top.score - (second.score if second else 0.0)
    alert_thr = decision_cfg["alert_risk_threshold"]
    supp_thr = decision_cfg["suppress_risk_threshold"]
    cand_margin = decision_cfg["candidate_margin"]

    top_threat = top.name in THREAT_CANDIDATES
    second_class_conflict = (
        second is not None
        and ((top.name in THREAT_CANDIDATES) != (second.name in THREAT_CANDIDATES))
    )

    # 1) 후보 경합 + 계열 상충 → 수동 검토
    if second is not None and margin < cand_margin and second_class_conflict:
        return Decision(
            "manual_review",
            f"상위 두 후보({top.name} {top.score:.2f} vs {second.name} {second.score:.2f}) "
            f"점수차 {margin:.2f} < {cand_margin} 이고 위협/양성 계열이 상충 → 수동 검토. "
            f"risk={risk:.1f}.",
            top.name, second.name if second else None, margin,
        )

    # 2) 위협 후보 1순위
    if top_threat:
        if risk >= alert_thr:
            return Decision(
                "alert",
                f"위협 후보 '{top.name}'(점수 {top.score:.2f}) 1순위, risk {risk:.1f} ≥ {alert_thr} → 경보.",
                top.name, second.name if second else None, margin,
            )
        if risk < supp_thr:
            return Decision(
                "suppress",
                f"위협 후보 1순위지만 risk {risk:.1f} < {supp_thr}(억제 충분) → 억제.",
                top.name, second.name if second else None, margin,
            )
        return Decision(
            "manual_review",
            f"위협 후보 '{top.name}' 1순위이나 risk {risk:.1f} 가 회색지대"
            f"({supp_thr}~{alert_thr}) → 수동 검토.",
            top.name, second.name if second else None, margin,
        )

    # 3) 양성 후보 1순위 → 억제(단 risk 매우 높으면 수동 검토)
    if risk >= alert_thr:
        return Decision(
            "manual_review",
            f"양성 후보 '{top.name}' 1순위이나 risk {risk:.1f} ≥ {alert_thr} 로 높음 → 수동 검토.",
            top.name, second.name if second else None, margin,
        )
    return Decision(
        "suppress",
        f"양성 후보 '{top.name}'(점수 {top.score:.2f}) 1순위, risk {risk:.1f} → 오탐 억제.",
        top.name, second.name if second else None, margin,
    )
