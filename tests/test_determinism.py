"""결정론 테스트 — 전체 파이프라인 2회 실행 산출물 바이트 동일."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
PY = ROOT / ".venv" / "bin" / "python"


def _digest_outputs() -> dict:
    files = sorted(p for p in OUT.rglob("*") if p.is_file())
    return {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def _run():
    env = {"PYTHONPATH": str(ROOT / "src")}
    import os
    e = os.environ.copy(); e.update(env)
    subprocess.run([str(PY if PY.exists() else sys.executable), "run.py"],
                   cwd=ROOT, env=e, check=True, capture_output=True)


def test_pipeline_byte_identical_across_runs():
    _run()
    d1 = _digest_outputs()
    _run()
    d2 = _digest_outputs()
    assert d1.keys() == d2.keys(), "산출 파일 목록 불일치"
    diffs = [k for k in d1 if d1[k] != d2[k]]
    assert not diffs, f"2회 실행 차이 파일: {diffs}"


def test_derive_events_deterministic():
    from cui.ais_subset import get_subset
    from cui.config import load_config
    from cui.derive_events import derive_underwater_events
    from cui.geo import Cable
    cfg = load_config()
    df = get_subset(cfg)
    cable = Cable.from_config(cfg.pipeline)
    mmsi = cfg.pipeline["cable"]["primary_vessel_mmsi"]
    a = derive_underwater_events(df, cable, cfg.derivation, cfg.seed, mmsi_filter=[mmsi])
    b = derive_underwater_events(df, cable, cfg.derivation, cfg.seed, mmsi_filter=[mmsi])
    assert [e.to_dict() for e in a] == [e.to_dict() for e in b]
