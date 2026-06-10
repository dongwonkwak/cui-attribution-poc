# 증거 패키지 — S3 악천후 자연 노이즈

> 합성 파생 데이터 기반 판단 로직 검산. 탐지 성능 주장 아님.

## 1. 이벤트 요약
- 인시던트 이벤트: `MX-20260603T080-05` (underwater_sensor/acoustic)
- severity **0.4**, confidence **0.25**

## 2. 시각·위치
- 시각: `2026-06-03T08:00:00`
- 위치: {"lat": 55.184803, "lon": 14.671917, "cable_segment_id": "BHC-1"}

## 3. 케이블 구간·보호구역
- 구간 `BHC-1`, 보호버퍼 500m
- 라인: `[[14.73352, 55.18323], [14.67189, 55.19052]]`

## 4. 수중 이벤트 (파생 근거)
- 파생 원본: `{"source": "METOC", "metoc_window": "2026-06-03T08:00:00", "wave_height_m": 3.2, "current": "high"}`
- 수식: `metoc 고파고 구간 → 광역 저신뢰 이벤트(룰)`
- 파라미터: `{"severity": 0.4, "confidence": 0.25, "count_per_window": 6}`

## 5. AIS 항적·선박 후보
- 1순위 선박 MMSI: `219021300`

- 원인 후보 랭킹(기여 요인):
  - **natural_noise**: 0.7107
    - 파고: 3.2m (기여 0.4107)
    - 활동성 의심 선박 부재: 예(max_act 0.121) (기여 0.3)
  - **sensor_fault**: 0.3
    - 최근접 노드 전원저하: SN-BHC-1-B (기여 0.3)
  - **specific_vessel**: 0.0702
    - 활동성(횡단/표류/이동/급선회): 0.0 (기여 0.0)
    - 케이블 횡단: 0회 (기여 0.0)
    - 보호구역 체류: 1726.0s (기여 0.2397)
    - 이동/표류(속도): mean 0.0kt var 0.0 (기여 0.0)
    - 케이블 근접: 225.3m (기여 0.465)
    - 이벤트 공간근접: 1935.7m (기여 0.0)
  - **ais_dark**: 0.0
  - **legal_fishing**: 0.0
  - **permitted_maintenance**: 0.0

## 6. METOC
- {"wave_height_m": 3.2, "current": "high"}

## 7. 허가 확인 결과
- 해당 허가 없음

## 8. 위험도 기여도 분해

| 항목 | 기여 | 상한 |
|---|---|---|
| sensor_event_strength | 10.0 | 25 |
| cable_proximity | 14.81 | 20 |
| vessel_behavior | 7.67 | 20 |
| ais_gap | 0.0 | 10 |
| vessel_history | 0.0 | 5 |

- raw **32.48** / 80 → normalized **40.6**
- 디스카운트: 허가 -0.0, METOC -2.34, 센서 -6.0 (합 -8.34)
  - 파고 3.2m(≥2.5) 악천후·선박 행동 존재로 부분 적용 → -2.34 감점
  - 최근접 노드 SN-BHC-1-B 전원저하 → -6.0 감점
- **risk = 32.26**

## 9. 판단 분기와 근거
- **분기: `suppress`**
- 1순위 후보: natural_noise (2순위 sensor_fault, 격차 0.4107)
- 근거: 양성 후보 'natural_noise'(점수 0.71) 1순위, risk 32.3 → 오탐 억제.
- 기대 분기 `suppress` 대비 **✓ 일치**
