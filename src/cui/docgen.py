"""문서 생성기 — 시나리오 입출력 체인 / naive 대조 / 루브릭 / 결과 요약.

모든 문서 상단에 '합성 파생 데이터 기반 판단 로직 검산' 고지(비과장 원칙).
"""
from __future__ import annotations

import json

DISCLAIMER = (
    "> **검산 고지**: 본 문서는 실 AIS 항적에서 물리 함수로 파생한 합성 수중 이벤트를 사용한 "
    "**룰 기반 융합 판단 로직의 결정론적 검산**이다. 탐지율·오탐률 등 어떤 성능도 주장하지 않는다.\n"
)


def render_chain(a) -> str:
    """입출력 체인: Raw AIS → 정규화 → 파생 수중 이벤트 → 결합 → 후보 → 위험도 → alert JSON → 분기."""
    ev = a.incident_event
    L = [f"# 입출력 체인 — {a.scenario_id} {a.scenario_name}", "", DISCLAIMER]

    # 0) 시나리오 입력
    L.append("## 0. 시나리오 입력")
    L.append(f"- incident_source: `{a.context['incident_source']}`")
    L.append(f"- 기대 분기: `{a.expected['decision']}`, 기대 1순위: `{a.expected['top_candidate']}`")

    # 1) Raw AIS 발췌(실데이터)
    L.append("\n## 1. Raw AIS 발췌 (실 DMA 항적)")
    if a.raw_ais_excerpt:
        L.append("| timestamp | mmsi | lat | lon | SOG | COG | nav_status | cable_dist_m |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in a.raw_ais_excerpt:
            L.append(f"| {r['timestamp']} | {r['mmsi']} | {r['lat']} | {r['lon']} | "
                     f"{r['sog']} | {r['cog']} | {r['nav_status']} | {r['cable_dist_m']} |")
    else:
        L.append("_(선박 무관 인시던트 — METOC/센서 파생)_")

    # 2) 파생 수중 이벤트(수식 포함)
    L.append("\n## 2. 합성 수중 이벤트 (물리 파생)")
    der = ev.get("metadata", {}).get("derivation", {})
    L.append(f"- 이벤트 `{ev['event_id']}` severity **{ev['severity']}**, confidence **{ev['confidence']}**")
    L.append(f"- 수식: `{der.get('formula', der.get('rule', ''))}`")
    if "terms" in der:
        L.append(f"- 항 기여: `{json.dumps(der['terms'], ensure_ascii=False)}`")
    if "params" in der:
        L.append(f"- 파라미터: `{json.dumps(der['params'], ensure_ascii=False)}`")
    df = ev.get("metadata", {}).get("derived_from", {})
    L.append(f"- 파생 원본(추적): `{json.dumps(df, ensure_ascii=False)}`")

    # 3) 8.2 결합
    L.append("\n## 3. 시공간 결합 (±{}분)".format(a.coupling["window_minutes"]))
    L.append(f"- 1순위 결합 선박 MMSI: `{a.coupling['primary_mmsi']}`, 창 내 선박 {len(a.coupling['vessels'])}척")
    prim = next((v for v in a.coupling["vessels"] if v["mmsi"] == a.coupling["primary_mmsi"]), None)
    if prim:
        L.append("- 특징량:")
        for k in ("min_cable_dist_m", "dwell_in_zone_s", "speed_mean_kt", "speed_var",
                  "cable_crossings", "max_turn_deg", "ais_gap_minutes",
                  "event_time_diff_s", "event_space_dist_m"):
            L.append(f"  - {k}: {prim[k]}")

    # 4) 8.3 후보 랭킹
    L.append("\n## 4. 원인 후보 랭킹 (기여 요인)")
    for c in a.candidates:
        L.append(f"- **{c['name']}**: {c['score']}")
        for f in c["factors"]:
            L.append(f"  - {f['factor']}: {f['value']} (기여 {f['contribution']})")

    # 5) 8.4/8.5 위험도 분해
    rb = a.score
    L.append("\n## 5. 위험도 스코어링 (기여도 분해)")
    comp, cmax = rb["contributions"], rb["component_max"]
    L.append("| 항목 | 기여 | 상한 |")
    L.append("|---|---|---|")
    for k in comp:
        L.append(f"| {k} | {comp[k]} | {cmax[k]} |")
    L.append(f"- raw **{rb['raw']}**/{rb['raw_max']} → normalized **{rb['normalized']}**")
    dsc = rb["discounts"]
    L.append(f"- 디스카운트 합 -{dsc['total']} (허가 -{dsc['maintenance_permit']}, "
             f"METOC -{dsc['metoc_noise']}, 센서 -{dsc['sensor_health']})")
    for r in dsc["rationale"]:
        L.append(f"  - {r}")
    L.append(f"- **risk = {rb['risk']}**")

    # 6) 최종 alert JSON
    L.append("\n## 6. 최종 인시던트 JSON")
    final = {
        "scenario": a.scenario_id,
        "incident_event_id": ev["event_id"],
        "risk": rb["risk"],
        "top_candidate": a.decision["top_candidate"],
        "branch": a.decision["branch"],
    }
    L.append("```json")
    L.append(json.dumps(final, ensure_ascii=False, indent=2))
    L.append("```")

    # 7) 판단 분기
    L.append("\n## 7. 판단 분기")
    L.append(f"- **`{a.decision['branch']}`** — {a.decision['rationale']}")
    match = "✓ 일치" if a.expected["decision"] == a.decision["branch"] else "✗ 불일치"
    L.append(f"- 기대 `{a.expected['decision']}` 대비 **{match}**")
    return "\n".join(L) + "\n"


# --- 증거 완성도 루브릭 (측정지표 2) ---
# 보험/수사 실무에 필요한 6개 필드, 각 0~2점. 먼저 정의한 뒤 시나리오별 채점.
RUBRIC_CRITERIA = [
    ("time_location_precision", "시각·위치 정밀도"),
    ("vessel_identification", "선박 식별"),
    ("environmental_conditions", "환경 조건(METOC)"),
    ("permit_verification", "허가 확인"),
    ("decision_traceability", "판단 근거 추적성"),
    ("raw_data_reference", "원시 데이터 참조"),
]


def score_rubric(bundle: dict) -> dict:
    """증거 패키지 1건을 루브릭으로 채점(각 0~2)."""
    sc, notes = {}, {}
    ev = bundle["underwater_event"]["event"]
    is_vessel = ev["source"] == "underwater_sensor" and bundle["ais_tracks_candidates"]["primary_mmsi"] is not None \
        and bundle["event_summary"]["source"] == "underwater_sensor" \
        and bool(bundle["ais_tracks_candidates"]["raw_ais_excerpt"])

    # 1) 시각·위치 정밀도
    loc = bundle["time_location"]["location"]
    has_time = bool(bundle["time_location"]["event_time"])
    has_xy = "lat" in loc and "lon" in loc
    sc["time_location_precision"] = 2 if (has_time and has_xy) else (1 if has_time else 0)
    notes["time_location_precision"] = f"time={has_time}, lat/lon={has_xy}"

    # 2) 선박 식별
    prim = bundle["ais_tracks_candidates"]["primary_mmsi"]
    behaviors = bundle["ais_tracks_candidates"]["vessel_behaviors"]
    if is_vessel:
        sc["vessel_identification"] = 2 if (prim and behaviors) else 1
        notes["vessel_identification"] = f"MMSI={prim}, behaviors={len(behaviors)}"
    else:
        # 비(非)선박 인시던트: 책임 선박이 없어 양성(positive) 선박 식별은 불가.
        # 결합 선박 문맥은 제시하나 정직하게 부분 점수.
        sc["vessel_identification"] = 1
        notes["vessel_identification"] = "선박 무관 인시던트(METOC/센서) — 양성 선박 식별 없음"

    # 3) 환경 조건
    sc["environmental_conditions"] = 2 if bundle.get("metoc") else 0
    notes["environmental_conditions"] = f"metoc={bundle.get('metoc')}"

    # 4) 허가 확인
    sc["permit_verification"] = 2 if bundle["permit_check"].get("result") else 0
    notes["permit_verification"] = bundle["permit_check"].get("result", "")

    # 5) 판단 근거 추적성
    dec = bundle["decision"]
    rb = bundle["risk_breakdown"]
    ok = bool(dec.get("rationale")) and "contributions" in rb
    sc["decision_traceability"] = 2 if ok else (1 if dec.get("rationale") else 0)
    notes["decision_traceability"] = "근거+기여도분해" if ok else "부분"

    # 6) 원시 데이터 참조
    df = bundle["underwater_event"].get("derived_from")
    raw = bundle["ais_tracks_candidates"]["raw_ais_excerpt"]
    if df and raw and is_vessel:
        sc["raw_data_reference"] = 2          # 실 AIS 원시행 + 파생근거
    elif df:
        sc["raw_data_reference"] = 1          # 파생근거만(METOC/센서는 실 관측 원시행 없음)
    else:
        sc["raw_data_reference"] = 0
    notes["raw_data_reference"] = f"derived_from={'있음' if df else '없음'}, raw행={len(raw)}"

    total = sum(sc.values())
    return {"scores": sc, "notes": notes, "total": total, "max": len(RUBRIC_CRITERIA) * 2}


def render_rubric(rubric_by_scenario: dict) -> str:
    L = ["# 증거 완성도 루브릭", "", DISCLAIMER]
    L.append("## 루브릭 정의 (보험/수사 실무 필요 필드, 각 0~2점)")
    L.append("| # | 기준 | 0 | 1 | 2 |")
    L.append("|---|---|---|---|---|")
    desc = {
        "time_location_precision": ("시각·위치 정밀도", "둘 다 없음", "시각만", "ISO시각+좌표"),
        "vessel_identification": ("선박 식별", "없음", "부분", "MMSI+행동특징 or 선박무관 명시"),
        "environmental_conditions": ("환경 조건(METOC)", "없음", "-", "파고·조류 제시"),
        "permit_verification": ("허가 확인", "없음", "-", "허가 일치/부재 결과"),
        "decision_traceability": ("판단 근거 추적성", "없음", "근거만", "근거+기여도분해"),
        "raw_data_reference": ("원시 데이터 참조", "없음", "derived_from만", "derived_from+원시행"),
    }
    for i, (k, _) in enumerate(RUBRIC_CRITERIA, 1):
        d = desc[k]
        L.append(f"| {i} | {d[0]} | {d[1]} | {d[2]} | {d[3]} |")

    L.append("\n## 시나리오별 채점")
    header = "| 시나리오 | " + " | ".join(name for _, name in RUBRIC_CRITERIA) + " | 합계 |"
    L.append(header)
    L.append("|" + "---|" * (len(RUBRIC_CRITERIA) + 2))
    for sid, rub in rubric_by_scenario.items():
        cells = [str(rub["scores"][k]) for k, _ in RUBRIC_CRITERIA]
        L.append(f"| {sid} | " + " | ".join(cells) + f" | **{rub['total']}/{rub['max']}** |")
    return "\n".join(L) + "\n"


def render_summary(results: list, rubric_by_scenario: dict) -> str:
    L = ["# 결과 요약 (제안서 10장 삽입용)", "", DISCLAIMER]
    L.append("실 DMA 발트해 AIS(2026-06-03, 보른홀름 인근)에서 물리 파생한 합성 수중 이벤트로 "
             "5개 시나리오의 룰 기반 융합 판단 로직을 검산한 결과다.\n")

    # 지표 3: expected/actual 분기 일치
    n_match = sum(r["decision_match"] for r in results)
    n_top = sum(r["top_match"] for r in results)
    L.append("## 지표 3 — 기대 분기 일치")
    L.append("| ID | 시나리오 | 기대 | 실제 | 분기일치 | 기대1순위 | 실제1순위 | 후보일치 | risk |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        L.append(f"| {r['id']} | {r['name']} | {r['expected_decision']} | {r['actual_decision']} | "
                 f"{'✓' if r['decision_match'] else '✗'} | {r['expected_top']} | {r['actual_top']} | "
                 f"{'✓' if r['top_match'] else '✗'} | {r['risk']} |")
    L.append(f"\n**분기 일치 {n_match}/{len(results)}, 1순위 후보 일치 {n_top}/{len(results)}**\n")

    # 지표 1: 단일출처 대비 융합 강등
    downg = [r for r in results if r["downgraded"]]
    L.append("## 지표 1 — 단일출처(naive) 대비 융합 강등")
    L.append("naive = 수중 이벤트 severity 임계만으로 alert. 융합이 문맥 반영해 강등한 건수.")
    L.append("| ID | naive | 융합 | 강등 | 근거 |")
    L.append("|---|---|---|---|---|")
    reason = {"S2": "허가 정비 일치", "S3": "악천후 자연 노이즈·활동성 선박 부재",
              "S4": "AIS-dark 능동 의심 → 수동 검토 escalation", "S5": "전원저하 노드 반복 이상값"}
    for r in results:
        L.append(f"| {r['id']} | {r['naive_branch']} | {r['actual_decision']} | "
                 f"{'예' if r['downgraded'] else '-'} | {reason.get(r['id'],'-') if r['downgraded'] else '-'} |")
    L.append(f"\n**융합 강등 {len(downg)}건** (naive 였다면 모두 alert 오탐). "
             f"S1은 강등 없이 alert 유지(정탐 보존).\n")

    # 지표 2: 루브릭
    L.append("## 지표 2 — 증거 완성도 루브릭")
    L.append("| ID | 점수 |")
    L.append("|---|---|")
    for sid, rub in rubric_by_scenario.items():
        L.append(f"| {sid} | {rub['total']}/{rub['max']} |")
    L.append("(기준 정의·세부 채점은 `rubric.md` 참조)\n")

    # 지표 4: 재현성
    L.append("## 지표 4 — 재현성")
    L.append("전체 파이프라인 2회 실행 산출물 **바이트 단위 동일**(고정 시드, 결정론적 정렬). "
             "`tests/test_determinism.py` 로 검증.\n")

    # 지표 5: incident bundle completeness
    L.append("## 지표 5 — 증거 패키지 완성도(8.6)")
    allc = all(r["evidence_complete"] for r in results)
    L.append(f"5개 시나리오 모두 8.6 필수 필드 체크리스트 **{'통과' if allc else '미통과'}**. "
             f"`tests/test_schema.py`·`evidence.check_completeness` 로 검증.\n")

    L.append("## 이 검산이 증명하는 것 / 증명하지 않는 것")
    L.append("- **증명**: 동일 입력에 대해 룰 기반 융합 로직이 결정론적·추적가능하게 동작하며, "
             "단일출처 대비 문맥(허가·METOC·센서·AIS끊김)을 반영해 분기를 차별화함.")
    L.append("- **비증명**: 실제 위협 탐지율·오탐률·운영 성능. 본 산출물은 합성 파생 데이터 기반 "
             "로직 검산이며 성능 주장이 아님.")
    return "\n".join(L) + "\n"


def render_contrast(a, naive: dict) -> str:
    """naive(단일출처) vs 융합 판단 대조 문서."""
    L = [f"# naive vs 융합 대조 — {a.scenario_id} {a.scenario_name}", "", DISCLAIMER]
    L.append("## 기준선 정의")
    L.append("- **naive(단일 출처)**: 수중 이벤트 severity 가 임계 이상이면 무조건 `alert`. "
             "허가·METOC·센서상태·선박행동 일절 무시.")
    L.append("- **융합**: 8.2~8.5 다중출처 결합 + 룰 기반 오탐 억제 후 분기.")
    L.append("\n## 동일 입력, 두 판정")
    L.append("| 구분 | 판정 | 근거 |")
    L.append("|---|---|---|")
    L.append(f"| naive | `{naive['branch']}` | {naive['basis']} |")
    L.append(f"| 융합 | `{a.decision['branch']}` | {a.decision['rationale']} |")
    downgraded = naive["branch"] == "alert" and a.decision["branch"] in ("suppress", "manual_review")
    L.append("\n## 결과")
    if downgraded:
        L.append(f"- naive 는 `alert`(오탐) 이나, 융합은 문맥을 반영해 "
                 f"**`{a.decision['branch']}` 로 옳게 강등**.")
        dsc = a.score["discounts"]
        if dsc["rationale"]:
            L.append("- 강등 근거(디스카운트):")
            for r in dsc["rationale"]:
                L.append(f"  - {r}")
    else:
        L.append(f"- 강등 없음: naive=`{naive['branch']}`, 융합=`{a.decision['branch']}`.")
    return "\n".join(L) + "\n"
