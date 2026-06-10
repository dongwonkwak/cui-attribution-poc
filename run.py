"""시나리오 러너 — 전(또는 일부) 시나리오 실행 → outputs/ 산출.

사용:
  python run.py            # 전체 시나리오(scenarios/*.yaml)
  python run.py S1         # 특정 시나리오만
결정론: 정렬된 시나리오 순서, 고정 시드. 2회 실행 바이트 동일을 목표.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from cui.config import load_config
from cui.docgen import (
    render_chain,
    render_contrast,
    render_rubric,
    render_summary,
    score_rubric,
)
from cui.evidence import build_bundle, check_completeness, render_md
from cui.naive import naive_decision
from cui.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent
SCEN_DIR = ROOT / "scenarios"
OUT = ROOT / "outputs"


def load_scenarios(only: str | None) -> list[dict]:
    files = sorted(SCEN_DIR.glob("S*.yaml"))
    scen = [yaml.safe_load(f.read_text(encoding="utf-8")) for f in files]
    if only:
        scen = [s for s in scen if s["id"] == only]
    return scen


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = load_config()
    pipe = Pipeline(cfg)
    cable_cfg = cfg.pipeline["cable"]

    results = []
    rubric_by_scenario = {}
    for s in load_scenarios(only):
        a = pipe.assess(s)
        bundle = build_bundle(a, cable_cfg)
        completeness = check_completeness(bundle)
        naive = naive_decision(a.incident_event, cfg.scoring)

        sid = a.scenario_id
        write(OUT / "chains" / f"{sid}.md", render_chain(a))
        write(OUT / "evidence" / f"{sid}_bundle.json",
              json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
        write(OUT / "evidence" / f"{sid}_bundle.md", render_md(bundle))
        rubric_by_scenario[sid] = score_rubric(bundle)
        # S2/S3 대조 문서
        if sid in ("S2", "S3"):
            write(OUT / "contrast" / f"{sid}_contrast.md", render_contrast(a, naive))

        results.append({
            "id": sid, "name": a.scenario_name,
            "expected_decision": a.expected["decision"],
            "actual_decision": a.decision["branch"],
            "decision_match": a.expected["decision"] == a.decision["branch"],
            "expected_top": a.expected["top_candidate"],
            "actual_top": a.decision["top_candidate"],
            "top_match": a.expected["top_candidate"] == a.decision["top_candidate"],
            "risk": a.score["risk"],
            "naive_branch": naive["branch"],
            "downgraded": naive["branch"] == "alert" and a.decision["branch"] in ("suppress", "manual_review"),
            "evidence_complete": completeness["complete"],
            "evidence_missing": completeness["missing"],
        })

    write(OUT / "results.json", json.dumps(results, ensure_ascii=False, indent=2))
    # 루브릭/요약 문서(전체 실행 시에만)
    if only is None:
        write(OUT / "rubric.md", render_rubric(rubric_by_scenario))
        write(OUT / "results_summary.md", render_summary(results, rubric_by_scenario))
    # 콘솔 요약
    print(f"{'ID':<4} {'expected':<14} {'actual':<14} {'match':<6} {'risk':<6} {'naive':<9} {'downgr':<7} {'evid'}")
    for r in results:
        print(f"{r['id']:<4} {str(r['expected_decision']):<14} {r['actual_decision']:<14} "
              f"{'OK' if r['decision_match'] else 'XX':<6} {r['risk']:<6} {r['naive_branch']:<9} "
              f"{'yes' if r['downgraded'] else '-':<7} {'OK' if r['evidence_complete'] else r['evidence_missing']}")
    n_match = sum(r["decision_match"] for r in results)
    print(f"\n분기 일치: {n_match}/{len(results)}")


if __name__ == "__main__":
    main()
