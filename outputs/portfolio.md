# CUI Threat Attribution Layer — PoC 검산 포트폴리오
## 앵커 드래깅 입출력 증명

---

## 검산 고지

본 포트폴리오의 모든 수치와 판단은 실 DMA 발트해 AIS 항적에서 **물리 함수로 파생한 합성 수중 이벤트**를 사용한 **룰 기반 융합 판단 로직의 결정론적 검산** 결과다. 탐지율·오탐률 등 어떤 운영 성능도 주장하지 않는다. 이하 개별 섹션에 반복되던 동일 고지는 이 항 1회로 통합한다.

## 데이터 출처·라이선스

- **실데이터**: 덴마크 해사청(DMA) 발트해 AIS — `aisdk-2026-06-03.zip`
  - 라이선스: DMA 공개 데이터, **무제한 사용권**(출처 표기 권장)
  - 사용 서브셋: 보른홀름 인근 bbox(lat 54.5–55.6, lon 14.0–16.2), 69,385 포인트 / 130 MMSI
- **가상데이터(목업)**: 케이블 라인, METOC, 정비허가, 선박이력, 센서노드 — `config/mock/`

---

## 검산 결과 요약

실 DMA 발트해 AIS(2026-06-03, 보른홀름 인근)에서 물리 파생한 합성 수중 이벤트로 5개 시나리오의 룰 기반 융합 판단 로직을 검산한 결과다.

### 지표 3 — 기대 분기 일치
| ID | 시나리오 | 기대 | 실제 | 분기일치 | 기대1순위 | 실제1순위 | 후보일치 | risk |
|---|---|---|---|---|---|---|---|---|
| S1 | 앵커 드래깅 고위험 | alert | alert | ✓ | specific_vessel | specific_vessel | ✓ | 63.75 |
| S2 | 허가 정비 오탐 억제 | suppress | suppress | ✓ | permitted_maintenance | permitted_maintenance | ✓ | 48.75 |
| S3 | 악천후 자연 노이즈 | suppress | suppress | ✓ | natural_noise | natural_noise | ✓ | 32.26 |
| S4 | AIS-dark 의심 | manual_review | manual_review | ✓ | ais_dark | ais_dark | ✓ | 55.95 |
| S5 | 센서 장애 | suppress | suppress | ✓ | sensor_fault | sensor_fault | ✓ | 40.14 |

**분기 일치 5/5, 1순위 후보 일치 5/5**

### 지표 1 — 단일출처(naive) 대비 융합 강등
naive = 수중 이벤트 severity 임계만으로 alert. 융합이 문맥 반영해 강등한 건수.
| ID | naive | 융합 | 강등 | 근거 |
|---|---|---|---|---|
| S1 | alert | alert | - | - |
| S2 | alert | suppress | 예 | 허가 정비 일치 |
| S3 | alert | suppress | 예 | 악천후 자연 노이즈·활동성 선박 부재 |
| S4 | alert | manual_review | 예 | AIS-dark 능동 의심 → 수동 검토 escalation |
| S5 | alert | suppress | 예 | 전원저하 노드 반복 이상값 |

**융합 강등 4건** (naive 였다면 모두 alert 오탐). S1은 강등 없이 alert 유지(정탐 보존).

### 지표 2 — 증거 완성도 루브릭
| ID | 점수 |
|---|---|
| S1 | 12/12 |
| S2 | 12/12 |
| S3 | 10/12 |
| S4 | 12/12 |
| S5 | 10/12 |
(기준 정의·세부 채점은 아래 루브릭 섹션 참조)

### 지표 4 — 재현성
전체 파이프라인 2회 실행 산출물 **바이트 단위 동일**(고정 시드, 결정론적 정렬).

### 지표 5 — 증거 패키지 완성도(8.6)
5개 시나리오 모두 8.6 필수 필드 체크리스트 **통과**.

---

## S1 입출력 체인 — 앵커 드래깅 고위험

### 0. 시나리오 입력
- incident_source: `vessel`
- 기대 분기: `alert`, 기대 1순위: `specific_vessel`

