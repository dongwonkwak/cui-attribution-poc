"""설정 로더. 모든 룰·임계값·가중·파생 상수는 config/*.yaml 에만 존재한다.

config 객체는 단순 dict 래퍼(SimpleNamespace 유사)로, 결정론을 위해 로드 순서·값을
그대로 보존한다. 어떤 임의 상수도 코드에 하드코딩하지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# 프로젝트 루트 = src/cui/config.py 기준 2단계 상위
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Config:
    """파이프라인 전체 설정. 4개 yaml(+mock) 을 묶어 보관."""

    def __init__(self, config_dir: Path = CONFIG_DIR):
        self.config_dir = config_dir
        self.pipeline = _load_yaml(config_dir / "pipeline.yaml")
        self.derivation = _load_yaml(config_dir / "derivation.yaml")
        self.scoring = _load_yaml(config_dir / "scoring.yaml")
        self.mock = {
            name: _load_yaml(config_dir / "mock" / f"{name}.yaml")
            for name in ("metoc", "permits", "vessel_history", "sensor_nodes")
            if (config_dir / "mock" / f"{name}.yaml").exists()
        }

    @property
    def seed(self) -> int:
        return int(self.pipeline["seed"])

    @property
    def root(self) -> Path:
        return ROOT


def load_config(config_dir: Path = CONFIG_DIR) -> Config:
    return Config(config_dir)
