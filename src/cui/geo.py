"""지오 연산 유틸 — 케이블 LineString, 최단거리, 보호구역 진입/체류, 횡단 카운트.

좌표는 [lon, lat] 순서(shapely 관례). 발트해 중위도에서 평면 근사 대신
미터 환산은 위도별 경도 축척을 반영한 로컬 등거리 투영(approx)으로 처리한다.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import LineString, Point

# 위도 1도 ≈ 111320 m. 경도 1도 ≈ 111320*cos(lat).
M_PER_DEG_LAT = 111_320.0


def m_per_deg_lon(lat_deg: float) -> float:
    return M_PER_DEG_LAT * math.cos(math.radians(lat_deg))


def to_local_xy(lon, lat, lat0):
    """기준 위도 lat0 에서 로컬 등거리 평면 좌표(m)로 변환."""
    x = (np.asarray(lon)) * m_per_deg_lon(lat0)
    y = (np.asarray(lat)) * M_PER_DEG_LAT
    return x, y


class Cable:
    """가상 케이블 라인 + 보호구역(버퍼)."""

    def __init__(self, coords: list[list[float]], buffer_m: float, segment_id: str):
        self.coords = coords  # [[lon,lat], ...]
        self.buffer_m = buffer_m
        self.segment_id = segment_id
        self.lat0 = float(np.mean([c[1] for c in coords])) if coords else 0.0
        # 로컬 평면 LineString(m)
        xs, ys = to_local_xy([c[0] for c in coords], [c[1] for c in coords], self.lat0)
        self.line_m = LineString(list(zip(xs, ys)))
        self.line_geo = LineString([(c[0], c[1]) for c in coords])  # 경위도(도)

    def distance_m(self, lon: float, lat: float) -> float:
        """포인트→케이블 최단거리(m)."""
        x, y = to_local_xy(lon, lat, self.lat0)
        return float(self.line_m.distance(Point(float(x), float(y))))

    def in_protection_zone(self, lon: float, lat: float) -> bool:
        return self.distance_m(lon, lat) <= self.buffer_m

    def signed_side(self, lon: float, lat: float) -> float:
        """케이블(첫점→끝점) 기준 점의 부호 방향(>0/<0). 부호 변화 = 횡단.

        로컬 평면에서 (방향벡터) × (점-시작점) 의 z성분 부호.
        """
        x, y = to_local_xy(lon, lat, self.lat0)
        ax, ay = self.line_m.coords[0]
        bx, by = self.line_m.coords[-1]
        return (bx - ax) * (float(y) - ay) - (by - ay) * (float(x) - ax)

    @classmethod
    def from_config(cls, pipeline_cfg: dict) -> "Cable":
        c = pipeline_cfg["cable"]
        return cls(c["line"], c["buffer_m"], c["segment_id"])


def crossing_times(track_lonlat_ts: list[tuple[float, float, object]], cable: Cable) -> list:
    """연속 포인트 경로가 케이블 세그먼트와 교차하는 시각 목록(횡단 직후 포인트 시각).

    track_lonlat_ts: [(lon, lat, timestamp), ...] 시간순 정렬 가정.
    샘플링 경계와 무관하게 '횡단이 일어난 시각'을 정확히 잡기 위해 전체 항적에서 계산.
    """
    if len(track_lonlat_ts) < 2:
        return []
    lons = [p[0] for p in track_lonlat_ts]
    lats = [p[1] for p in track_lonlat_ts]
    xs, ys = to_local_xy(lons, lats, cable.lat0)
    out = []
    for i in range(1, len(track_lonlat_ts)):
        seg = LineString([(xs[i - 1], ys[i - 1]), (xs[i], ys[i])])
        if seg.intersects(cable.line_m):
            out.append(track_lonlat_ts[i][2])
    return out


def track_crossings(track_lonlat: list[tuple[float, float]], cable: Cable) -> int:
    """선박 항적이 케이블을 횡단한 횟수(선분 교차 수)."""
    if len(track_lonlat) < 2:
        return 0
    xs, ys = to_local_xy(
        [p[0] for p in track_lonlat], [p[1] for p in track_lonlat], cable.lat0
    )
    path = LineString(list(zip(xs, ys)))
    inter = path.intersection(cable.line_m)
    if inter.is_empty:
        return 0
    geom_type = inter.geom_type
    if geom_type == "Point":
        return 1
    if geom_type == "MultiPoint":
        return len(inter.geoms)
    # 선분이 겹치는 경우 등은 1회로 보수적 카운트
    return 1
