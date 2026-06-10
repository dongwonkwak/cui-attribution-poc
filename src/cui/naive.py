"""대조용 단일출처 naive 탐지 기준선.

정의: 융합/문맥을 일절 보지 않고 '수중 이벤트 severity 가 임계 이상이면 무조건 alert'.
허가·METOC·센서상태·선박행동을 전혀 고려하지 않는 단일 출처 판정. S2/S3 대조에서
이 naive 가 오탐(alert)을 내는 것을 융합이 어떻게 강등(suppress/manual_review)하는지 비교.
"""
from __future__ import annotations


def naive_decision(incident_event: dict, scoring_cfg: dict) -> dict:
    thr = scoring_cfg["naive"]["severity_alert_threshold"]
    sev = float(incident_event["severity"])
    branch = "alert" if sev >= thr else "no_alert"
    return {
        "branch": branch,
        "basis": f"수중 이벤트 severity {sev} {'≥' if sev >= thr else '<'} 임계 {thr} "
                 f"(단일 출처, 문맥 무시)",
        "severity": sev,
        "threshold": thr,
    }
