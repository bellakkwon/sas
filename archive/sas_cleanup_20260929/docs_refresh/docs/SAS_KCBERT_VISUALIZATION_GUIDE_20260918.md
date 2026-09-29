> **2026-09-29 안내:** 아래는 이전 실행 이력입니다. 현재 실행 파일은 [00_RUN_ALL.sas](../sas/00_RUN_ALL.sas) 하나이며 [RUNBOOK](../sas/RUNBOOK.md)을 따릅니다. 옛 실행기는 `archive/sas_cleanup_20260929/`에 보존했습니다.

# ScamLens: KcBERT SAS 시각화 명세서 및 가이드라인 (2026-09-18)

> 최신 발표용 Studio·VA 작업은 [2026-09-21 실행 안내](../visualization_20260921_v1/SAS_FINAL_VISUALIZATION_20260921.md)를 따릅니다. 아래 내용은 이전 판의 기록이며, 공개본에 없는 행별 입력을 요구할 수 있습니다.

본 문서는 GitHub 연동 저장소(`kimchikingdom/sas`) 내에서 **ScamLens KcBERT 15개 조건 Matched Control 실험**, **불확실성(Brier Score)**, **하위집단(URL 유무)**, 그리고 **4대 오류 전이(Transition)** 결과를 SAS Studio 및 SAS Visual Analytics(VA)에서 시각화하기 위한 **사용 데이터 명세**와 **시각화 방법론**을 상세히 기술합니다.

---

## 1. 디렉터리 및 파일 구성

```
sas/
├── data/processed/sas/
│   ├── sas_kcbert_15arms.csv          # 15개 조건(Arm x Seed) 전수 평가 지표
│   ├── sas_kcbert_arm_summary.csv     # 조건별(Arm) 종합 평균 및 표준편차
│   ├── sas_kcbert_subgroup_url.csv    # URL 유무(URL_YES / URL_NO) 하위집단 집계
│   ├── sas_kcbert_transitions.csv     # FLIP 전환 시 4대 오류 전이 분석 집계
│   └── sas_kcbert_top_uncertain.csv   # 상위 50개 고불확실성 유사도 그룹 집계
├── sas/
│   ├── 00_RUN_KCBERT_VISUALS_CAS.sas  # 시각화 및 CAS 적재 원클릭 통합 실행기
│   ├── 14_kcbert_visuals.sas          # PROC SGPLOT / SGPANEL 고해상도 시각화 프로그램
│   └── 15_publish_kcbert_to_cas.sas   # SAS Viya CAS 적재 및 승격(promote) 프로그램
└── docs/
    └── SAS_KCBERT_VISUALIZATION_GUIDE_20260918.md # 본 가이드라인
```

---

## 2. 사용 데이터셋 명세 (Data Specifications)

모든 입력 데이터는 원문 텍스트나 개인식별정보(PII)가 일체 배제된 **비식별 통계 집계 데이터(CSV)**입니다.

### ① `sas_kcbert_15arms.csv` (15행 $\times$ 11열)
* **설명**: 3대 실험 조건(DUP, FLIP, BASE) 각각에 대해 5개 난수 시드(42, 101, 202, 303, 404)로 평가된 15개 모델의 검증셋 최적 임계값 적용 결과.
* **주요 변수**:
  - `arm` (문자형): 실험 조건 (`DUP`: 중복제거 기준, `FLIP`: 난독화반전 기준, `BASE`: 기본 모델)
  - `seed` (숫자형): 데이터 분할 및 학습 난수 시드 (42, 101, 202, 303, 404)
  - `threshold` (숫자형): 검증셋에서 FPR $\le 1.0\%$ 제약 하에 선정된 분류 임계값
  - `recall` (백분율): 악성 문자 재현율 ($TP / (TP + FN)$)
  - `fpr` (백분율): 정상 문자 오탐률 ($FP / (TN + FP)$) — **1.0% 이하 통제 여부 확인**
  - `f1` (백분율): 재현율과 정밀도의 조화평균
  - `brier_score` (숫자형): 확률 예측 오차 점수 (0에 가까울수록 확률 신뢰도 우수)
  - `tp`, `fp`, `fn`, `tn` (정수형): 혼동 행렬 빈도수

### ② `sas_kcbert_arm_summary.csv` (3행 $\times$ 9열)
* **설명**: 조건(Arm)별 5개 시드의 평균 및 표준편차 요약 통계.
* **주요 변수**:
  - `arm`: 실험 조건 (DUP, FLIP, BASE)
  - `f1_mean`, `f1_std`: F1-Score 평균 및 표준편차
  - `recall_mean`, `recall_std`: Recall 평균 및 표준편차
  - `fpr_mean`, `fpr_std`: FPR 평균 및 표준편차
  - `brier_mean`, `brier_std`: Brier Score 평균 및 표준편차