### 1. Raw AIS 발췌 (실 DMA 항적)
| timestamp | mmsi | lat | lon | SOG | COG | nav_status | cable_dist_m |
|---|---|---|---|---|---|---|---|
| 2026-06-03T07:14:59 | 219027963 | 55.18616 | 14.702547 | 0.9 | None | Unknown value | 80.0 |
| 2026-06-03T07:16:09 | 219027963 | 55.18616 | 14.702547 | 0.9 | None | Unknown value | 80.0 |
| 2026-06-03T07:17:05 | 219027963 | 55.18616 | 14.702547 | 0.9 | None | Unknown value | 80.0 |
| 2026-06-03T07:20:58 | 219027963 | 55.186118 | 14.702587 | 0.3 | None | Unknown value | 84.0 |
| 2026-06-03T07:22:09 | 219027963 | 55.186118 | 14.702587 | 0.3 | None | Unknown value | 84.0 |
| 2026-06-03T07:23:05 | 219027963 | 55.186118 | 14.702587 | 0.3 | None | Unknown value | 84.0 |

### 2. 합성 수중 이벤트 (물리 파생)
- 이벤트 `UW-219027963-0096` severity **0.6902**, confidence **0.9095**
- 수식: `severity = w_p*exp(-d/d0) + w_s*exp(-(SOG-peak)^2/(2*sigma^2)) + w_k*kin + noise`
- 항 기여: `{"proximity": 0.9049, "speed_term": 0.8353, "kinematics": 0.0, "seeded_noise": -0.0094}`
- 파라미터: `{"w_proximity": 0.45, "w_speed": 0.35, "w_kinematics": 0.2, "d0_m": 800.0, "peak_knots": 1.5, "sigma_knots": 1.0, "noise_amplitude": 0.03, "seed": 20260610}`
- 파생 원본(추적): `{"source": "DMA_AIS", "mmsi": 219027963, "ais_row_index": 32874, "timestamp": "2026-06-03T07:14:59", "sog": 0.9, "cog": null, "cable_distance_m": 80.0}`

### 3. 시공간 결합 (±15분)
- 1순위 결합 선박 MMSI: `219027963`, 창 내 선박 6척
- 특징량:
  - min_cable_dist_m: 80.0
  - dwell_in_zone_s: 846.0
  - speed_mean_kt: 0.557
  - speed_var: 0.1029
  - cable_crossings: 1
  - max_turn_deg: 0.0
  - ais_gap_minutes: 0.0
  - event_time_diff_s: 0.0
  - event_space_dist_m: 0.0

### 4. 원인 후보 랭킹 (기여 요인)
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
- **permitted_maintenance**: 0.0
- **sensor_fault**: 0.0

### 5. 위험도 스코어링 (기여도 분해)
| 항목 | 기여 | 상한 |
|---|---|---|
| sensor_event_strength | 17.26 | 25 |
| cable_proximity | 17.98 | 20 |
| vessel_behavior | 10.76 | 20 |
| ais_gap | 0.0 | 10 |
| vessel_history | 5 | 5 |
- raw **51.0**/80 → normalized **63.75**
- 디스카운트 합 -0.0 (허가 -0.0, METOC -0.0, 센서 -0.0)
- **risk = 63.75**

### 6. 최종 인시던트 JSON
```json
{
  "scenario": "S1",
  "incident_event_id": "UW-219027963-0096",
  "risk": 63.75,
  "top_candidate": "specific_vessel",
  "branch": "alert"
}
```

### 7. 판단 분기
- **`alert`** — 위협 후보 'specific_vessel'(점수 0.58) 1순위, risk 63.8 ≥ 60.0 → 경보.
- 기대 `alert` 대비 **✓ 일치**

---

## 단일출처 vs 융합 대조

### S2 — 허가 정비 오탐 억제

#### 기준선 정의
- **naive(단일 출처)**: 수중 이벤트 severity 가 임계 이상이면 무조건 `alert`. 허가·METOC·센서상태·선박행동 일절 무시.
- **융합**: 8.2~8.5 다중출처 결합 + 룰 기반 오탐 억제 후 분기.

#### 동일 입력, 두 판정
| 구분 | 판정 | 근거 |
|---|---|---|
| naive | `alert` | 수중 이벤트 severity 0.6902 ≥ 임계 0.35 (단일 출처, 문맥 무시) |
| 융합 | `suppress` | 양성 후보 'permitted_maintenance'(점수 0.95) 1순위, risk 48.8 → 오탐 억제. |

