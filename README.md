# CUI Threat Attribution Layer — 결정론적 PoC 검산 파이프라인

해저 케이블 위협 판단 레이어(CUI Threat Attribution Layer)의 **룰 기반 다중출처 융합
판단 로직**을, 실 발트해 AIS 항적에서 물리 파생한 합성 수중 이벤트로 **결정론적으로
검산**한다. 목적은 탐지 성능 측정이 아니라 판단 로직의 동작 검증이다.

> **이 검산이 증명하는 것 / 증명하지 않는 것**
> - **증명**: 동일 입력에 대해 융합 로직이 결정론적·추적가능하게 동작하고, 단일출처
>   대비 문맥(허가·METOC·센서상태·AIS끊김)을 반영해 `alert/suppress/manual_review`
>   분기를 차별화함. 모든 점수는 항목별 기여도로 분해된다.
> - **비증명**: 실제 위협 **탐지율·오탐률·운영 성능**. 합성 파생 데이터 기반 로직
>   검산이며 어떤 성능도 주장하지 않는다.

## 데이터 출처·라이선스

- **실데이터**: 덴마크 해사청(DMA) 발트해 AIS, 일 단위 CSV.
  - 호스트: `http://aisdata.ais.dk/` (S3 버킷 `aisdata.ais.dk.s3.eu-central-1.amazonaws.com`)
  - 사용 파일: `aisdk-2026-06-03.zip` (661MB zip → 3.64GB CSV)
  - 라이선스: **DMA 공개 데이터, 무제한 사용권**(출처 표기 권장). 본 PoC는 출처를 명기한다.
  - 사용 컬럼: Timestamp(`DD/MM/YYYY HH:MM:SS`), MMSI, Latitude, Longitude, SOG, COG,
    Navigational status, Type of mobile. 결측·중복·비물리적 점프(>60kt) 정제 포함.
  - 서브셋: 보른홀름 인근 bbox(lat 54.5–55.6, lon 14.0–16.2) → 69,385 포인트 / 130 MMSI.
    3.64GB CSV를 zip 멤버 스트리밍하며 bbox 필터링(전체 압축 해제 없음).
- **가상데이터(목업)**: `config/mock/` — 케이블 라인, METOC, 정비허가, 선박이력, 센서노드.
  각 설정의 근거는 해당 yaml 주석에 1줄씩 기재.

## 선택 구역 / 시나리오 배역 (실 항적 기반)

- 가상 케이블 `BHC-1`: `[[14.73352,55.18323],[14.67189,55.19052]]`, 보호버퍼 500m
  (보른홀름 북서 정박지, region_finder가 1순위 표류 선박의 표류 방위에 수직 배치).
- **S1/S2 주인공**: MMSI **219027963** — 케이블 73~200m 이내 저속 표류, 07:14:59 세그먼트 1회 횡단.
- **S4 AIS-dark**: MMSI **219031421** — 케이블 최단 10.3m, 약 231분 AIS 송신 중단.
- 대조군: 정박 선박 다수(S3 결합 문맥, S5 무관 입증).

## 파생 수식과 상수 근거 (`config/derivation.yaml`)

합성 수중 이벤트는 **실 AIS 항적 포인트에서만** 파생한다(임의 주입 금지). 각 레코드에
`derived_from`(원본 행 참조)·`derivation`(수식+파라미터)을 기록한다.

```
severity(t) = w_p·proximity + w_s·speed + w_k·kinematics + seeded_noise
  proximity  = exp(-d / d0)                         d0=800m  (교란 의미반경)
  speed      = exp(-(SOG-peak)^2 / (2·sigma^2))     peak=1.5kt, sigma=1.0kt (앵커드래그 저속대)
  kinematics = 0.6·min(|ΔCOG|/90,1) + 0.4·min(max(0,-ΔSOG)/3,1)   (드래그 개시 시그니처)
  seeded_noise ~ N(0, 0.03)  (sha256(seed,행키) 결정론적)
  w_p,w_s,w_k = 0.45, 0.35, 0.20    event_threshold = 0.35
```
- S3(악천후): 선박 무관, METOC 고파고(≥2.5m) 구간의 광역 저신뢰 이벤트(룰).
- S5(센서장애): 전원 저하 노드의 규칙적 반복 이상값(02:00부터 7분 간격 5회, 룰).

위험도(8.5): `raw = 이벤트강도(≤25)+근접(≤20)+선박행동(≤20)+AIS끊김(≤10)+이력(≤5)`,
`risk = clamp(raw/80·100 − 허가(≤15) − METOC(≤10) − 센서(≤10), 0,100)`. 분기 임계는
`config/pipeline.yaml`(alert≥60, suppress<35, 후보격차<0.15+계열상충→manual_review).

