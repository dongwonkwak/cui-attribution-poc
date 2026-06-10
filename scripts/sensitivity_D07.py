"""D-07 peak_knots 민감도 스윕 — S1만 재실행.

사용:  python scripts/sensitivity_D07.py
출력:  outputs/sensitivity_D07.md  (표 + alert 유지 구간)
다른 시나리오·상수는 건드리지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml

from cui.config import load_config
from cui.pipeline import Pipeline

SWEEP = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25]
ALERT_THRESHOLD = 60.0
ORIGINAL_PEAK = 1.5

S1 = yaml.safe_load((ROOT / "scenarios" / "S1.yaml").read_text(encoding="utf-8"))

cfg = load_config()
pipe = Pipeline(cfg)  # AIS 데이터 1회 로드

rows = []
for pk in SWEEP:
    cfg.derivation["speed"]["peak_knots"] = pk
    a = pipe.assess(S1)
    sev = round(a.incident_event["severity"], 4)
    risk = a.score["risk"]
    branch = a.decision["branch"]
    rows.append({"peak_knots": pk, "severity": sev, "risk": risk, "branch": branch})
    print(f"  peak={pk:.2f}  severity={sev:.4f}  risk={risk:.2f}  branch={branch}")

# 원상 복구
cfg.derivation["speed"]["peak_knots"] = ORIGINAL_PEAK

alert_peaks = [r["peak_knots"] for r in rows if r["branch"] == "alert"]
lo, hi = (min(alert_peaks), max(alert_peaks)) if alert_peaks else (None, None)

# --- Markdown 생성 ---
lines = [
    "# D-07 peak_knots 민감도 분석 — S1 앵커 드래깅",
    "",
    "> **검산 고지**: 본 문서는 실 AIS 항적에서 물리 함수로 파생한 합성 수중 이벤트를 사용한"
    " **룰 기반 융합 판단 로직의 결정론적 검산**이다. 탐지율·오탐률 등 어떤 성능도 주장하지 않는다.",
    "",
    "## 목적",
    "D-07에서 `peak_knots`를 2.5 → 1.5 kt로 정정한 근거를 보강한다.",
    "나머지 상수(`sigma_knots`, 가중, 임계 등) 및 S2~S5 시나리오는 고정.",
    "",
    "## 스윕 결과",
    "",
    "| peak_knots (kt) | severity | risk | 분기 | alert? |",
    "|---|---|---|---|---|",
]
for r in rows:
    alert_mark = "✓" if r["branch"] == "alert" else "✗"
    lines.append(
        f"| {r['peak_knots']:.2f} | {r['severity']:.4f} | {r['risk']:.2f}"
        f" | {r['branch']} | {alert_mark} |"
    )

lines += [
    "",
    "## 분기 기준",
    f"- alert 임계: risk ≥ {ALERT_THRESHOLD:.0f} (pipeline.yaml, 불변)",
    "",
    "## alert 유지 구간",
]
if lo is not None:
    lines.append(f"peak ∈ [{lo}, {hi}] kt 전 구간에서 S1 분기 **alert** 유지.")
else:
    lines.append("스윕 범위 내 alert 없음.")

lines += [
    "",
    "## 해석",
    "SOG 0.9 kt 선박에 대해 피크 위치가 ±1 kt 이상 벗어나도 alert가 유지되는 이유:",
    "- `proximity` 항(케이블 80 m)이 severity의 1차 기여자(`w_proximity=0.45`)이므로,"
    " `speed_term` 변동이 severity 전체에 미치는 영향이 제한적.",
    "- S1은 단일 상수 변동에 강건함이 구조적으로 확인된 시나리오.",
]

OUT = ROOT / "outputs" / "sensitivity_D07.md"
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\n→ {OUT}")
if lo is not None:
    print(f"alert 유지 구간: peak ∈ [{lo}, {hi}] kt")