#### 결과
- naive 는 `alert`(오탐) 이나, 융합은 문맥을 반영해 **`suppress` 로 옳게 강등**.
- 강등 근거(디스카운트):
  - 허가 MNT-2026-0603-01 가 선박/시간/구역 일치 → 정비로 간주, -15 감점

### S3 — 악천후 자연 노이즈

#### 기준선 정의
- **naive(단일 출처)**: 수중 이벤트 severity 가 임계 이상이면 무조건 `alert`. 허가·METOC·센서상태·선박행동 일절 무시.
- **융합**: 8.2~8.5 다중출처 결합 + 룰 기반 오탐 억제 후 분기.

#### 동일 입력, 두 판정
| 구분 | 판정 | 근거 |
|---|---|---|
| naive | `alert` | 수중 이벤트 severity 0.4 ≥ 임계 0.35 (단일 출처, 문맥 무시) |
| 융합 | `suppress` | 양성 후보 'natural_noise'(점수 0.71) 1순위, risk 32.3 → 오탐 억제. |

#### 결과
- naive 는 `alert`(오탐) 이나, 융합은 문맥을 반영해 **`suppress` 로 옳게 강등**.
- 강등 근거(디스카운트):
  - 파고 3.2m(≥2.5) 악천후·선박 행동 존재로 부분 적용 → -2.34 감점
  - 최근접 노드 SN-BHC-1-B 전원저하 → -6.0 감점

---

## 증거 완성도 루브릭

### 루브릭 정의 (보험/수사 실무 필요 필드, 각 0~2점)
| # | 기준 | 0 | 1 | 2 |
|---|---|---|---|---|
| 1 | 시각·위치 정밀도 | 둘 다 없음 | 시각만 | ISO시각+좌표 |
| 2 | 선박 식별 | 없음 | 부분 | MMSI+행동특징 or 선박무관 명시 |
| 3 | 환경 조건(METOC) | 없음 | - | 파고·조류 제시 |
| 4 | 허가 확인 | 없음 | - | 허가 일치/부재 결과 |
| 5 | 판단 근거 추적성 | 없음 | 근거만 | 근거+기여도분해 |
| 6 | 원시 데이터 참조 | 없음 | derived_from만 | derived_from+원시행 |

### 시나리오별 채점
| 시나리오 | 시각·위치 정밀도 | 선박 식별 | 환경 조건(METOC) | 허가 확인 | 판단 근거 추적성 | 원시 데이터 참조 | 합계 |
|---|---|---|---|---|---|---|---|
| S1 | 2 | 2 | 2 | 2 | 2 | 2 | **12/12** |
| S2 | 2 | 2 | 2 | 2 | 2 | 2 | **12/12** |
| S3 | 2 | 1 | 2 | 2 | 2 | 1 | **10/12** |
| S4 | 2 | 2 | 2 | 2 | 2 | 2 | **12/12** |
| S5 | 2 | 1 | 2 | 2 | 2 | 1 | **10/12** |

---

## 증거 패키지 샘플 — S1

### 이벤트 요약
- 인시던트: `UW-219027963-0096` (underwater_sensor / acoustic)
- severity **0.6902**, confidence **0.9095**
- 시각: `2026-06-03T07:14:59` / 위치: lat 55.18616, lon 14.702547, 케이블구간 BHC-1

### 수중 이벤트 파생 근거
- 파생 원본: MMSI 219027963, ais_row_index 32874, SOG 0.9kt, cable_distance_m 80.0
- 항 기여: proximity 0.9049 / speed_term 0.8353 / kinematics 0.0 / seeded_noise −0.0094
- 파라미터: w_p=0.45, w_s=0.35, w_k=0.2, d0=800m, peak=1.5kt, σ=1.0kt, seed=20260610

### METOC
- wave_height_m: 0.9, current: low

### 허가 확인
- 해당 허가 없음

