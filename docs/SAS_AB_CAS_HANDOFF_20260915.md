# SAS A/B 검수 분석 및 CAS 배포 가이드 (2026-09-15)

> **안내:** 현재 A/B 검수 분석 및 CAS 배포는 통합 실행기 [sas/00_RUN_ALL.sas](../sas/00_RUN_ALL.sas)을 통해 단일 진입점에서 오케스트레이션됩니다. 세부 실행 규약은 [RUNBOOK](../sas/RUNBOOK.md)을 따르며, 이전 가이드는 [보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_AB_CAS_HANDOFF_20260915.md)에 보존되어 있습니다.

본 문서는 ScamLens A/B 검수자 일치도(11), 최종 합의 기준 모델 판정 비교(12), 그리고 SAS Viya CAS 인메모리 배포(13)의 연계 규약과 실행 검수 지침을 기술합니다.

---

## 1. 실행 체계 및 프로파일

모든 활성 SAS 프로그램은 `sas/` 디렉터리에 위치하며, `sas/00_RUN_ALL.sas`가 전체 파이프라인의 유일한 진입점입니다. 과거 개별 실행기들은 아카이브로 이전되었습니다.

### 실행 방법 (SAS Studio / Enterprise Guide)

```sas
%let projroot = /home/student/github;
%let sl_profile = AUTO; /* PUBLIC은 비공개 A/B 단계를 건너뜁니다 */
%let sl_run_cas = 1;    /* CAS 배포 요청 시 명시적 활성화 */
%include "&projroot./sas/00_RUN_ALL.sas";
```

- **실행 프로파일 제어**:
  - `AUTO` (기본값): 비공개 입력 검증과 선행 분석 완료 시 11·12 프로그램을 실행하고, `sl_run_cas=1`이면 13 CAS 프로그램을 실행합니다.
  - `PUBLIC`: 비공개 데이터 기반 분석(11, 12, 13 포함)을 의도적으로 비활성화(`skipped_disabled_by_profile`)하고 공개 집계 분석만 수행합니다.
  - `FULL`: 필수 비공개 입력 누락 시 실행을 즉시 중단합니다.
- **CAS 배포 옵션**:
  - `sl_run_cas`: 명시적으로 `1`로 지정할 때 CAS 적재가 활성화됩니다 (기본값: SAS Viya 1, SAS 9.4 0).

---

## 2. 필수 입력 데이터 및 안전 가드

13 A/B CAS 단계는 11 및 12 단계의 비공개 원본 입력을 엄격히 요구하며 가드를 절대 우회하지 않습니다:

- **필수 비공개 원본 데이터**:
  - `&projroot./data/processed/sas/sas_reviewer_ab_20260914.csv`
  - `&projroot./data/processed/sas/sas_consensus_predictions_20260914.csv`
- **의존성 가드 (Guards)**:
  - 필수 입력 CSV 중 하나라도 없으면 11 단계는 `skipped_missing_input`, 12 단계는 `skipped_missing_upstream`으로 기록됩니다.
  - 11 및 12 단계가 정상 완료(`sc11_complete=1`, `sc12_complete=1`)되지 않은 경우 13 CAS 단계는 `skipped_missing_upstream`으로 차단되며 실행되지 않습니다.
  - 가드를 임의로 우회하거나 선행 검증 없이 CAS 적재를 호출하는 것은 엄격히 금지됩니다.

---

## 3. CAS 적재 규약 및 테이블 명세

Step 11(`sas/13_publish_ab_to_cas.sas`) 실행 시:

- **적재 대상 라이브러리**: 개인 `CASUSER` 라이브러리
- **테이블 명명 규약**: 기존 테이블 덮어쓰기 방지를 위해 실행 시마다 V7 호환의 고유 fresh UUID 접미사(`slva_suffix`, 예: `v<UUID11>`)가 자동으로 부여됩니다.
- **보안 및 개인정보 보호**: 원문 텍스트, 개인 식별자(`review_id`), 검수 사유 등은 적재 대상에서 원천 배제되며 오직 비식별 통계 집계치만 적재됩니다.
- **무결성 검산**: 적재 완료 후 Compute 세션으로 데이터를 즉시 재조회하여 키 정렬 및 값 일치도를 검증합니다.

---

## 4. 산출물 위치 및 수동 검수

- **실행 산출물 폴더**: 고유 실행 루트 `outputs/run_<UUID>/`
  - 마스터 상태: `run_status.csv` (단계 `11_reviewer_ab`, `12_consensus_models`, `13_cas_ab` 확인)
  - 마스터 로그: `master_run.log`
  - 단계별 상세 로그 및 보고서: `11_reviewer_ab.log`, `11_reviewer_ab.html`, `12_consensus_models.log`, `12_consensus_models.html`, `13_publish_ab_to_cas.log`
- **검수 원칙**:
  - 상태 표기 `completed_check_log`는 절차적 성공을 나타내며, 연구자가 각 단계 로그의 ERROR/WARNING 부재 및 수치 출력값을 직접 확인해야 합니다.
  - 실제 SAS 런타임 수동 검수 없이 VA 완료나 모델 성능을 단정하지 않습니다.

---

## 5. 관련 문서

- [SAS 통합 런북](../sas/RUNBOOK.md)
- [이전 A/B CAS 전달 가이드 보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_AB_CAS_HANDOFF_20260915.md)
