"""8.2 시공간 결합 — 수중 이벤트 기준 ±window 창에서 보호구역 인근 선박 행동 결합.

특징량: 케이블 최단거리, 보호구역 진입/체류 시간, 속도 평균·분산, 케이블 횡단 횟수,
급회전, AIS 끊김 길이, 이벤트-행동 시간차, 이벤트-선박 공간거리.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cui.geo import Cable, crossing_times, track_crossings


@dataclass
class VesselBehavior:
    mmsi: int
    min_cable_dist_m: float
    dwell_in_zone_s: float           # 보호구역(버퍼) 내 체류 시간(초)
    entered_zone: bool
    speed_mean_kt: float
    speed_var: float
    cable_crossings: int
    max_turn_deg: float              # 급회전 최대 COG 변화
    ais_gap_minutes: float           # 창 내 최대 AIS 끊김(분)
    event_time_diff_s: float         # 이벤트~최근접 행동 시간차(초)
    event_space_dist_m: float        # 이벤트 위치~선박 최근접 공간거리(m)
    n_points: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class CouplingResult:
    event_id: str
    window_minutes: float
    vessels: list[VesselBehavior] = field(default_factory=list)
    primary_mmsi: int | None = None  # 가장 강하게 결합된 선박

    def primary(self) -> VesselBehavior | None:
        for v in self.vessels:
            if v.mmsi == self.primary_mmsi:
                return v
        return None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "window_minutes": self.window_minutes,
            "primary_mmsi": self.primary_mmsi,
            "vessels": [v.to_dict() for v in self.vessels],
        }


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _angle_diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def couple(df: pd.DataFrame, event, cable: Cable, coupling_cfg: dict) -> CouplingResult:
    """이벤트 ±window 창에서 보호구역 인근 선박 행동을 결합."""
    win = coupling_cfg["window_minutes"]
    gap_min = coupling_cfg["ais_gap_min_minutes"]
    et = pd.Timestamp(event.event_time)
    elat = event.location.get("lat")
    elon = event.location.get("lon")
    t0, t1 = et - pd.Timedelta(minutes=win), et + pd.Timedelta(minutes=win)

    window_df = df[(df["timestamp"] >= t0) & (df["timestamp"] <= t1)]
    # 보호구역 근방(버퍼*4) 선박만 고려해 비용 절감
    cand_mmsi = set()
    for mmsi, g in window_df.groupby("mmsi"):
        dmin = min(cable.distance_m(lo, la) for lo, la in zip(g["lon"], g["lat"]))
        if dmin <= cable.buffer_m * 4:
            cand_mmsi.add(int(mmsi))

    result = CouplingResult(event_id=event.event_id, window_minutes=win)
    for mmsi in sorted(cand_mmsi):
        g = window_df[window_df["mmsi"] == mmsi].sort_values("timestamp")
        # 횡단은 전체 항적 기준 횡단 시각이 창 시간에 드는 수로 카운트(샘플링 경계 아티팩트 방지)
        full = df[df["mmsi"] == mmsi].dropna(subset=["lat", "lon"]).sort_values("timestamp")
        xt = crossing_times(list(zip(full["lon"], full["lat"], full["timestamp"])), cable)
        crossings = sum(1 for t in xt if t0 <= pd.Timestamp(t) <= t1)
        dists = np.array([cable.distance_m(lo, la) for lo, la in zip(g["lon"], g["lat"])])
        in_zone = dists <= cable.buffer_m
        # 체류 시간(연속 in-zone 포인트 시간폭)
        dwell_s = 0.0
        if in_zone.any():
            tz = g.loc[in_zone, "timestamp"]
            dwell_s = (tz.max() - tz.min()).total_seconds()
        sog = g["sog"].dropna()
        cog = g["cog"].dropna().to_numpy()
        max_turn = max(
            (_angle_diff(cog[i], cog[i - 1]) for i in range(1, len(cog))), default=0.0
        )
        # AIS 끊김
        dt = g["timestamp"].diff().dt.total_seconds().dropna() / 60
        ais_gap = float(dt[dt >= gap_min].max()) if (dt >= gap_min).any() else 0.0
        # 이벤트-선박 공간거리
        if elat is not None:
            sp = np.array([_haversine_m(elat, elon, la, lo) for la, lo in zip(g["lat"], g["lon"])])
            space_dist = float(sp.min())
            t_at_min = g.iloc[int(sp.argmin())]["timestamp"]
            time_diff = abs((t_at_min - et).total_seconds())
        else:
            space_dist = float("nan")
            time_diff = 0.0
        result.vessels.append(VesselBehavior(
            mmsi=mmsi,
            min_cable_dist_m=round(float(dists.min()), 1),
            dwell_in_zone_s=round(dwell_s, 1),
            entered_zone=bool(in_zone.any()),
            speed_mean_kt=round(float(sog.mean()), 3) if len(sog) else 0.0,
            speed_var=round(float(sog.var()), 4) if len(sog) > 1 else 0.0,
            cable_crossings=int(crossings),
            max_turn_deg=round(float(max_turn), 1),
            ais_gap_minutes=round(ais_gap, 1),
            event_time_diff_s=round(time_diff, 1),
            event_space_dist_m=round(space_dist, 1) if not math.isnan(space_dist) else None,
            n_points=int(len(g)),
        ))
    # 1순위 선박: (보호구역 진입) → (이벤트 공간근접) → (케이블 근접) 우선
    if result.vessels:
        def keyf(v: VesselBehavior):
            return (
                not v.entered_zone,
                v.event_space_dist_m if v.event_space_dist_m is not None else 1e9,
                v.min_cable_dist_m,
            )
        result.primary_mmsi = sorted(result.vessels, key=keyf)[0].mmsi
    return result