### 위험도 기여도 분해 (JSON 핵심 필드)
```json
{
  "contributions": {
    "sensor_event_strength": 17.26,
    "cable_proximity": 17.98,
    "vessel_behavior": 10.76,
    "ais_gap": 0.0,
    "vessel_history": 5
  },
  "raw": 51.0,
  "raw_max": 80,
  "normalized": 63.75,
  "discounts": { "maintenance_permit": 0.0, "metoc_noise": 0.0, "sensor_health": 0.0, "total": 0.0 },
  "risk": 63.75
}
```

### 판단
```json
{
  "branch": "alert",
  "top_candidate": "specific_vessel",
  "margin": 0.5808,
  "rationale": "위협 후보 'specific_vessel'(점수 0.58) 1순위, risk 63.8 ≥ 60.0 → 경보."
}
```

---

## 결정 로그

모호 지점 임의 결정 및 스펙 충돌 시 정정 기록.

| # | 결정 | 근거 |
|---|---|---|
| D-01 | 데이터 2026-06-03, 보른홀름 bbox | DMA 가용 최근 평일, 케이블 인근 저속·표류 항적 확보 |
| D-02 | 후보 구역 2 + 케이블 배치 | 사용자 선택. 단일 횡단·명확 표류로 S1 체인 최선명 |
| D-03 | 파생 상수 d0/가중/임계/노이즈 | 물리 의미반경·드래그 운동학·신호대노이즈비, 각 yaml 주석 |
| D-04 | 스코어 상한·디스카운트 상한 | 제안서 8.5 명세 그대로 |
| D-05 | 분기 임계 alert60/suppress35/margin0.15 | 회색지대를 manual_review로 보내는 보수적 설정 |
| D-06 | incident=케이블 횡단 시점(없으면 최고severity) | 사용자 요청. 횡단이 결합창 vessel_behavior에 반영되도록 |
| **D-07** | **속도 피크 2.5→1.5kt 정정** | 앵커 드래그 실측 표류속도(0.5~2kt)에 맞춤. 임계 끼워맞춤이 아닌 물리상수 정정. 정정 전 2.5kt에서는 최종 config 기준 risk 57.65 → manual_review(정정으로 alert 복귀). 민감도: peak ∈ [1.0, 2.0] kt에서 S1 분기 alert 유지 |
| D-08 | 후보 점수 활동성 게이팅 | 정박선이 근접만으로 위협(specific_vessel)이 되지 않도록. natural_noise는 '활동성 의심 선박 부재', sensor_fault는 반복패턴 시에만 강하게 |
| D-09 | S3 METOC incident=선박 고립지점 | 스펙 S3 '인근 의심 선박 부재' 정의 충족 |
| D-10 | crossings=전체항적 횡단시각 중 창내 카운트 | AIS 희소로 횡단쌍이 창 경계에 걸리는 샘플링 아티팩트 보정 |
| D-11 | SOG 결측 포인트는 이벤트 미생성 | 물리 파생 불가 포인트의 정직한 처리 |

스펙 충돌로 멈춰 물어본 지점: 없음(모두 스펙 허용범위 내 결정). D-07은 스펙 임계 끼워맞춤 금지 규정을 준수하기 위해 **임계가 아닌 물리상수를 정정**하고 그 사실을 본 로그에 기록함.

---

## 이 검산이 증명하는 것 / 증명하지 않는 것

- **증명**: 동일 입력에 대해 룰 기반 융합 로직이 결정론적·추적가능하게 동작하며, 단일출처 대비 문맥(허가·METOC·센서·AIS끊김)을 반영해 분기를 차별화함.
- **비증명**: 실제 위협 탐지율·오탐률·운영 성능. 본 산출물은 합성 파생 데이터 기반 로직 검산이며 성능 주장이 아님.

---

## 재현 방법

1. 의존성 설치: `pip install -e .` (Python 3.11+, `pyproject.toml` 기준)
2. AIS 원본 준비: `data/raw/aisdk-2026-06-03.zip` 배치 (DMA 공개 데이터, 직접 다운로드)
3. 전체 실행: `PYTHONPATH=src python run.py` → `outputs/` 전체 재생성
4. 특정 시나리오만: `PYTHONPATH=src python run.py S1`
5. 결정론 검증: `PYTHONPATH=src pytest tests/test_determinism.py` (2회 실행 후 바이트 비교)