## 실행 방법 / 재현 절차

```bash
uv venv --python 3.11 && uv pip install pandas numpy shapely pyyaml requests pytest

# (선택) 후보 구역 재탐색: 실 데이터 다운로드+서브셋+탐색
PYTHONPATH=src .venv/bin/python -m cui.region_finder

# 전체 시나리오 실행 → outputs/ 생성 (최초 실행 시 DMA 일 파일 자동 다운로드)
PYTHONPATH=src .venv/bin/python run.py
PYTHONPATH=src .venv/bin/python run.py S1     # 특정 시나리오만

# 테스트: 결정론(2회 바이트 동일)/스코어 산식/스키마·완성도
.venv/bin/python -m pytest -q
```

재현성: 고정 시드(`seed: 20260610`) + 결정론적 정렬. **2회 실행 산출물 바이트 동일**.

## 산출물 (`outputs/`)

- `chains/S1.md … S5.md` — 입출력 체인(Raw AIS→파생 수중 이벤트→결합→후보 랭킹→위험도
  분해→인시던트 JSON→분기)
- `contrast/S2_contrast.md`, `S3_contrast.md` — naive(단일출처) vs 융합 대조
- `evidence/S*_bundle.json` + `.md` — 8.6 증거 패키지(필수 필드 체크리스트 통과)
- `rubric.md` — 증거 완성도 루브릭(정의+채점), `results_summary.md` — 결과 요약(지표 5종)

## 결과 (5개 시나리오)

| ID | 시나리오 | 기대 분기 | 실제 | 1순위 후보 | risk |
|---|---|---|---|---|---|
| S1 | 앵커 드래깅 고위험 | alert | alert | specific_vessel | 63.75 |
| S2 | 허가 정비 오탐 억제 | suppress | suppress | permitted_maintenance | 48.75 |
| S3 | 악천후 자연 노이즈 | suppress | suppress | natural_noise | 32.26 |
| S4 | AIS-dark 의심 | manual_review¹ | manual_review | ais_dark | 55.95 |
| S5 | 센서 장애 | suppress² | suppress | sensor_fault | 40.14 |

분기 일치 **5/5**, 1순위 후보 일치 **5/5**, 융합 강등 **4건**(naive였다면 모두 alert 오탐).
¹ 스펙 허용집합 {alert, manual_review}. ² 스펙 허용집합 {suppress, manual_review}.

## 결정 로그 (모호 지점 임의 결정 + 스펙 충돌 시 정정 기록)

| # | 결정 | 근거 |
|---|---|---|
| D-01 | 데이터 2026-06-03, 보른홀름 bbox | DMA 가용 최근 평일, 케이블 인근 저속·표류 항적 확보 |
| D-02 | 후보 구역 2 + 케이블 배치 | 사용자 선택. 단일 횡단·명확 표류로 S1 체인 최선명 |
| D-03 | 파생 상수 d0/가중/임계/노이즈 | 물리 의미반경·드래그 운동학·신호대노이즈비, 각 yaml 주석 |
| D-04 | 스코어 상한·디스카운트 상한 | 제안서 8.5 명세 그대로 |
| D-05 | 분기 임계 alert60/suppress35/margin0.15 | 회색지대를 manual_review로 보내는 보수적 설정 |
| D-06 | incident=케이블 횡단 시점(없으면 최고severity) | 사용자 요청. 횡단이 결합창 vessel_behavior에 반영되도록 |
| **D-07** | **속도 피크 2.5→1.5kt 정정** | 앵커 드래그 실측 표류속도(0.5~2kt)에 맞춤. 임계 끼워맞춤이 아닌 물리상수 정정 |
| D-08 | 후보 점수 활동성 게이팅 | 정박선이 근접만으로 위협(specific_vessel)이 되지 않도록. natural_noise는 '활동성 의심 선박 부재', sensor_fault는 반복패턴 시에만 강하게 |
| D-09 | S3 METOC incident=선박 고립지점 | 스펙 S3 '인근 의심 선박 부재' 정의 충족 |
| D-10 | crossings=전체항적 횡단시각 중 창내 카운트 | AIS 희소로 횡단쌍이 창 경계에 걸리는 샘플링 아티팩트 보정 |
| D-11 | SOG 결측 포인트는 이벤트 미생성 | 물리 파생 불가 포인트의 정직한 처리 |

스펙 충돌로 멈춰 물어본 지점: 없음(모두 스펙 허용범위 내 결정). D-07은 스펙 임계 끼워맞춤
금지 규정을 준수하기 위해 **임계가 아닌 물리상수를 정정**하고 그 사실을 본 로그에 기록함.
