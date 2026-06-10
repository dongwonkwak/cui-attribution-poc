# 증거 패키지 — S2 허가 정비 오탐 억제

> 합성 파생 데이터 기반 판단 로직 검산. 탐지 성능 주장 아님.

## 1. 이벤트 요약
- 인시던트 이벤트: `UW-219027963-0096` (underwater_sensor/acoustic)
- severity **0.6902**, confidence **0.9095**

## 2. 시각·위치
- 시각: `2026-06-03T07:14:59`
- 위치: {"lat": 55.18616, "lon": 14.702547, "cable_segment_id": "BHC-1"}

## 3. 케이블 구간·보호구역
- 구간 `BHC-1`, 보호버퍼 500m
- 라인: `[[14.73352, 55.18323], [14.67189, 55.19052]]`

## 4. 수중 이벤트 (파생 근거)
- 파생 원본: `{"source": "DMA_AIS", "mmsi": 219027963, "ais_row_index": 32874, "timestamp": "2026-06-03T07:14:59", "sog": 0.9, "cog": null, "cable_distance_m": 80.0}`
- 수식: `severity = w_p*exp(-d/d0) + w_s*exp(-(SOG-peak)^2/(2*sigma^2)) + w_k*kin + noise`
- 항 기여: `{"proximity": 0.9049, "speed_term": 0.8353, "kinematics": 0.0, "seeded_noise": -0.0094}`
- 파라미터: `{"w_proximity": 0.45, "w_speed": 0.35, "w_kinematics": 0.2, "d0_m": 800.0, "peak_knots": 1.5, "sigma_knots": 1.0, "noise_amplitude": 0.03, "seed": 20260610}`

## 5. AIS 항적·선박 후보
- 1순위 선박 MMSI: `219027963`
- 원본 AIS 발췌(이벤트 인근):

| timestamp | mmsi | lat | lon | SOG | COG | nav_status | cable_dist_m |
|---|---|---|---|---|---|---|---|
| 2026-06-03T07:14:59 | 219027963 | 55.18616 | 14.702547 | 0.9 | None | Unknown value | 80.0 |
| 2026-06-03T07:16:09 | 219027963 | 55.18616 | 14.702547 | 0.9 | None | Unknown value | 80.0 |
| 2026-06-03T07:17:05 | 219027963 | 55.18616 | 14.702547 | 0.9 | None | Unknown value | 80.0 |
| 2026-06-03T07:20:58 | 219027963 | 55.186118 | 14.702587 | 0.3 | None | Unknown value | 84.0 |
| 2026-06-03T07:22:09 | 219027963 | 55.186118 | 14.702587 | 0.3 | None | Unknown value | 84.0 |
| 2026-06-03T07:23:05 | 219027963 | 55.186118 | 14.702587 | 0.3 | None | Unknown value | 84.0 |

- 원인 후보 랭킹(기여 요인):
  - **permitted_maintenance**: 0.95
    - 허가 일치(MMSI+시간+구역): MNT-2026-0603-01 (기여 0.95)
  - **specific_vessel**: 0.5808
    - 활동성(횡단/표류/이동/급선회): 1.0 (기여 0.0)
    - 케이블 횡단: 1회 (기여 0.4)
    - 보호구역 체류: 846.0s (기여 0.1175)
    - 이동/표류(속도): mean 0.557kt var 0.1029 (기여 0.0763)
    - 케이블 근접: 80.0m (기여 0.552)
    - 이벤트 공간근접: 0.0m (기여 0.0)
    - 반복접근 이력: 4회 (기여 0.12)
  - **ais_dark**: 0.0
  - **legal_fishing**: 0.0
  - **natural_noise**: 0.0
    - 파고: 0.9m (기여 0.0)
    - 활동성 의심 선박 부재: 아니오(max_act 1.0) (기여 0.0)
  - **sensor_fault**: 0.0

## 6. METOC
- {"wave_height_m": 0.9, "current": "low"}

## 7. 허가 확인 결과
- 일치(정비로 간주)
  - {"permit_id": "MNT-2026-0603-01", "operator": "Baltic Cable Maintenance A/S", "work_type": "cable inspection / seabed survey", "mmsi": 219027963}

## 8. 위험도 기여도 분해

| 항목 | 기여 | 상한 |
|---|---|---|
| sensor_event_strength | 17.26 | 25 |
| cable_proximity | 17.98 | 20 |
| vessel_behavior | 10.76 | 20 |
| ais_gap | 0.0 | 10 |
| vessel_history | 5 | 5 |

- raw **51.0** / 80 → normalized **63.75**
- 디스카운트: 허가 -15, METOC -0.0, 센서 -0.0 (합 -15.0)
  - 허가 MNT-2026-0603-01 가 선박/시간/구역 일치 → 정비로 간주, -15 감점
- **risk = 48.75**

## 9. 판단 분기와 근거
- **분기: `suppress`**
- 1순위 후보: permitted_maintenance (2순위 specific_vessel, 격차 0.3692)
- 근거: 양성 후보 'permitted_maintenance'(점수 0.95) 1순위, risk 48.8 → 오탐 억제.
- 기대 분기 `suppress` 대비 **✓ 일치**
