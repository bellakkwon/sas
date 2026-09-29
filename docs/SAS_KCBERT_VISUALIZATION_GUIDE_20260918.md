# ScamLens: KcBERT SAS 시각화 및 CAS/VA 가이드라인 (2026-09-18)

> **안내:** 현재 KcBERT 시각화 및 CAS 적재는 단일 진입점 [sas/00_RUN_ALL.sas](../sas/00_RUN_ALL.sas)을 통해 통합 실행되며, 실행 상세는 [RUNBOOK](../sas/RUNBOOK.md)을 따릅니다. 이전 개별 실행기 및 가이드는 [보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_KCBERT_VISUALIZATION_GUIDE_20260918.md)에 보존되어 있습니다.

본 문서는 ScamLens KcBERT 15개 조건 Matched Control 실험, 불확실성(Brier Score), 하위집단(URL 유무), 4대 오류 전이(Transition) 결과를 SAS Studio 및 SAS Visual Analytics(VA)에서 시각화하기 위한 데이터 명세와 연계 규약을 기술합니다.

---

## 1. 실행 체계 및 환경

모든 활성 SAS 프로그램은 `sas/` 디렉터리에 위치하며, 과거 개별 실행기들은 아카이브로 이전되었습니다.

### 실행 방법 (SAS Studio / Enterprise Guide)

```sas
%let projroot = /home/student/github;
%let sl_profile = AUTO; /* 또는 PUBLIC */
%let sl_run_cas = 1;    /* CAS 배포 요청 시 명시적 활성화 */
%include "&projroot./sas/00_RUN_ALL.sas";
```

- **프로그램 단계**:
  - Step 12: `sas/14_kcbert_visuals.sas` (PROC SGPLOT / SGPANEL 고해상도 시각화 보고서 생성)
  - Step 13: `sas/15_publish_kcbert_to_cas.sas` (SAS Viya CAS 적재 및 글로벌 승격)
- **실행 프로파일**: AUTO 및 PUBLIC 프로파일 모두에서 14 시각화 프로그램을 실행하고, `sl_run_cas=1`이면 15 CAS 프로그램을 실행합니다.

---

## 2. 시각화 데이터 및 차트 매핑

모든 입력 데이터는 원문이나 개인식별정보가 없는 비식별 통계 집계치입니다.

### 5대 핵심 시각화 사양 (14_kcbert_visuals.sas)

1. **[차트 1] 15-Arm FPR vs Recall 트레이드오프 산점도**:
   - 데이터: `work.kcbert_15arms`
   - 축: X축 `fpr` (FPR 1.0% 기준 참조선), Y축 `recall`
   - 목적: FLIP 조건의 파레토 최적성 및 1.0% 상한 준수 입증
2. **[차트 2] 조건별 오탐률(FPR) 및 재현율(Recall) 분포 박스플롯**:
   - 데이터: `work.kcbert_15arms`
   - 목적: 시드 간 편차(박스 높이) 비교를 통한 FLIP의 안정적인 분산 통제 확인
3. **[차트 3] URL 유무별 하위집단 오탐률 패널 분석**:
   - 데이터: `work.kcbert_subgroup_url`
   - 패널: URL 미포함 vs URL 포함
   - 목적: URL 포함 정상 문자에서 DUP 대비 FLIP의 오탐 억제 효과 검증
4. **[차트 4] Brier Score 불확실성 및 확률 보정 오차**:
   - 데이터: `work.kcbert_arm_summary`
   - 목적: 예측 확률 신뢰도(Brier Score, 낮을수록 우수) 비교
5. **[차트 5] FLIP 전환 시 4대 오류 전이 분석**:
   - 데이터: `work.kcbert_transitions`
   - 목적: 정상 오탐 해소, 악성 정탐 손실 등 질적 전이 건수 및 URL 비율 파악

---

## 3. SAS Visual Analytics (VA) 대시보드 연계

CAS 실행(`sl_run_cas=1`) 시 `sas/15_publish_kcbert_to_cas.sas`가 실행되어 개인 `CASUSER` 라이브러리에 5개 집계 테이블을 적재 및 승격합니다:

- **테이블 명명 규약**: 기존 테이블 덮어쓰기를 방지하기 위해 실행 시마다 V7 호환의 고유 fresh UUID 접미사(`slkc_suffix`, 예: `k<UUID7>`)가 자동 생성됩니다:
  - `CASUSER.va_kcbert_15arms_<suffix>`
  - `CASUSER.va_kcbert_arm_summary_<suffix>`
  - `CASUSER.va_kcbert_subgroup_url_<suffix>`
  - `CASUSER.va_kcbert_transitions_<suffix>`
  - `CASUSER.va_kcbert_top_uncertain_<suffix>`
- **VA 리포트 디자인**:
  - VA 접속 후 `CASUSER`에서 해당 실행의 고유 접미사가 붙은 테이블을 선택하여 대시보드를 구성합니다.
  - SAS Studio 로그의 `CAS_KCBERT_TABLES=`에서 이번 실행의 테이블 접두사와 접미사 패턴을 확인하고, CASUSER에서 일치하는 테이블을 선택하십시오.

---

## 4. 산출물 위치 및 수동 검수 지침

- **실행 산출물**: 고유 실행 루트 `outputs/run_<UUID>/`
  - 마스터 상태: `run_status.csv` (단계 `14_kcbert_visuals`, `15_cas_kcbert`)
  - 시각화 보고서: `outputs/run_<UUID>/14_kcbert_visuals.html` 및 `14_kcbert_visuals.log`
  - CAS 로그: `outputs/run_<UUID>/15_publish_kcbert_to_cas.log`
- **검수 원칙**:
  - 상태 표기 `completed_check_log`는 절차적 정상 완료를 의미합니다.
  - 연구자가 각 단계 상세 로그의 ERROR/WARNING 부재 및 수치 출력 정상성을 직접 검수해야 합니다.
  - 로그 및 수치 검산 없이 런타임/VA 완료를 단정하지 않습니다.

---

## 5. 관련 문서

- [SAS 통합 런북](../sas/RUNBOOK.md)
- [이전 KcBERT 시각화 가이드 보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_KCBERT_VISUALIZATION_GUIDE_20260918.md)
