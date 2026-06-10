"""8.1 정규화 — 비(非)수중 입력(METOC/허가/이력/센서)을 공통 이벤트로 변환.

AIS 항적 자체는 대량이라 Event 로 전량 변환하지 않고 8.2 결합 단계에서 원본
DataFrame 을 직접 쓴다(추적성은 derived_from 으로 확보). 여기서는 컨텍스트성
이벤트(METOC 조건, 허가, 센서 상태)를 정규화한다.
"""
from __future__ import annotations

import pandas as pd

from cui.schema import Event


def metoc_events(metoc_cfg: dict, cable_segment_id: str) -> list[Event]:
    out = []
    for i, w in enumerate(metoc_cfg["windows"]):
        out.append(Event(
            event_id=f"METOC-{i:02d}",
            event_time=pd.Timestamp(w["start"]).isoformat(),
            source="metoc",
            event_type="metoc_condition",
            location={"cable_segment_id": cable_segment_id},
            asset_id=cable_segment_id,
            severity=0.0,
            confidence=1.0,
            metadata={"wave_height_m": w["wave_height_m"], "current": w["current"]},
        ))
    return out


def permit_events(permits_cfg: dict, cable_segment_id: str) -> list[Event]:
    out = []
    for p in permits_cfg["permits"]:
        out.append(Event(
            event_id=f"PERMIT-{p['permit_id']}",
            event_time=pd.Timestamp(p["time_window"][0]).isoformat(),
            source="maintenance",
            event_type="permit",
            location={"cable_segment_id": cable_segment_id,
                      "lat": p["area"]["center"][1], "lon": p["area"]["center"][0]},
            asset_id=p["cable_segment_id"],
            severity=0.0,
            confidence=1.0,
            metadata={
                "permit_id": p["permit_id"], "mmsi": p["mmsi"],
                "operator": p["operator"], "work_type": p["work_type"],
                "area": p["area"], "time_window": p["time_window"],
            },
        ))
    return out


def sensor_health_events(sensor_cfg: dict, cable_segment_id: str) -> list[Event]:
    out = []
    for node in sensor_cfg["nodes"]:
        degraded = node.get("power_status") != "nominal" or node.get("comm_status") != "nominal"
        out.append(Event(
            event_id=f"SH-{node['node_id']}",
            event_time=pd.Timestamp(sensor_cfg["fault_start"]).isoformat(),
            source="operator_log",
            event_type="sensor_health",
            location={"cable_segment_id": cable_segment_id,
                      "lat": node["lat"], "lon": node["lon"]},
            asset_id=node["node_id"],
            severity=0.0,
            confidence=1.0,
            metadata={
                "node_id": node["node_id"],
                "power_status": node.get("power_status"),
                "comm_status": node.get("comm_status"),
                "degraded": degraded,
            },
        ))
    return out


def vessel_history_flag(history_cfg: dict, mmsi: int) -> dict | None:
    for f in history_cfg.get("flags", []):
        if f["mmsi"] == mmsi:
            return f
    return None
