"""[커밋①] DMA 발트해 AIS — 다운로드 + bbox/시간창 서브셋 + 정제.

DMA 일 단위 파일은 압축 해제 시 수 GB 다. 전체를 풀지 않고 zip 멤버를 스트리밍하며
bbox 로 즉시 필터링해 메모리를 아낀다(원칙: 결정론적·재현 가능한 서브셋).

CSV 포맷(DMA aisdk):
  - 콤마 구분, 헤더 첫 컬럼은 '# Timestamp'
  - 소수점은 마침표, Timestamp 는 DD/MM/YYYY HH:MM:SS
  - 사용 컬럼: Timestamp, MMSI, Latitude, Longitude, SOG, COG, Navigational status, Type of mobile
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

# DMA 원본 컬럼명(헤더의 '# ' 접두 제거 후)
COL_MAP = {
    "Timestamp": "timestamp",
    "MMSI": "mmsi",
    "Latitude": "lat",
    "Longitude": "lon",
    "SOG": "sog",
    "COG": "cog",
    "Navigational status": "nav_status",
    "Type of mobile": "mobile_type",
}
USE_COLS = list(COL_MAP.keys())


def download(url: str, dest: Path, chunk_mb: int = 8) -> Path:
    """일 단위 zip 다운로드(이미 있으면 건너뜀)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with requests.get(url, stream=True, timeout=1800) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_mb * 1024 * 1024):
                f.write(chunk)
    return dest


def _read_zip_chunks(zip_path: Path, chunksize: int = 500_000):
    """zip 내부 CSV 멤버를 청크 단위로 스트리밍(전체 압축 해제 없이)."""
    zf = zipfile.ZipFile(zip_path)
    member = zf.namelist()[0]
    raw = zf.open(member)
    text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
    # 헤더의 '# Timestamp' → 'Timestamp' 로 정규화하기 위해 첫 줄을 직접 읽어 교체
    header_line = text.readline().lstrip("#").strip()
    names = [c.strip() for c in header_line.split(",")]
    reader = pd.read_csv(
        text,
        names=names,
        usecols=[c for c in USE_COLS if c in names],
        chunksize=chunksize,
        dtype=str,
        na_filter=False,
    )
    for chunk in reader:
        yield chunk
    raw.close()


def subset_bbox(
    zip_path: Path,
    bbox: dict,
    date: str,
) -> pd.DataFrame:
    """zip 을 스트리밍하며 bbox 안 포인트만 수집 → 정제 전 raw DataFrame."""
    lat_min, lat_max = bbox["lat_min"], bbox["lat_max"]
    lon_min, lon_max = bbox["lon_min"], bbox["lon_max"]
    parts: list[pd.DataFrame] = []
    for chunk in _read_zip_chunks(zip_path):
        chunk = chunk.rename(columns=COL_MAP)
        # 수치 변환(빈 문자열 → NaN)
        for col in ("lat", "lon", "sog", "cog"):
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        m = (
            chunk["lat"].between(lat_min, lat_max)
            & chunk["lon"].between(lon_min, lon_max)
        )
        sub = chunk.loc[m].copy()
        if len(sub):
            parts.append(sub)
    if not parts:
        return pd.DataFrame(columns=list(COL_MAP.values()))
    df = pd.concat(parts, ignore_index=True)
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="%d/%m/%Y %H:%M:%S", errors="coerce"
    )
    df["mmsi"] = pd.to_numeric(df["mmsi"], errors="coerce").astype("Int64")
    return df


def clean(df: pd.DataFrame, max_speed_knots: float, min_points: int) -> pd.DataFrame:
    """정제: 결측·중복·비물리적 점프 제거, 항적 최소 길이 필터.

    - 좌표/시각 결측 행 제거
    - (mmsi, timestamp) 중복 제거
    - 연속 포인트 환산속도가 max_speed_knots 초과면 점프로 보고 해당 포인트 제거
    - 포인트 수 < min_points 인 MMSI 제거
    """
    df = df.dropna(subset=["lat", "lon", "timestamp", "mmsi"]).copy()
    df = df.drop_duplicates(subset=["mmsi", "timestamp"])
    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)

    # 비물리적 점프 제거(haversine 환산속도)
    df = _drop_jumps(df, max_speed_knots)

    # 최소 포인트 필터
    counts = df.groupby("mmsi")["timestamp"].transform("size")
    df = df.loc[counts >= min_points].reset_index(drop=True)
    return df


def _drop_jumps(df: pd.DataFrame, max_speed_knots: float) -> pd.DataFrame:
    import numpy as np

    keep = []
    for _, g in df.groupby("mmsi", sort=False):
        g = g.sort_values("timestamp")
        lat = g["lat"].to_numpy()
        lon = g["lon"].to_numpy()
        ts = g["timestamp"].astype("int64").to_numpy() / 1e9  # 초
        ok = [True] * len(g)
        prev = 0
        for i in range(1, len(g)):
            dt = ts[i] - ts[prev]
            if dt <= 0:
                ok[i] = False
                continue
            dist_nm = _haversine_nm(lat[prev], lon[prev], lat[i], lon[i])
            speed = dist_nm / (dt / 3600.0)
            if speed > max_speed_knots:
                ok[i] = False  # 점프 포인트 버리고 prev 유지
            else:
                prev = i
        keep.append(g.loc[ok])
    return pd.concat(keep, ignore_index=True) if keep else df


def _haversine_nm(lat1, lon1, lat2, lon2):
    import numpy as np

    R_nm = 3440.065
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R_nm * np.arcsin(np.sqrt(a))


def get_subset(cfg, force: bool = False) -> pd.DataFrame:
    """파이프라인 진입점: 다운로드→서브셋→정제. 캐시 parquet 사용."""
    data_cfg = cfg.pipeline["data"]
    date = data_cfg["date"]
    root = cfg.root
    zip_path = root / "data" / f"aisdk-{date}.zip"
    cache = root / "data" / f"subset-{date}.pkl"
    if cache.exists() and not force:
        return pd.read_pickle(cache)
    download(data_cfg["source_url"], zip_path)
    raw = subset_bbox(zip_path, data_cfg["bbox"], date)
    df = clean(raw, data_cfg["max_speed_knots"], data_cfg["min_points_per_track"])
    df.to_pickle(cache)
    # 사람이 검수할 수 있도록 CSV 발췌도 함께 저장
    df.to_csv(root / "data" / f"subset-{date}.csv", index=False)
    return df


if __name__ == "__main__":
    from cui.config import load_config

    cfg = load_config()
    df = get_subset(cfg, force=True)
    print(f"서브셋 포인트: {len(df):,}  고유 MMSI: {df['mmsi'].nunique()}")
    print(df.head())
