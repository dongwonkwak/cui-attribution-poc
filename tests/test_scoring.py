"""8.5 스코어 산식 단위 테스트 — 기여도 합 = 정규화 전 raw, 분기 일치."""
import yaml

from cui.config import load_config
from cui.pipeline import Pipeline

ROOT = load_config().root


def _assessments():
    cfg = load_config()
    pipe = Pipeline(cfg)
    out = {}
    for f in sorted((ROOT / "scenarios").glob("S*.yaml")):
        s = yaml.safe_load(f.read_text(encoding="utf-8"))
        out[s["id"]] = pipe.assess(s)
    return out


def test_contribution_sum_equals_raw():
    for sid, a in _assessments().items():
        c = a.score["contributions"]
        s = sum(c.values())
        assert abs(s - a.score["raw"]) < 1e-6, f"{sid}: 기여 합 {s} != raw {a.score['raw']}"


def test_risk_equals_normalized_minus_discounts():
    for sid, a in _assessments().items():
        sc = a.score
        expected = max(0.0, min(100.0, sc["normalized"] - sc["discounts"]["total"]))
        assert abs(expected - sc["risk"]) < 1e-6, f"{sid}: risk 산식 불일치"


def test_contributions_within_caps():
    for sid, a in _assessments().items():
        c = a.score["contributions"]
        m = a.score["component_max"]
        for k in c:
            assert c[k] <= m[k] + 1e-6, f"{sid}: {k} 상한 초과"
        assert a.score["raw"] <= a.score["raw_max"] + 1e-6


def test_expected_decision_match():
    results = {}
    for sid, a in _assessments().items():
        results[sid] = (a.expected["decision"], a.decision["branch"],
                        a.expected["top_candidate"], a.decision["top_candidate"])
    n = sum(1 for v in results.values() if v[0] == v[1])
    assert n == len(results), f"분기 일치 {n}/{len(results)}: {results}"
    nt = sum(1 for v in results.values() if v[2] == v[3])
    assert nt == len(results), f"1순위 후보 일치 {nt}/{len(results)}: {results}"
