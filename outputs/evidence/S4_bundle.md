# 증거 패키지 — S4 AIS-dark 의심

> 합성 파생 데이터 기반 판단 로직 검산. 탐지 성능 주장 아님.

## 1. 이벤트 요약
- 인시던트 이벤트: `UW-219031421-0076` (underwater_sensor/acoustic)
- severity **0.671**, confidence **0.9289**

## 2. 시각·위치
- 시각: `2026-06-03T07:55:06`
- 위치: {"lat": 55.1866, "lon": 14.703932, "cable_segment_id": "BHC-1"}

## 3. 케이블 구간·보호구역
- 구간 `BHC-1`, 보호버퍼 500m
- 라인: `[[14.73352, 55.18323], [14.67189, 55.19052]]`

## 4. 수중 이벤트 (파생 근거)
- 파생 원본: `{"source": "DMA_AIS", "mmsi": 219031421, "ais_row_index": 40333, "timestamp": "2026-06-03T07:55:06", "sog": 0.0, "cog": null, "cable_distance_m": 14.2}`
- 수식: `severity = w_p*exp(-d/d0) + w_s*exp(-(SOG-peak)^2/(2*sigma^2)) + w_k*kin + noise`
- 항 기여: `{"proximity": 0.9825, "speed_term": 0.3247, "kinematics": 0.0, "seeded_noise": 0.1153}`
- 파라미터: `{"w_proximity": 0.45, "w_speed": 0.35, "w_kinematics": 0.2, "d0_m": 800.0, "peak_knots": 1.5, "sigma_knots": 1.0, "noise_amplitude": 0.03, "seed": 20260610}`

## 5. AIS 항적·선박 후보
- 1순위 선박 MMSI: `219031421`
- 원본 AIS 발췌(이벤트 인근):

| timestamp | mmsi | lat | lon | SOG | COG | nav_status | cable_dist_m |
|---|---|---|---|---|---|---|---|
| 2026-06-03T07:42:10 | 219031421 | 55.186597 | 14.703887 | 0.0 | None | Unknown value | 15.1 |
| 2026-06-03T07:52:08 | 219031421 | 55.186595 | 14.703938 | 0.0 | None | Unknown value | 14.6 |
| 2026-06-03T07:54:19 | 219031421 | 55.186595 | 14.703938 | 0.0 | None | Unknown value | 14.6 |
| 2026-06-03T07:55:06 | 219031421 | 55.1866 | 14.703932 | 0.0 | None | Unknown value | 14.2 |
| 2026-06-03T08:06:22 | 219031421 | 55.1866 | 14.703932 | 0.0 | None | Unknown value | 14.2 |
| 2026-06-03T08:06:25 | 219031421 | 55.1866 | 14.703932 | 0.0 | None | Unknown value | 14.2 |

- 원인 후보 랭킹(기여 요인):
  - **ais_dark**: 0.5073
    - AIS 끊김 길이: 11.3min (기여 0.113)
    - 끊김 전 케이블 근접: 14.2m (기여 0.3943)
  - **natural_noise**: 0.3
    - 파고: 0.9m (기여 0.0)
    - 활동성 의심 선박 부재: 예(max_act 0.124) (기여 0.3)
  - **specific_vessel**: 0.0754
    - 활동성(횡단/표류/이동/급선회): 0.113 (기여 0.0)
    - 케이블 횡단: 0회 (기여 0.0)
    - 보호구역 체류: 1459.0s (기여 0.2026)
    - 이동/표류(속도): mean 0.0kt var 0.0 (기여 0.0)
    - 케이블 근접: 14.2m (기여 0.591)
    - 이벤트 공간근접: 0.0m (기여 0.0)
  - **legal_fishing**: 0.0
  - **permitted_maintenance**: 0.0
  - **sensor_fault**: 0.0

## 6. METOC
- {"wave_height_m": 0.9, "current": "low"}

## 7. 허가 확인 결과
- 해당 허가 없음

## 8. 위험도 기여도 분해

| 항목 | 기여 | 상한 |
|---|---|---|
| sensor_event_strength | 16.78 | 25 |
| cable_proximity | 19.62 | 20 |
| vessel_behavior | 6.48 | 20 |
| ais_gap | 1.88 | 10 |
| vessel_history | 0.0 | 5 |

- raw **44.76** / 80 → normalized **55.95**
- 디스카운트: 허가 -0.0, METOC -0.0, 센서 -0.0 (합 -0.0)
- **risk = 55.95**

## 9. 판단 분기와 근거
- **분기: `manual_review`**
- 1순위 후보: ais_dark (2순위 natural_noise, 격차 0.2073)
- 근거: 위협 후보 'ais_dark' 1순위이나 risk 56.0 가 회색지대(35.0~60.0) → 수동 검토.
- 기대 분기 `manual_review` 대비 **✓ 일치**
