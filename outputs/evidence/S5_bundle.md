# 증거 패키지 — S5 센서 장애

> 합성 파생 데이터 기반 판단 로직 검산. 탐지 성능 주장 아님.

## 1. 이벤트 요약
- 인시던트 이벤트: `SF-SN-BHC-1-B-00` (underwater_sensor/vibration)
- severity **0.55**, confidence **0.3**

## 2. 시각·위치
- 시각: `2026-06-03T02:00:00`
- 위치: {"lat": 55.1895, "lon": 14.68, "cable_segment_id": "BHC-1"}

## 3. 케이블 구간·보호구역
- 구간 `BHC-1`, 보호버퍼 500m
- 라인: `[[14.73352, 55.18323], [14.67189, 55.19052]]`

## 4. 수중 이벤트 (파생 근거)
- 파생 원본: `{"source": "sensor_node", "node_id": "SN-BHC-1-B", "power_status": "degraded", "comm_status": "intermittent"}`
- 수식: `전원 저하 노드 반복 이상값(룰)`
- 파라미터: `{"severity": 0.55, "confidence": 0.3}`

## 5. AIS 항적·선박 후보
- 1순위 선박 MMSI: `219978000`

- 원인 후보 랭킹(기여 요인):
  - **sensor_fault**: 0.8
    - 최근접 노드 전원저하: SN-BHC-1-B (기여 0.3)
    - 규칙적 반복 이상값: 예 (기여 0.5)
  - **natural_noise**: 0.3
    - 파고: 0.7m (기여 0.0)
    - 활동성 의심 선박 부재: 예(max_act 0.092) (기여 0.3)
  - **specific_vessel**: 0.0699
    - 활동성(횡단/표류/이동/급선회): 0.0 (기여 0.0)
    - 케이블 횡단: 0회 (기여 0.0)
    - 보호구역 체류: 1588.0s (기여 0.2206)
    - 이동/표류(속도): mean 0.0kt var 0.0 (기여 0.0)
    - 케이블 근접: 26.6m (기여 0.584)
    - 이벤트 공간근접: 1457.6m (기여 0.0)
  - **ais_dark**: 0.0
  - **legal_fishing**: 0.0
  - **permitted_maintenance**: 0.0

## 6. METOC
- {"wave_height_m": 0.7, "current": "low"}

## 7. 허가 확인 결과
- 해당 허가 없음

## 8. 위험도 기여도 분해

| 항목 | 기여 | 상한 |
|---|---|---|
| sensor_event_strength | 13.75 | 25 |
| cable_proximity | 19.3 | 20 |
| vessel_behavior | 7.06 | 20 |
| ais_gap | 0.0 | 10 |
| vessel_history | 0.0 | 5 |

- raw **40.11** / 80 → normalized **50.14**
- 디스카운트: 허가 -0.0, METOC -0.0, 센서 -10 (합 -10.0)
  - 최근접 노드 SN-BHC-1-B 전원저하·규칙적 반복 이상값 → -10 감점
- **risk = 40.14**

## 9. 판단 분기와 근거
- **분기: `suppress`**
- 1순위 후보: sensor_fault (2순위 natural_noise, 격차 0.5)
- 근거: 양성 후보 'sensor_fault'(점수 0.80) 1순위, risk 40.1 → 오탐 억제.
- 기대 분기 `suppress` 대비 **✓ 일치**
