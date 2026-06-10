# 결과 요약 (제안서 10장 삽입용)

> **검산 고지**: 본 문서는 실 AIS 항적에서 물리 함수로 파생한 합성 수중 이벤트를 사용한 **룰 기반 융합 판단 로직의 결정론적 검산**이다. 탐지율·오탐률 등 어떤 성능도 주장하지 않는다.

실 DMA 발트해 AIS(2026-06-03, 보른홀름 인근)에서 물리 파생한 합성 수중 이벤트로 5개 시나리오의 룰 기반 융합 판단 로직을 검산한 결과다.

## 지표 3 — 기대 분기 일치
| ID | 시나리오 | 기대 | 실제 | 분기일치 | 기대1순위 | 실제1순위 | 후보일치 | risk |
|---|---|---|---|---|---|---|---|---|
| S1 | 앵커 드래깅 고위험 | alert | alert | ✓ | specific_vessel | specific_vessel | ✓ | 63.75 |
| S2 | 허가 정비 오탐 억제 | suppress | suppress | ✓ | permitted_maintenance | permitted_maintenance | ✓ | 48.75 |
| S3 | 악천후 자연 노이즈 | suppress | suppress | ✓ | natural_noise | natural_noise | ✓ | 32.26 |
| S4 | AIS-dark 의심 | manual_review | manual_review | ✓ | ais_dark | ais_dark | ✓ | 55.95 |
| S5 | 센서 장애 | suppress | suppress | ✓ | sensor_fault | sensor_fault | ✓ | 40.14 |

**분기 일치 5/5, 1순위 후보 일치 5/5**

## 지표 1 — 단일출처(naive) 대비 융합 강등
naive = 수중 이벤트 severity 임계만으로 alert. 융합이 문맥 반영해 강등한 건수.
| ID | naive | 융합 | 강등 | 근거 |
|---|---|---|---|---|
| S1 | alert | alert | - | - |
| S2 | alert | suppress | 예 | 허가 정비 일치 |
| S3 | alert | suppress | 예 | 악천후 자연 노이즈 — 정박 선박 존재로 METOC 감점 부분 적용, 활동성 의심 거동 부재 |
| S4 | alert | manual_review | 예 | AIS-dark 능동 의심 → 수동 검토 escalation |
| S5 | alert | suppress | 예 | 전원저하 노드 반복 이상값 |

**융합 강등 4건** (naive 였다면 모두 alert 오탐). S1은 강등 없이 alert 유지(정탐 보존).

## 지표 2 — 증거 완성도 루브릭
| ID | 점수 |
|---|---|
| S1 | 12/12 |
| S2 | 12/12 |
| S3 | 10/12 |
| S4 | 12/12 |
| S5 | 10/12 |
(기준 정의·세부 채점은 `rubric.md` 참조)

## 지표 4 — 재현성
전체 파이프라인 2회 실행 산출물 **바이트 단위 동일**(고정 시드, 결정론적 정렬). `tests/test_determinism.py` 로 검증.

## 지표 5 — 증거 패키지 완성도(8.6)
5개 시나리오 모두 8.6 필수 필드 체크리스트 **통과**. `tests/test_schema.py`·`evidence.check_completeness` 로 검증.

## 이 검산이 증명하는 것 / 증명하지 않는 것
- **증명**: 동일 입력에 대해 룰 기반 융합 로직이 결정론적·추적가능하게 동작하며, 단일출처 대비 문맥(허가·METOC·센서·AIS끊김)을 반영해 분기를 차별화함.
- **비증명**: 실제 위협 탐지율·오탐률·운영 성능. 본 산출물은 합성 파생 데이터 기반 로직 검산이며 성능 주장이 아님.
