"""[커밋①] 케이블 인근 저속·표류 항적 자동 탐색 → 후보 구역 보고.

스펙: bbox 안에 가상 케이블 라인을 긋고, 그 주변을 저속(≤3kt)으로 통과/체류하는
실제 항적이 ≥3척 포함되는 구역을 찾는다.

앵커 드래깅(S1)에 의미있는 신호는 '저속이면서 위치가 표류(drift)하며 케이블을
가로지르는' 선박이다. 종일 0kt 고정 정박선은 S1엔 부적합하나 S2/S5 대조군으론 유용.
따라서:
  - 저속(≤slow) 포인트로 밀집 구역(anchorage/approach)을 찾고,
  - 그 안에서 '표류 선박'(저속 구간 공간범위 ≥ drift_min_m)을 식별,
  - 케이블을 1순위 표류 선박의 표류 경로에 '수직'으로 놓아 횡단이 성립하게 한다,
  - 저속 선박 ≥min_slow_vessels 그리고 표류 선박 ≥min_drift_vessels 인 구역만 후보.

결정론: 모든 정렬·선택은 안정 정렬 + 고정 기준. 난수 없음.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cui.geo import M_PER_DEG_LAT, Cable, m_per_deg_lon, track_crossings


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@dataclass
class RegionCandidate:
    rank: int
    centroid_lon: float
    centroid_lat: float
    cable_line: list[list[float]]
    slow_vessels: list[int]
    drift_vessels: list[int]
    primary_vessel: int
    n_slow_vessels: int
    n_drift_vessels: int
    n_slow_points: int
    time_span: tuple[str, str]
    vessel_summaries: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def slow_drift_features(df: pd.DataFrame, slow_kt: float) -> dict[int, dict]:
    """MMSI별 저속 구간 특징: 포인트수, 공간범위(extent_m), 표류경로(m),
    표류 방위(start→end), 중심좌표, 평균 SOG, 지배 상태."""
    out: dict[int, dict] = {}
    for mmsi, g in df.groupby("mmsi", sort=True):
        g = g.sort_values("timestamp")
        slow = g[g["sog"] <= slow_kt]
        if len(slow) < 3:
            continue
        lat = slow["lat"].to_numpy()
        lon = slow["lon"].to_numpy()
        extent_m = _haversine_km(lat.min(), lon.min(), lat.max(), lon.max()) * 1000
        path_m = sum(
            _haversine_km(lat[i - 1], lon[i - 1], lat[i], lon[i]) * 1000
            for i in range(1, len(lat))
        )
        bearing = math.degrees(math.atan2(lon[-1] - lon[0], lat[-1] - lat[0])) % 360
        status = g["nav_status"].astype(str)
        out[int(mmsi)] = {
            "mmsi": int(mmsi),
            "n_slow": int(len(slow)),
            "extent_m": round(extent_m, 1),
            "drift_path_m": round(path_m, 1),
            "drift_bearing": round(bearing, 1),
            "clon": float(lon.mean()),
            "clat": float(lat.mean()),
            "min_sog": round(float(slow["sog"].min()), 2),
            "mean_sog": round(float(slow["sog"].mean()), 2),
            "status": status.mode().iloc[0] if not status.mode().empty else "",
        }
    return out


def _grid_key(lon, lat, cell_deg):
    return (math.floor(lon / cell_deg), math.floor(lat / cell_deg))


def find_candidates(df: pd.DataFrame, rf_cfg: dict, cable_buffer_m: float) -> list[RegionCandidate]:
    slow_kt = rf_cfg["slow_speed_knots"]
    drift_min = rf_cfg["drift_min_m"]
    proximity_m = rf_cfg["proximity_m"]
    min_slow = rf_cfg["min_slow_vessels"]
    min_drift = rf_cfg["min_drift_vessels"]
    top_n = rf_cfg["candidate_count"]
    cell_deg = 0.02

    feats = slow_drift_features(df, slow_kt)
    if not feats:
        return []

    slow = df[df["sog"] <= slow_kt].copy()
    slow["cell"] = [_grid_key(lon, lat, cell_deg) for lon, lat in zip(slow["lon"], slow["lat"])]
    cell_stats = (
        slow.groupby("cell")
        .agg(n_vessels=("mmsi", "nunique"), n_points=("mmsi", "size"),
             lon=("lon", "mean"), lat=("lat", "mean"))
        .reset_index()
        .sort_values(["n_vessels", "n_points", "cell"], ascending=[False, False, True])
        .reset_index(drop=True)
    )

    candidates: list[RegionCandidate] = []
    used_cells: set = set()
    for _, row in cell_stats.iterrows():
        if len(candidates) >= top_n:
            break
        cell = row["cell"]
        if any((cell[0] + dx, cell[1] + dy) in used_cells
               for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            continue
        cand = _build_candidate(
            df, feats, float(row["lon"]), float(row["lat"]),
            slow_kt, drift_min, proximity_m, cable_buffer_m, len(candidates) + 1,
        )
        if cand and cand.n_slow_vessels >= min_slow and cand.n_drift_vessels >= min_drift:
            candidates.append(cand)
            used_cells.add(cell)
    return candidates


def _build_candidate(df, feats, clon, clat, slow_kt, drift_min, proximity_m, buffer_m, rank):
    win_lat = (proximity_m * 1.5) / M_PER_DEG_LAT
    win_lon = (proximity_m * 1.5) / m_per_deg_lon(clat)

    # 이 셀 인근에 저속 중심이 있는 선박들
    local = [
        f for f in feats.values()
        if abs(f["clat"] - clat) <= win_lat and abs(f["clon"] - clon) <= win_lon
    ]
    if not local:
        return None
    drift_local = [f for f in local if f["extent_m"] >= drift_min]
    if not drift_local:
        return None
    # 1순위 표류 선박 = 표류 범위 최대(동률 시 MMSI 작은 쪽)
    primary = sorted(drift_local, key=lambda f: (-f["extent_m"], f["mmsi"]))[0]

    # 케이블: 1순위 표류 선박의 표류 방위에 '수직'으로, 그 저속 중심을 지나게 배치
    perp = (primary["drift_bearing"] + 90.0) % 360
    half_len_m = 2000.0
    dlat = (half_len_m * math.cos(math.radians(perp))) / M_PER_DEG_LAT
    dlon = (half_len_m * math.sin(math.radians(perp))) / m_per_deg_lon(primary["clat"])
    pclon, pclat = primary["clon"], primary["clat"]
    line = [[pclon - dlon, pclat - dlat], [pclon + dlon, pclat + dlat]]
    cable = Cable(line, buffer_m, f"CAND-{rank}")

    # proximity_m 내 저속 선박 집계 + 횡단 계산
    near = df[
        df["lat"].between(clat - win_lat, clat + win_lat)
        & df["lon"].between(clon - win_lon, clon + win_lon)
    ].copy()
    near["dist_m"] = [cable.distance_m(lon, lat) for lon, lat in zip(near["lon"], near["lat"])]
    inzone = near[near["dist_m"] <= proximity_m]
    slow_inzone = inzone[inzone["sog"] <= slow_kt]
    if slow_inzone.empty:
        return None
    slow_vessels = sorted(int(m) for m in slow_inzone["mmsi"].dropna().unique())

    summaries, drift_vessels = [], []
    for mmsi in slow_vessels:
        g = df[df["mmsi"] == mmsi].sort_values("timestamp")
        crossings = track_crossings(list(zip(g["lon"], g["lat"])), cable)
        f = feats.get(mmsi, {})
        ext = f.get("extent_m", 0.0)
        is_drift = ext >= drift_min
        if is_drift:
            drift_vessels.append(mmsi)
        gz = inzone[inzone["mmsi"] == mmsi]
        summaries.append({
            "mmsi": mmsi,
            "is_drift": is_drift,
            "is_primary": mmsi == primary["mmsi"],
            "n_points_inzone": int(len(gz)),
            "min_sog": round(float(gz["sog"].min()), 2),
            "mean_sog": round(float(gz["sog"].mean()), 2),
            "extent_m": ext,
            "drift_path_m": f.get("drift_path_m", 0.0),
            "min_dist_m": round(float(gz["dist_m"].min()), 1),
            "cable_crossings": int(crossings),
            "nav_status": f.get("status", ""),
        })
    summaries.sort(key=lambda s: (not s["is_primary"], -s["cable_crossings"], -s["extent_m"]))
    ts = inzone["timestamp"]
    return RegionCandidate(
        rank=rank,
        centroid_lon=round(clon, 5),
        centroid_lat=round(clat, 5),
        cable_line=[[round(line[0][0], 5), round(line[0][1], 5)],
                    [round(line[1][0], 5), round(line[1][1], 5)]],
        slow_vessels=slow_vessels,
        drift_vessels=sorted(drift_vessels),
        primary_vessel=primary["mmsi"],
        n_slow_vessels=len(slow_vessels),
        n_drift_vessels=len(drift_vessels),
        n_slow_points=int(len(slow_inzone)),
        time_span=(str(ts.min()), str(ts.max())),
        vessel_summaries=summaries,
    )


def report(candidates: list[RegionCandidate]) -> str:
    lines = ["# 후보 구역 (케이블 인근 저속·표류 항적)", ""]
    if not candidates:
        lines.append("적합 후보 없음 — bbox/시간창을 옮겨 재탐색 필요.")
        return "\n".join(lines)
    for c in candidates:
        lines.append(f"## 후보 {c.rank} — 중심 ({c.centroid_lat}, {c.centroid_lon})")
        lines.append(f"- 제안 케이블: {c.cable_line}")
        lines.append(f"- 저속 {c.n_slow_vessels}척 / 표류 {c.n_drift_vessels}척 / 1순위 표류선박 MMSI {c.primary_vessel}")
        lines.append(f"- 저속 포인트 {c.n_slow_points}개, 시간 {c.time_span[0]} ~ {c.time_span[1]}")
        lines.append("- 선박 요약(1순위·횡단·표류 우선):")
        for s in c.vessel_summaries:
            tag = "★표류" if s["is_drift"] else "정박"
            star = "[1순위]" if s["is_primary"] else ""
            lines.append(
                f"  - {star}MMSI {s['mmsi']} ({tag}): inzone {s['n_points_inzone']}pt, "
                f"SOG {s['min_sog']}~{s['mean_sog']}kt, 표류범위 {s['extent_m']}m, "
                f"케이블최단 {s['min_dist_m']}m, 횡단 {s['cable_crossings']}회, '{s['nav_status']}'"
            )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import json

    from cui.ais_subset import get_subset
    from cui.config import load_config

    cfg = load_config()
    df = get_subset(cfg)
    cands = find_candidates(df, cfg.pipeline["region_finder"], cfg.pipeline["cable"]["buffer_m"])
    print(report(cands))
    out = cfg.root / "data" / "region_candidates.json"
    out.write_text(json.dumps([c.to_dict() for c in cands], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[저장] {out}")
