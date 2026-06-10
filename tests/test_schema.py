"""8.1 스키마 검증 + 8.6 증거 완성도 테스트."""
import yaml

from cui.config import load_config
from cui.evidence import build_bundle, check_completeness
from cui.pipeline import Pipeline
from cui.schema import Event, validate_all

ROOT = load_config().root


def test_event_schema_valid():
    e = Event(
        event_id="X1", event_time="2026-06-03T00:00:00", source="underwater_sensor",
        event_type="vibration", location={"lat": 55.0, "lon": 14.0},
        severity=0.5, confidence=0.8,
    )
    e.validate()  # 예외 없어야 함


def test_event_schema_rejects_bad_severity():
    e = Event(
        event_id="X2", event_time="t", source="ais", event_type="vessel_track",
        location={"lat": 1, "lon": 2}, severity=1.5, confidence=0.5,
    )
    try:
        e.validate()
        assert False, "범위 초과 severity 가 통과됨"
    except ValueError:
        pass


def test_all_scenarios_schema_and_completeness():
    cfg = load_config()
    pipe = Pipeline(cfg)
    cable_cfg = cfg.pipeline["cable"]
    for f in sorted((ROOT / "scenarios").glob("S*.yaml")):
        s = yaml.safe_load(f.read_text(encoding="utf-8"))
        a = pipe.assess(s)
        # incident 이벤트 스키마 검증
        ev = Event(**{k: a.incident_event[k] for k in
                      ("event_id", "event_time", "source", "event_type",
                       "location", "asset_id", "severity", "confidence", "metadata")})
        ev.validate()
        # 8.6 완성도
        bundle = build_bundle(a, cable_cfg)
        comp = check_completeness(bundle)
        assert comp["complete"], f"{s['id']} 증거 누락: {comp['missing']}"