### ③ `sas_kcbert_subgroup_url.csv` (6행 $\times$ 9열)
* **설명**: 수신된 문자에 **URL이 포함되어 있는지 여부**에 따른 조건별 탐지 성능.
* **주요 변수**:
  - `arm`: 실험 조건 (DUP, FLIP, BASE)
  - `url_group`: 하위집단 구분 (`URL_YES`: URL 포함, `URL_NO`: URL 미포함)
  - `recall`, `fpr`, `f1`: 하위집단별 탐지 지표

### ④ `sas_kcbert_transitions.csv` (4행 $\times$ 7열)
* **설명**: DUP 모델에서 FLIP 모델로 전환했을 때 판정이 바뀐 4대 오류 전이 현황.
* **주요 변수**:
  - `transition_name`: 오류 전이 코드 (`resolved_fp`, `lost_tp`, `new_fp`, `rescued_fn`)
  - `transition_name_kr`: 한글 명칭 (정상 오탐 해소, 악성 정탐 손실, 신규 정상 오탐, 악성 미탐 구제)
  - `total_count`: 발생 건수
  - `url_1_ratio`: 해당 전이 샘플 중 URL이 포함된 비율
  - `net_effect`: 보안 순효과 (`positive`: 긍정적 개선, `negative`: 부정적 손실)

### ⑤ `sas_kcbert_top_uncertain.csv` (50행 $\times$ 10열)
* **설명**: 모델 간 또는 시드 간 예측 확률 분산이 가장 큰 상위 50개 고불확실성 유사도 그룹.
* **주요 변수**:
  - `development_group_id`: 메시지 유사도 그룹 ID
  - `pred_std`: 예측 확률 표준편차 (불확실성 지표)
  - `flip_pred_mean`, `dup_pred_mean`: 모델별 평균 예측 위험도

---

## 3. SAS 시각화 방법론 및 차트 매핑 (Visualization Guide)

`14_kcbert_visuals.sas`에 구현된 5대 핵심 시각화와 이를 SAS Visual Analytics (VA) 대시보드에 구성하는 방법입니다.

---

### [차트 1] 15-Arm FPR vs Recall 트레이드오프 산점도 (Trade-off Scatter)
* **사용 데이터**: `work.kcbert_15arms`
* **시각화 유형**: 산점도 (Scatter Plot with Reference Line)
* **SAS 프로시저**: `PROC SGPLOT`
* **축 및 변수 매핑**:
  - **X축**: `fpr` (오탐률, False Positive Rate) — 범위: 0.002 ~ 0.014 (백분율 표시)
  - **Y축**: `recall` (재현율, Recall) — 범위: 0.93 ~ 0.99 (백분율 표시)
  - **그룹(색상)**: `arm` (DUP, FLIP, BASE)
  - **라벨(텍스트)**: `seed` (각 점 위에 시드 번호 표시)
  - **참조선(Refline)**: X축 `0.01` 위치에 빨간색 점선 (`FPR 1.0% 규제 상한선`)
* **해석 및 비즈니스 의미**:
  - **FLIP 조건(녹색 점들)**이 재현율 96% 이상을 유지하면서도 모두 FPR 1.0% 상한선 왼쪽에 밀집되어 있어, 상용 서비스 배포에 가장 안전한 파레토 최적(Pareto Optimal) 상태임을 입증합니다.

---

### [차트 2] 조건별 오탐률(FPR) 및 재현율(Recall) 분포 박스플롯 (Distribution Boxplot)
* **사용 데이터**: `work.kcbert_15arms`
* **시각화 유형**: 수직 박스플롯 (Vertical Box Plot)
* **SAS 프로시저**: `PROC SGPLOT`
* **축 및 변수 매핑**:
  - **카테고리(X축)**: `arm` (실험 조건)
  - **반응 변수(Y축)**: `fpr` (차트 2A) 및 `recall` (차트 2B)
  - **참조선**: Y축 `0.01` (FPR 1.0% 기준)
* **해석 및 비즈니스 의미**:
  - 조건별 중앙값뿐만 아니라 **시드 간 변동성(박스의 높이)**을 비교합니다. DUP는 시드에 따라 FPR 편차가 크지만, FLIP은 오탐률이 극히 낮고 일관되게 안정적임을 보여줍니다.

---

### [차트 3] URL 유무별 하위집단 오탐률 패널 바차트 (Subgroup Analysis)
* **사용 데이터**: `work.kcbert_subgroup_url`
* **시각화 유형**: 패널형 수직 막대 차트 (Panel Bar Chart)
* **SAS 프로시저**: `PROC SGPANEL`
* **축 및 변수 매핑**:
  - **패널 구분(`PANELBY`)**: `url_group` (URL 미포함 문자 vs URL 포함 문자, 2열 배치)
  - **카테고리(X축)**: `arm`
  - **반응 변수(Y축)**: `fpr` (오탐률)
  - **그룹(색상)**: `arm`
* **해석 및 비즈니스 의미 (핵심 연구 발견)**:
  - **URL 미포함 정상 문자**: 모든 모델의 오탐률이 0.1% 미만으로 안전합니다.
  - **URL 포함 정상 문자**: DUP 모델은 오탐률이 **3.0%**로 폭증하는 치명적 약점을 보이지만, **FLIP 모델은 0.6% 수준으로 강력하게 억제**합니다. 즉, FLIP이 "URL만 보면 무조건 스미싱으로 오인하는 지름길 편향(Shortcut Learning)"을 완벽히 교정했음을 증명합니다.

