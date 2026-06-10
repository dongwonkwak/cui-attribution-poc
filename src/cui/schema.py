"""8.1 공통 이벤트 스키마 — 모든 입력을 동일 구조로 정규화.

event_id, event_time, source, location, asset_id, event_type, severity,
confidence, metadata
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SOURCES = {"ais", "underwater_sensor", "metoc", "maintenance", "vessel_history", "operator_log"}
EVENT_TYPES = {
    "vibration", "acoustic", "vessel_track", "ais_gap",
    "metoc_condition", "permit", "sensor_health",
}


@dataclass
class Event:
    event_id: str
    event_time: str                # ISO8601 문자열(결정론적 직렬화)
    source: str                    # SOURCES 중 하나
    event_type: str                # EVENT_TYPES 중 하나
    location: dict                 # {lat, lon} 또는 {cable_segment_id}
    asset_id: str | None = None    # 케이블 구간/센서 노드/MMSI 등
    severity: float = 0.0          # 0~1
    confidence: float = 0.0        # 0~1
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(f"잘못된 source: {self.source}")
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"잘못된 event_type: {self.event_type}")
        if not (0.0 <= self.severity <= 1.0):
            raise ValueError(f"severity 범위 위반: {self.severity}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence 범위 위반: {self.confidence}")
        if "lat" not in self.location and "cable_segment_id" not in self.location:
            raise ValueError("location 은 lat/lon 또는 cable_segment_id 필요")

    def to_dict(self) -> dict:
        return asdict(self)


def validate_all(events: list[Event]) -> None:
    ids = set()
    for e in events:
        e.validate()
        if e.event_id in ids:
            raise ValueError(f"event_id 중복: {e.event_id}")
        ids.add(e.event_id)
