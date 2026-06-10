"""전체 판단 파이프라인 오케스트레이션.

AIS 서브셋 → (시나리오별) 인시던트 수중 이벤트 선정 → 8.2 결합 → 8.3 랭킹
→ 8.4 억제 → 8.5 스코어링 → 분기 → Assessment. 결정론(고정 시드, 정렬 안정).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from cui.ais_subset import get_subset
from cui.config import Config
from cui.couple import couple
from cui.decide import decide
from cui.derive_events import (
    derive_metoc_events,
    derive_sensor_fault_events,
    derive_underwater_events,
)
from cui.geo import Cable
from cui.normalize import vessel_history_flag
from cui.rank import rank_candidates
from cui.score import compute_score
from cui.suppress import compute_discounts


@dataclass
class Assessment:
    scenario_id: str
    scenario_name: str
    incident_event: dict
    coupling: dict
    candidates: list[dict]
    discounts: dict
    score: dict
    decision: dict
    context: dict
    expected: dict
    raw_ais_excerpt: list[dict] = field(default_factory=list)
    derived_events_sample: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class Pipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.df = get_subset(cfg)
        self.cable = Cable.from_config(cfg.pipeline)
        self.seed = cfg.seed

    # --- 인시던트 수중 이벤트 선정 ---
    def _crossing_time(self, mmsi: int):
        """선박 항적이 케이블을 횡단하는 시각(부호변화 구간 중 최근접) 반환. 없으면 None."""
        g = self.df[self.df["mmsi"] == mmsi].dropna(subset=["lat", "lon"]).sort_values("timestamp")
        if len(g) < 2:
            return None
        sides = [self.cable.signed_side(lo, la) for lo, la in zip(g["lon"], g["lat"])]
        ts = g["timestamp"].tolist()
        lons, lats = g["lon"].tolist(), g["lat"].tolist()
        best = None  # (cable_dist_at_crossing, crossing_time)
        for i in range(1, len(sides)):
            if sides[i - 1] == 0 or sides[i] == 0:
                continue
            if (sides[i - 1] > 0) != (sides[i] > 0):  # 부호 변화 = 횡단
                # 횡단 구간 양 끝의 케이블 최단거리 중 작은 쪽
                d = min(self.cable.distance_m(lons[i - 1], lats[i - 1]),
                        self.cable.distance_m(lons[i], lats[i]))
                ct = ts[i]  # 횡단 직후 시각
                if best is None or d < best[0]:
                    best = (d, ct)
        return best[1] if best else None

    def _vessel_incident(self, mmsi: int):
        evs = derive_underwater_events(
            self.df, self.cable, self.cfg.derivation, self.seed, mmsi_filter=[mmsi]
        )
        if not evs:
            return None, []
        # 우선순위: 케이블 횡단 시각 인근 이벤트 → 없으면 최고 severity
        ct = self._crossing_time(mmsi)
        if ct is not None:
            ctp = pd.Timestamp(ct)
            cand = min(
                evs,
                key=lambda e: (abs((pd.Timestamp(e.event_time) - ctp).total_seconds()),
                               -e.severity, e.event_id),
            )
            # 횡단 시각과 너무 멀면(>10분) 횡단 인근 이벤트가 없는 것 → severity 우선
            if abs((pd.Timestamp(cand.event_time) - ctp).total_seconds()) <= 600:
                return cand, evs
        top = sorted(evs, key=lambda e: (-e.severity, e.event_id))[0]
        return top, evs

    def _metoc_incident(self):
        """S3: 광역 METOC 노이즈 중 '인근 의심 선박이 없는' 지점의 이벤트를 incident로 선정.

        스펙 S3 정의('인근 의심 선박 행동 부재')를 만족하도록, 각 METOC 이벤트에서
        ±결합창 내 최근접 선박까지 거리를 구해 가장 고립된(선박에서 먼) 이벤트를 고른다.
        """
        bbox = self.cfg.pipeline["data"]["bbox"]
        evs = derive_metoc_events(
            self.cfg.mock["metoc"], self.cfg.derivation, self.cable, bbox, self.seed
        )
        if not evs:
            return None, []
        win = self.cfg.pipeline["coupling"]["window_minutes"]

        def nearest_vessel_m(e):
            et = pd.Timestamp(e.event_time)
            w = self.df[(self.df["timestamp"] >= et - pd.Timedelta(minutes=win))
                        & (self.df["timestamp"] <= et + pd.Timedelta(minutes=win))]
            elat, elon = e.location["lat"], e.location["lon"]
            if w.empty:
                return float("inf")
            return min(_haversine_m(elat, elon, la, lo) for la, lo in zip(w["lat"], w["lon"]))

        # 선박에서 가장 먼(고립된) 이벤트 우선, 동률 시 event_id
        top = sorted(evs, key=lambda e: (-nearest_vessel_m(e), e.event_id))[0]
        return top, evs

    def _sensor_incident(self):
        evs = derive_sensor_fault_events(
            self.cfg.mock["sensor_nodes"], self.cfg.derivation, self.cable, self.seed
        )
        if not evs:
            return None, []
        top = sorted(evs, key=lambda e: (-e.severity, e.event_id))[0]
        return top, evs

    # --- 컨텍스트 조립 ---
    def _metoc_at(self, event_time: str) -> dict | None:
        et = pd.Timestamp(event_time)
        windows = self.cfg.mock["metoc"]["windows"]
        chosen = None
        for w in windows:
            if pd.Timestamp(w["start"]) <= et:
                chosen = w
        return {"wave_height_m": chosen["wave_height_m"], "current": chosen["current"]} if chosen else None

    def _nearest_node(self, event) -> dict | None:
        elat = event.location.get("lat")
        elon = event.location.get("lon")
        if elat is None:
            return None
        best = None
        for n in self.cfg.mock["sensor_nodes"]["nodes"]:
            d = _haversine_m(elat, elon, n["lat"], n["lon"])
            degraded = n.get("power_status") != "nominal" or n.get("comm_status") != "nominal"
            if best is None or d < best["dist_m"]:
                best = {"node_id": n["node_id"], "dist_m": round(d, 1), "degraded": degraded}
        return best

    def _permit_match(self, mmsi, event) -> dict | None:
        et = pd.Timestamp(event.event_time)
        elat, elon = event.location.get("lat"), event.location.get("lon")
        for p in self.cfg.mock["permits"]["permits"]:
            if p["mmsi"] != mmsi:
                continue
            t0, t1 = pd.Timestamp(p["time_window"][0]), pd.Timestamp(p["time_window"][1])
            if not (t0 <= et <= t1):
                continue
            if elat is not None:
                clon, clat = p["area"]["center"]
                if _haversine_m(elat, elon, clat, clon) > p["area"]["radius_m"]:
                    continue
            return {"permit_id": p["permit_id"], "operator": p["operator"],
                    "work_type": p["work_type"], "mmsi": p["mmsi"]}
        return None

    def _ais_excerpt(self, mmsi, event, n=6) -> list[dict]:
        """이벤트 시각 인근 원본 AIS 행 발췌(체인 문서용)."""
        if mmsi is None:
            return []
        et = pd.Timestamp(event.event_time)
        g = self.df[self.df["mmsi"] == mmsi].sort_values("timestamp").copy()
        g["abs_dt"] = (g["timestamp"] - et).abs()
        sel = g.nsmallest(n, "abs_dt").sort_values("timestamp")
        out = []
        for _, r in sel.iterrows():
            out.append({
                "timestamp": pd.Timestamp(r["timestamp"]).isoformat(),
                "mmsi": int(r["mmsi"]),
                "lat": round(float(r["lat"]), 6), "lon": round(float(r["lon"]), 6),
                "sog": None if pd.isna(r["sog"]) else round(float(r["sog"]), 2),
                "cog": None if pd.isna(r["cog"]) else round(float(r["cog"]), 1),
                "nav_status": r["nav_status"],
                "cable_dist_m": round(self.cable.distance_m(r["lon"], r["lat"]), 1),
            })
        return out

    # --- 시나리오 평가 ---
    def assess(self, scenario: dict) -> Assessment:
        src = scenario["incident_source"]
        mmsi = scenario.get("incident_mmsi")
        derived_sample = []
        if src == "vessel":
            event, all_evs = self._vessel_incident(mmsi)
            derived_sample = [e.to_dict() for e in sorted(all_evs, key=lambda e: (-e.severity, e.event_id))[:3]]
        elif src == "metoc":
            event, all_evs = self._metoc_incident()
            derived_sample = [e.to_dict() for e in all_evs[:3]]
        elif src == "sensor_fault":
            event, all_evs = self._sensor_incident()
            derived_sample = [e.to_dict() for e in all_evs[:3]]
        else:
            raise ValueError(f"알 수 없는 incident_source: {src}")
        if event is None:
            raise RuntimeError(f"{scenario['id']}: 인시던트 이벤트 생성 실패")

        coupling = couple(self.df, event, self.cable, self.cfg.pipeline["coupling"])
        prim = coupling.primary()

        # 컨텍스트
        permit_match = None
        if scenario.get("enable_permit") and mmsi is not None:
            permit_match = self._permit_match(mmsi, event)
        history = None
        if scenario.get("enable_history") and mmsi is not None:
            history = vessel_history_flag(self.cfg.mock["vessel_history"], mmsi)
        prim_nav = ""
        if prim is not None:
            gp = self.df[self.df["mmsi"] == prim.mmsi]["nav_status"]
            prim_nav = gp.mode().iloc[0] if not gp.mode().empty else ""

        ctx = {
            "incident_source": src,
            "permit_match": permit_match,
            "metoc_at_event": self._metoc_at(event.event_time),
            "nearest_node": self._nearest_node(event),
            "sensor_repeat": src == "sensor_fault",
            "vessel_history": history,
            "primary_nav_status": prim_nav,
            "buffer_m": self.cable.buffer_m,
            "metoc_wave_threshold": self.cfg.derivation["metoc_event"]["wave_height_threshold_m"],
        }

        candidates = rank_candidates(event, coupling, ctx, self.cable.buffer_m)
        discounts = compute_discounts(ctx, coupling, self.cfg.scoring)
        score = compute_score(event, coupling, ctx, discounts, self.cfg.scoring)
        decision = decide(candidates, score.risk, self.cfg.pipeline["decision"])

        return Assessment(
            scenario_id=scenario["id"],
            scenario_name=scenario["name"],
            incident_event=event.to_dict(),
            coupling=coupling.to_dict(),
            candidates=[c.to_dict() for c in candidates],
            discounts=discounts.to_dict(),
            score=score.to_dict(),
            decision=decision.to_dict(),
            context={k: v for k, v in ctx.items()},
            expected={"decision": scenario.get("expected_decision"),
                      "top_candidate": scenario.get("expected_top_candidate")},
            raw_ais_excerpt=self._ais_excerpt(mmsi, event) if src == "vessel" else [],
            derived_events_sample=derived_sample,
        )