---

### [차트 4] Brier Score 불확실성 및 확률 보정 오차 (Calibration Score)
* **사용 데이터**: `work.kcbert_arm_summary`
* **시각화 유형**: 수직 막대 차트 (Bar Chart)
* **SAS 프로시저**: `PROC SGPLOT`
* **축 및 변수 매핑**:
  - **카테고리(X축)**: `arm`
  - **반응 변수(Y축)**: `brier_mean` (평균 Brier 점수)
  - **Y축 범위**: 0.010 ~ 0.014 (확대 표시)
* **해석 및 비즈니스 의미**:
  - Brier Score는 모델이 출력한 예측 확률(예: 80% 위험)이 실제 사건과 얼마나 정밀하게 일치하는지를 나타내며, **낮을수록 우수**합니다.
  - FLIP(0.01158) < DUP(0.01218) < BASE(0.01273) 순으로 나타나, FLIP 조건이 가장 신뢰할 수 있는 예측 확률을 제공합니다.

---

### [차트 5] FLIP 전환 시 4대 오류 전이 건수 및 URL 비율 (Error Transitions)
* **사용 데이터**: `work.kcbert_transitions`
* **시각화 유형**: 막대 차트 (Bar Chart with Legend)
* **SAS 프로시저**: `PROC SGPLOT`
* **축 및 변수 매핑**:
  - **카테고리(X축)**: `transition_name_kr` (오류 전이 범주)
  - **반응 변수(Y축)**: `total_count` (발생 건수) 및 `url_1_ratio` (URL 포함 비율)
  - **그룹(색상)**: `net_effect` (`positive`=파란색/녹색, `negative`=주황색/빨간색)
* **해석 및 비즈니스 의미**:
  - 정상 문자를 악성으로 오탐하던 오류를 고친 **"정상 오탐 해소"가 25건**으로 가장 많으며, 이 중 **92.0%가 URL이 포함된 정상 문자**였습니다. 반면 "악성 정탐 손실(22건)"은 Two-track 동적 게이팅을 통해 보완됩니다.

---

## 4. SAS Visual Analytics (VA) 대시보드 인터랙티브 구성 가이드

SAS Viya 환경에서 `15_publish_kcbert_to_cas.sas`를 실행하면 `CASUSER` 라이브러리에 테이블들이 적재됩니다. VA 리포트 디자이너에서 다음과 같이 대시보드를 구성하는 것을 권장합니다:

```
+-----------------------------------------------------------------------------------+
|  [ScamLens 안심문자 AI 탐지 성능 & 불확실성 대시보드]                             |
+-----------------------------------------------------------------------------------+
|  필터: [실험 조건 (Arm) ▼]   [난수 시드 (Seed) ▼]   [URL 포함 여부 ▼]             |
+-----------------------------------------------------------------------------------+
|  [KPI 카드 1]        [KPI 카드 2]        [KPI 카드 3]        [KPI 카드 4]         |
|  평균 F1-Score       평균 오탐률(FPR)    평균 재현율(Recall)  Brier 오차 점수     |
|  96.66%              0.75% (< 1.0%)      96.55%              0.01136             |
+------------------------------------+----------------------------------------------+
|  [좌측 시각화]                     |  [우측 시각화]                              |
|  차트 1: FPR vs Recall 산점도      |  차트 3: URL 유무별 하위집단 오탐률 비교    |
|  (파레토 최적점 인터랙티브 탐색)   |  (URL 편향 취약성 및 방어력 대조)            |
+------------------------------------+----------------------------------------------+
|  [하단 시각화]                                                                    |
|  차트 5: FLIP 전환 4대 오류 전이 상세 테이블 및 URL 비율 분석                      |
+-----------------------------------------------------------------------------------+
```

---

## 5. 실행 방법

### 방법 A: SAS Studio / SAS 9.4 (원클릭 통합 실행)
1. SAS Studio에서 `sas/00_RUN_KCBERT_VISUALS_CAS.sas` 파일을 엽니다.
2. 실행 단축키(`F3` 또는 상단 달리기 아이콘)를 누릅니다.
3. `outputs/sas_kcbert_visuals/scamlens_kcbert_visuals_report.html`에 5종 고해상도 차트가 자동으로 생성됩니다.

### 방법 B: SAS Viya CAS 적재
1. CAS 세션이 연결된 Viya Compute 환경에서 `00_RUN_KCBERT_VISUALS_CAS.sas`를 실행합니다.
2. 실행 로그에 `[SUCCESS] KcBERT 테이블이 CASUSER 에 적재 및 승격되었습니다.` 메시지가 뜨면 완료됩니다.
3. SAS Visual Analytics에 접속하여 `SCAMLENS_KCBERT_15ARMS_20260918` 테이블을 열고 위 가이드대로 대시보드를 구성합니다.
