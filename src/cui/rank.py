"""8.3 원인 후보 랭킹 — 각 후보에 신뢰도 점수 + 주요 기여 요인 목록(설명가능).

후보: specific_vessel, ais_dark, permitted_maintenance, legal_fishing,
      natural_noise, sensor_fault. 블랙박스 점수 금지 — 모든 점수는 요인 가중합.

ctx(dict) 키:
  incident_source: 'vessel'|'metoc'|'sensor_fault'
  permit_match: dict|None        # 허가 일치(mmsi+시간+구역)
  metoc_at_event: dict|None      # {wave_height_m, current}
  nearest_node: dict|None        # {node_id, degraded, dist_m}
  sensor_repeat: bool            # 규칙적 반복 이상값 패턴
  vessel_history: dict|None      # primary 선박 반복접근 이력
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cui.couple import CouplingResult, VesselBehavior


@dataclass
class Candidate:
    name: str
    score: float                       # 0~1
    factors: list[dict] = field(default_factory=list)  # [{factor, value, contribution}]

    def to_dict(self) -> dict:
        return {"name": self.name, "score": round(self.score, 4), "factors": self.factors}


def _f(name, value, contribution):
    return {"factor": name, "value": value, "contribution": round(contribution, 4)}


def _clamp01(x):
    return max(0.0, min(1.0, x))


def _activity(v: VesselBehavior) -> float:
    """선박 '활동성 의심' 정도(0~1). 정박(0kt·무횡단·무선회)은 ~0.

    앵커드래그/AIS-dark 같은 능동 위협은 횡단·표류·이동·급선회로 나타난다.
    """
    cross = _clamp01(v.cable_crossings / 1.0)
    turn = _clamp01(v.max_turn_deg / 90.0)
    move = _clamp01(v.speed_mean_kt / 2.0 + min(v.speed_var, 1.0))  # 표류/이동
    gap = _clamp01(v.ais_gap_minutes / 60.0)
    return _clamp01(max(cross, turn, 0.7 * move, 0.6 * gap))


def rank_candidates(event, coupling: CouplingResult, ctx: dict, buffer_m: float) -> list[Candidate]:
    prim: VesselBehavior | None = coupling.primary()
    cands: list[Candidate] = []

    # --- specific_vessel ---
    # 핵심: 케이블 근접·체류는 '활동성(activity)'으로 게이팅한다. 정박만 한 선박은
    # 근접해도 위협이 아니므로 낮게. 횡단/표류/이동/급선회가 있어야 위협으로 본다.
    f = []
    s = 0.0
    if prim is not None:
        act = _activity(prim)
        prox = _clamp01(1.0 - prim.min_cable_dist_m / (buffer_m * 2)) if prim.min_cable_dist_m is not None else 0.0
        space = _clamp01(1.0 - (prim.event_space_dist_m or 9999) / (buffer_m * 2))
        # 행동 신호(횡단·체류·급선회·이동) — 위협의 본체
        behavior = (
            0.40 * _clamp01(prim.cable_crossings / 1.0)
            + 0.25 * _clamp01(prim.dwell_in_zone_s / 1800.0)
            + 0.15 * _clamp01(prim.max_turn_deg / 90.0)
            + 0.20 * _clamp01(prim.speed_mean_kt / 2.0 + min(prim.speed_var, 1.0))
        )
        # 근접·공간근접은 행동을 증폭(게이트). 행동이 0이면 점수도 ~0.
        gate = 0.6 * prox + 0.4 * space
        s = behavior * (0.5 + 0.5 * gate) * (0.4 + 0.6 * act)
        f = [
            _f("활동성(횡단/표류/이동/급선회)", round(act, 3), 0.0),
            _f("케이블 횡단", f"{prim.cable_crossings}회", 0.40 * _clamp01(prim.cable_crossings / 1.0)),
            _f("보호구역 체류", f"{prim.dwell_in_zone_s}s", 0.25 * _clamp01(prim.dwell_in_zone_s / 1800.0)),
            _f("이동/표류(속도)", f"mean {prim.speed_mean_kt}kt var {prim.speed_var}",
               0.20 * _clamp01(prim.speed_mean_kt / 2.0 + min(prim.speed_var, 1.0))),
            _f("케이블 근접", f"{prim.min_cable_dist_m}m", round(0.6 * prox, 3)),
            _f("이벤트 공간근접", f"{prim.event_space_dist_m}m", round(0.4 * space, 3)),
        ]
        if ctx.get("vessel_history") and act > 0.2:
            bonus = 0.12
            s = _clamp01(s + bonus)
            f.append(_f("반복접근 이력", f"{ctx['vessel_history'].get('repeat_slow_approaches')}회", bonus))
    cands.append(Candidate("specific_vessel", _clamp01(s), f))

    # --- ais_dark ---
    f = []
    s = 0.0
    if prim is not None and prim.ais_gap_minutes > 0:
        c_gap = 0.6 * _clamp01(prim.ais_gap_minutes / 60.0)        # 60분 끊김=만점
        c_prox = 0.4 * (_clamp01(1.0 - prim.min_cable_dist_m / (buffer_m * 2)))
        s = c_gap + c_prox
        f = [
            _f("AIS 끊김 길이", f"{prim.ais_gap_minutes}min", c_gap),
            _f("끊김 전 케이블 근접", f"{prim.min_cable_dist_m}m", c_prox),
        ]
    cands.append(Candidate("ais_dark", _clamp01(s), f))

    # --- permitted_maintenance ---
    f = []
    s = 0.0
    pm = ctx.get("permit_match")
    if pm:
        s = 0.95
        f = [_f("허가 일치(MMSI+시간+구역)", pm.get("permit_id"), 0.95)]
    cands.append(Candidate("permitted_maintenance", s, f))

    # --- legal_fishing ---
    f = []
    s = 0.0
    if prim is not None:
        navs = ctx.get("primary_nav_status", "")
        if "fishing" in str(navs).lower():
            s = 0.7
            f = [_f("항법상태 조업", navs, 0.7)]
    cands.append(Candidate("legal_fishing", s, f))

    # --- natural_noise ---
    f = []
    s = 0.0
    met = ctx.get("metoc_at_event")
    if met:
        wave = met.get("wave_height_m", 0.0)
        thr = ctx.get("metoc_wave_threshold", 2.5)
        c_wave = 0.7 * _clamp01((wave - 1.0) / (thr * 1.5))
        # '활동성 의심 선박' 부재일수록 자연 노이즈 가능성↑(정박선은 의심 아님)
        max_act = max((_activity(v) for v in coupling.vessels), default=0.0)
        absent = max_act < 0.25
        c_absence = 0.3 * (1.0 if absent else 0.0)
        s = c_wave + c_absence
        f = [
            _f("파고", f"{wave}m", c_wave),
            _f("활동성 의심 선박 부재", f"{'예' if absent else '아니오'}(max_act {round(max_act,3)})", c_absence),
        ]
    cands.append(Candidate("natural_noise", _clamp01(s), f))

    # --- sensor_fault ---
    f = []
    s = 0.0
    node = ctx.get("nearest_node")
    if node and node.get("degraded"):
        # 단순히 전원저하 노드가 근처라는 것만으론 약한 근거(0.3). 인시던트가 실제로
        # 규칙적 반복 이상값(센서 소스)일 때 비로소 강한 근거(+0.5).
        c_deg = 0.3
        c_rep = 0.5 if ctx.get("sensor_repeat") else 0.0
        s = c_deg + c_rep
        f = [_f("최근접 노드 전원저하", node.get("node_id"), c_deg)]
        if ctx.get("sensor_repeat"):
            f.append(_f("규칙적 반복 이상값", "예", c_rep))
    cands.append(Candidate("sensor_fault", _clamp01(s), f))

    # 점수 내림차순(동률 시 이름 사전순 — 결정론)
    cands.sort(key=lambda c: (-c.score, c.name))
    return cands
