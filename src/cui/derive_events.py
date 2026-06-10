"""[커밋②] 합성 수중 이벤트 — 실 AIS 항적의 물리 함수로만 파생.

원칙#2: 항적과 무관한 임의 이벤트 주입 금지. 각 합성 이벤트는 원본 AIS 행 참조
(derived_from)와 적용 수식·파라미터(derivation)를 추적 가능하게 기록한다.

severity(t) = w_p*proximity + w_s*speed + w_k*kinematics + seeded_noise
  proximity  = exp(-d / d0)
  speed      = exp(-((SOG - peak)^2) / (2*sigma^2))      # 앵커드래그 저속 피크
  kinematics = cw*min(|dCOG|/cog_norm,1) + sw*min(max(0,-dSOG)/sog_norm,1)
  seeded_noise ~ N(0, amplitude)  (고정 시드)
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd

from cui.geo import Cable
from cui.schema import Event


def _seeded_noise(seed: int, key: str, amplitude: float) -> float:
    """결정론적 가우시안 노이즈: (전역시드, 행키) 해시로 정규난수 생성."""
    h = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    # 두 4바이트 정수 → Box-Muller 로 표준정규
    u1 = (int.from_bytes(h[0:4], "big") + 1) / (2**32 + 1)
    u2 = (int.from_bytes(h[4:8], "big") + 1) / (2**32 + 1)
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return z * amplitude


def _angle_diff(a: float, b: float) -> float:
    """두 방위(도) 최소 각차 0~180."""
    d = abs((a - b + 180) % 360 - 180)
    return d


def derive_underwater_events(
    df: pd.DataFrame,
    cable: Cable,
    deriv_cfg: dict,
    seed: int,
    mmsi_filter: list[int] | None = None,
) -> list[Event]:
    """선택 구역 AIS 항적 → 임계 초과 포인트에서 수중 이벤트 생성."""
    sv = deriv_cfg["severity"]
    d0 = deriv_cfg["proximity"]["d0_m"]
    peak = deriv_cfg["speed"]["peak_knots"]
    sigma = deriv_cfg["speed"]["sigma_knots"]
    kc = deriv_cfg["kinematics"]
    noise_amp = deriv_cfg["noise"]["amplitude"]
    threshold = deriv_cfg["event_threshold"]
    conf = deriv_cfg["confidence"]

    work = df if mmsi_filter is None else df[df["mmsi"].isin(mmsi_filter)]
    events: list[Event] = []

    for mmsi, g in work.sort_values(["mmsi", "timestamp"]).groupby("mmsi", sort=True):
        g = g.reset_index()  # 원본 인덱스를 'index' 컬럼으로 보존(derived_from 추적)
        prev_cog = None
        prev_sog = None
        for i in range(len(g)):
            row = g.iloc[i]
            # SOG/위치 결측 포인트는 물리 파생 불가 → 이벤트 미생성(건너뜀, prev 유지)
            if pd.isna(row["sog"]) or pd.isna(row["lon"]) or pd.isna(row["lat"]):
                continue
            lon, lat, sog = float(row["lon"]), float(row["lat"]), float(row["sog"])
            cog = float(row["cog"]) if pd.notna(row["cog"]) else None

            d = cable.distance_m(lon, lat)
            proximity = math.exp(-d / d0)
            speed_term = math.exp(-((sog - peak) ** 2) / (2 * sigma**2))

            dcog = _angle_diff(cog, prev_cog) if (cog is not None and prev_cog is not None) else 0.0
            dsog = (sog - prev_sog) if prev_sog is not None else 0.0
            kin = (
                kc["cog_weight"] * min(dcog / kc["cog_norm_deg"], 1.0)
                + kc["sog_drop_weight"] * min(max(0.0, -dsog) / kc["sog_drop_norm_knots"], 1.0)
            )

            signal = (
                sv["w_proximity"] * proximity
                + sv["w_speed"] * speed_term
                + sv["w_kinematics"] * kin
            )
            row_key = f"{int(mmsi)}:{row['timestamp']}"
            noise = _seeded_noise(seed, row_key, noise_amp)
            severity = float(np.clip(signal + noise, 0.0, 1.0))

            prev_cog, prev_sog = cog, sog

            if severity <= threshold:
                continue

            confidence = float(np.clip(
                conf["base"]
                + conf["proximity_bonus"] * proximity
                + conf["severity_bonus"] * severity,
                0.0, 1.0,
            ))
            ev_type = "vibration" if kin >= sv["w_kinematics"] * 0.5 else "acoustic"
            ts_iso = pd.Timestamp(row["timestamp"]).isoformat()
            event = Event(
                event_id=f"UW-{int(mmsi)}-{i:04d}",
                event_time=ts_iso,
                source="underwater_sensor",
                event_type=ev_type,
                location={"lat": round(lat, 6), "lon": round(lon, 6),
                          "cable_segment_id": cable.segment_id},
                asset_id=cable.segment_id,
                severity=round(severity, 4),
                confidence=round(confidence, 4),
                metadata={
                    "derived_from": {
                        "source": "DMA_AIS",
                        "mmsi": int(mmsi),
                        "ais_row_index": int(row["index"]),
                        "timestamp": ts_iso,
                        "sog": round(sog, 2),
                        "cog": round(cog, 1) if cog is not None else None,
                        "cable_distance_m": round(d, 1),
                    },
                    "derivation": {
                        "formula": "severity = w_p*exp(-d/d0) + w_s*exp(-(SOG-peak)^2/(2*sigma^2)) + w_k*kin + noise",
                        "terms": {
                            "proximity": round(proximity, 4),
                            "speed_term": round(speed_term, 4),
                            "kinematics": round(kin, 4),
                            "seeded_noise": round(noise, 4),
                        },
                        "params": {
                            "w_proximity": sv["w_proximity"], "w_speed": sv["w_speed"],
                            "w_kinematics": sv["w_kinematics"], "d0_m": d0,
                            "peak_knots": peak, "sigma_knots": sigma,
                            "noise_amplitude": noise_amp, "seed": seed,
                        },
                        "delta": {"dCOG_deg": round(dcog, 1), "dSOG_knots": round(dsog, 2)},
                    },
                },
            )
            events.append(event)
    return events


def derive_metoc_events(
    metoc_cfg: dict, deriv_cfg: dict, cable: Cable, region_bbox: dict, seed: int,
) -> list[Event]:
    """S3: 고파고 구간이 만드는 광역 저신뢰 이벤트(선박 무관, 룰 기반).

    케이블 라인을 따라 균등 분포한 지점에 생성 → 광역·다발·저신뢰 시그니처.
    """
    mc = deriv_cfg["metoc_event"]
    high_wave = [w for w in metoc_cfg["windows"] if w["wave_height_m"] >= mc["wave_height_threshold_m"]]
    if not high_wave:
        return []
    events: list[Event] = []
    n = mc["count_per_window"]
    coords = cable.coords
    for w in high_wave:
        for k in range(n):
            t = (k + 0.5) / n  # 케이블 라인상의 균등 위치(0~1)
            lon = coords[0][0] + t * (coords[-1][0] - coords[0][0])
            lat = coords[0][1] + t * (coords[-1][1] - coords[0][1])
            # 광역 분산: 케이블에서 수백 m 옆으로 결정론적 오프셋
            off = _seeded_noise(seed, f"metoc:{w['start']}:{k}", 0.004)
            ts = pd.Timestamp(w["start"]).isoformat()
            events.append(Event(
                event_id=f"MX-{w['start'].replace(':','').replace('-','')[:12]}-{k:02d}",
                event_time=ts,
                source="underwater_sensor",
                event_type="acoustic",
                location={"lat": round(lat + off, 6), "lon": round(lon + off, 6),
                          "cable_segment_id": cable.segment_id},
                asset_id=cable.segment_id,
                severity=round(mc["severity"], 4),
                confidence=round(mc["confidence"], 4),
                metadata={
                    "derived_from": {
                        "source": "METOC",
                        "metoc_window": w["start"],
                        "wave_height_m": w["wave_height_m"],
                        "current": w.get("current"),
                    },
                    "derivation": {
                        "formula": "metoc 고파고 구간 → 광역 저신뢰 이벤트(룰)",
                        "rule": f"wave_height_m >= {mc['wave_height_threshold_m']}",
                        "params": {"severity": mc["severity"], "confidence": mc["confidence"],
                                   "count_per_window": n},
                    },
                },
            ))
    return events


def derive_sensor_fault_events(
    sensor_cfg: dict, deriv_cfg: dict, cable: Cable, seed: int,
) -> list[Event]:
    """S5: 전원 저하 노드의 반복 이상값(룰 기반, 규칙적 반복이 시그니처)."""
    sf = deriv_cfg["sensor_fault_event"]
    degraded = [n for n in sensor_cfg["nodes"] if n.get("power_status") == "degraded"]
    if not degraded:
        return []
    events: list[Event] = []
    for node in degraded:
        base_t = pd.Timestamp(sensor_cfg["fault_start"])
        for k in range(sf["repeat_count"]):
            ts = (base_t + pd.Timedelta(minutes=sf["interval_minutes"] * k)).isoformat()
            events.append(Event(
                event_id=f"SF-{node['node_id']}-{k:02d}",
                event_time=ts,
                source="underwater_sensor",
                event_type="vibration",
                location={"lat": node["lat"], "lon": node["lon"],
                          "cable_segment_id": cable.segment_id},
                asset_id=node["node_id"],
                severity=round(sf["severity"], 4),
                confidence=round(sf["confidence"], 4),
                metadata={
                    "derived_from": {
                        "source": "sensor_node",
                        "node_id": node["node_id"],
                        "power_status": node["power_status"],
                        "comm_status": node.get("comm_status"),
                    },
                    "derivation": {
                        "formula": "전원 저하 노드 반복 이상값(룰)",
                        "rule": f"power_status=='degraded' → {sf['repeat_count']}회 @ {sf['interval_minutes']}분 간격",
                        "params": {"severity": sf["severity"], "confidence": sf["confidence"]},
                    },
                },
            ))
    return events
