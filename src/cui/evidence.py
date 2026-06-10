"""8.6 증거 패키지 — JSON + MD 동시 출력.

필수 필드(8.6 체크리스트): 이벤트 요약, 시각·위치, 케이블 구간·보호구역,
수중 이벤트(파생 근거 포함), AIS 항적·선박 후보, METOC, 허가 확인 결과,
위험도 기여도 분해, 판단 분기와 근거.
"""
from __future__ import annotations

import json

# 8.6 필수 필드 체크리스트(키)
REQUIRED_FIELDS = [
    "event_summary", "time_location", "cable_segment", "underwater_event",
    "ais_tracks_candidates", "metoc", "permit_check", "risk_breakdown",
    "decision",
]


def build_bundle(assessment, cable_cfg: dict) -> dict:
    a = assessment
    ev = a.incident_event
    prim_mmsi = a.coupling.get("primary_mmsi")
    bundle = {
        "scenario": {"id": a.scenario_id, "name": a.scenario_name},
        "disclaimer": "합성 파생 데이터 기반 판단 로직 검산. 탐지 성능 주장 아님.",
        "event_summary": {
            "incident_event_id": ev["event_id"],
            "source": ev["source"],
            "event_type": ev["event_type"],
            "severity": ev["severity"],
            "confidence": ev["confidence"],
        },
        "time_location": {
            "event_time": ev["event_time"],
            "location": ev["location"],
        },
        "cable_segment": {
            "segment_id": cable_cfg["segment_id"],
            "line": cable_cfg["line"],
            "protection_buffer_m": cable_cfg["buffer_m"],
        },
        "underwater_event": {
            "event": ev,
            "derived_from": ev.get("metadata", {}).get("derived_from"),
            "derivation": ev.get("metadata", {}).get("derivation"),
        },
        "ais_tracks_candidates": {
            "primary_mmsi": prim_mmsi,
            "raw_ais_excerpt": a.raw_ais_excerpt,
            "vessel_behaviors": a.coupling.get("vessels", []),
            "cause_candidates": a.candidates,
        },
        "metoc": a.context.get("metoc_at_event"),
        "permit_check": {
            "permit_match": a.context.get("permit_match"),
            "result": "일치(정비로 간주)" if a.context.get("permit_match") else "해당 허가 없음",
        },
        "sensor_health": a.context.get("nearest_node"),
        "risk_breakdown": a.score,
        "decision": a.decision,
        "expected": a.expected,
    }
    return bundle


def check_completeness(bundle: dict) -> dict:
    """8.6 필수 필드 충족 여부."""
    missing = []
    for k in REQUIRED_FIELDS:
        v = bundle.get(k)
        if v is None or (isinstance(v, (list, dict)) and len(v) == 0):
            missing.append(k)
    return {"complete": not missing, "missing": missing,
            "n_required": len(REQUIRED_FIELDS), "n_present": len(REQUIRED_FIELDS) - len(missing)}


def render_md(bundle: dict) -> str:
    b = bundle
    L = []
    sc = b["scenario"]
    L.append(f"# 증거 패키지 — {sc['id']} {sc['name']}")
    L.append(f"\n> {b['disclaimer']}\n")

    es = b["event_summary"]
    L.append("## 1. 이벤트 요약")
    L.append(f"- 인시던트 이벤트: `{es['incident_event_id']}` ({es['source']}/{es['event_type']})")
    L.append(f"- severity **{es['severity']}**, confidence **{es['confidence']}**")

    tl = b["time_location"]
    L.append("\n## 2. 시각·위치")
    L.append(f"- 시각: `{tl['event_time']}`")
    L.append(f"- 위치: {json.dumps(tl['location'], ensure_ascii=False)}")

    cs = b["cable_segment"]
    L.append("\n## 3. 케이블 구간·보호구역")
    L.append(f"- 구간 `{cs['segment_id']}`, 보호버퍼 {cs['protection_buffer_m']}m")
    L.append(f"- 라인: `{cs['line']}`")

    uw = b["underwater_event"]
    L.append("\n## 4. 수중 이벤트 (파생 근거)")
    if uw.get("derived_from"):
        L.append(f"- 파생 원본: `{json.dumps(uw['derived_from'], ensure_ascii=False)}`")
    if uw.get("derivation"):
        d = uw["derivation"]
        L.append(f"- 수식: `{d.get('formula', d.get('rule'))}`")
        if "terms" in d:
            L.append(f"- 항 기여: `{json.dumps(d['terms'], ensure_ascii=False)}`")
        L.append(f"- 파라미터: `{json.dumps(d.get('params', {}), ensure_ascii=False)}`")

    ac = b["ais_tracks_candidates"]
    L.append("\n## 5. AIS 항적·선박 후보")
    L.append(f"- 1순위 선박 MMSI: `{ac['primary_mmsi']}`")
    if ac["raw_ais_excerpt"]:
        L.append("- 원본 AIS 발췌(이벤트 인근):")
        L.append("\n| timestamp | mmsi | lat | lon | SOG | COG | nav_status | cable_dist_m |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in ac["raw_ais_excerpt"]:
            L.append(f"| {r['timestamp']} | {r['mmsi']} | {r['lat']} | {r['lon']} | "
                     f"{r['sog']} | {r['cog']} | {r['nav_status']} | {r['cable_dist_m']} |")
    L.append("\n- 원인 후보 랭킹(기여 요인):")
    for c in ac["cause_candidates"]:
        L.append(f"  - **{c['name']}**: {c['score']}")
        for f in c["factors"]:
            L.append(f"    - {f['factor']}: {f['value']} (기여 {f['contribution']})")

    L.append("\n## 6. METOC")
    L.append(f"- {json.dumps(b['metoc'], ensure_ascii=False)}")

    L.append("\n## 7. 허가 확인 결과")
    L.append(f"- {b['permit_check']['result']}")
    if b['permit_check']['permit_match']:
        L.append(f"  - {json.dumps(b['permit_check']['permit_match'], ensure_ascii=False)}")

    rb = b["risk_breakdown"]
    L.append("\n## 8. 위험도 기여도 분해")
    comp = rb["contributions"]; cmax = rb["component_max"]
    L.append("\n| 항목 | 기여 | 상한 |")
    L.append("|---|---|---|")
    for k in comp:
        L.append(f"| {k} | {comp[k]} | {cmax[k]} |")
    L.append(f"\n- raw **{rb['raw']}** / {rb['raw_max']} → normalized **{rb['normalized']}**")
    dsc = rb["discounts"]
    L.append(f"- 디스카운트: 허가 -{dsc['maintenance_permit']}, METOC -{dsc['metoc_noise']}, "
             f"센서 -{dsc['sensor_health']} (합 -{dsc['total']})")
    for r in dsc["rationale"]:
        L.append(f"  - {r}")
    L.append(f"- **risk = {rb['risk']}**")

    dec = b["decision"]
    L.append("\n## 9. 판단 분기와 근거")
    L.append(f"- **분기: `{dec['branch']}`**")
    L.append(f"- 1순위 후보: {dec['top_candidate']} (2순위 {dec['second_candidate']}, 격차 {dec['margin']})")
    L.append(f"- 근거: {dec['rationale']}")
    exp = b["expected"]
    match = "✓ 일치" if exp.get("decision") == dec["branch"] else "✗ 불일치"
    L.append(f"- 기대 분기 `{exp.get('decision')}` 대비 **{match}**")

    return "\n".join(L) + "\n"
