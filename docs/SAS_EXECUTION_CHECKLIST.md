# SAS 실행 체크리스트

> **안내:** 현재 SAS 파이프라인의 유일한 실행 진입점은 [sas/00_RUN_ALL.sas](../sas/00_RUN_ALL.sas)이며, 상세 실행 규약은 [RUNBOOK](../sas/RUNBOOK.md)을 따릅니다. 이전 실행 가이드는 [보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_EXECUTION_CHECKLIST.md)에 보존되어 있습니다.

현재 완료 범위와 연구 결과 수치는 [SAS 현황](SAS_STATUS_20260914.md)을 참조하십시오. 상태 표기(`completed_check_log`)는 절차적 완료를 의미하며, 실제 SAS 런타임 검증 및 수치 일치 여부는 연구자가 로그와 산출물을 직접 수동 검수해야 합니다.

---

## 1. 실행 전 점검 (Preflight Checklist)

- [ ] **서버 저장소 위치 확인**: SAS 서버 내 저장소 루트가 `/home/student/github`에 위치하는지 확인 (경로 상이 시 `%let projroot = ...;` 지정)
- [ ] **세션 무결성 확보**: 이전 작업의 잔여 오류(`SYSCC > 0`)가 없는 클린 세션(fresh session) 및 UTF-8 인코딩 세션 시작
- [ ] **입력 데이터 준비 상태 점검**:
  - 공개 최종 집계: `data/aggregates/final/` (6개 필수 CSV 완비 여부)
  - 공개 후속 집계: `data/aggregates/followup/` (u5, comparison, fusion, kisa_ocr_diagnostics_20260921.csv 완비 여부)
  - 비공개 원본 입력 (선택/필수 프로파일별): `data/processed/sas/`
- [ ] **실행 프로파일 및 제어 변수 결정**:
  - `sl_profile`: `AUTO` (기본값: 데이터 완비에 따라 가용 단계 자동 실행), `PUBLIC` (공개 집계 14, 21, 99, 31 및 CAS 전용), `FULL` (비공개 데이터 누락 시 즉시 중단)
  - `sl_run_cas`: 명시적 CAS 배포 요청 시 `1` 지정 (Viya 기본 1, SAS 9.4 기본 0)
  - `sl_run_text`: 04 한국어 n-gram 텍스트 모형 포함 시 `1` 지정 (기본값: `0`)
  - `sl_run_zip`: 후속 진단 결과 ZIP 패키징 수행 시 `1` 지정 (기본값: `1`)

---

## 2. 실행 절차 (Execution Steps)

1. SAS Studio 또는 Enterprise Guide에서 아래 코드를 제출합니다:
   ```sas
   %let projroot = /home/student/github;
   %let sl_profile = AUTO; /* 또는 PUBLIC */
   %let sl_run_cas = 1;    /* CAS 배포 요청 시 명시적 지정 */
   %include "&projroot./sas/00_RUN_ALL.sas";
   ```
2. 모든 활성 실행 모듈은 `sas/` 디렉터리 내 프로그램으로 단일 오케스트레이션됩니다.
3. 13 A/B CAS 단계는 11 및 12 단계가 비공개 입력 완비 하에 정상 완료된 경우에만 실행되며 가드를 절대 우회하지 않습니다.

---

## 3. 실행 후 산출물 검수 (Post-Run Verification)

- [ ] **마스터 산출물 디렉터리**: 고유 실행 폴더 `outputs/run_<UUID>/` 생성 확인 (이전 실행 결과 보존 및 격리)
- [ ] **마스터 실행 기록 검수**:
  - `outputs/run_<UUID>/run_status.csv`: 모든 단계 상태가 `completed_check_log` 또는 의도된 건너뜀(`skipped_*`)인지 확인
  - `outputs/run_<UUID>/master_run.log`: ERROR/WARNING 발생 여부 및 최종 종합 판정 확인
  - `outputs/run_<UUID>/run_summary.html`: 단계별 요약표 확인
- [ ] **후속 진단 산출물 검수**:
  - `outputs/run_<UUID>/followup/run_<UUID>/`: 단계별 로그, ODS 보고서, `kisa_verified_readback.csv` 확인
  - ZIP 파일: 전역 매크로 변수 `sl_followup_zip_path`가 반환한 경로의 ZIP 패키지 확인 (임의 파일명 추측 금지)
- [ ] **최종 종합 시각화 검수**:
  - `outputs/run_<UUID>/final/run_<UUID>/final_visualization.html` 및 `run_status.txt` 확인
- [ ] **CAS 배포 증거 검수** (CAS 실행 시):
  - 증거 파일: `outputs/run_<UUID>/final/cas_<UUID>/cas_status.txt`
  - CASUSER 인메모리 테이블: `va_kcbert_*_<suffix>`, `slf_*_<suffix>` (실행별 자동 생성 fresh UUID 접미사 확인)
- [ ] **수동 검수 완료**: 연구자가 로그와 수치를 대조하기 전에는 런타임/VA 완료를 단정하지 않음

---

## 4. 참고 및 연계 문서

- [SAS 통합 런북](../sas/RUNBOOK.md)
- [SAS 실행 현황](SAS_STATUS_20260914.md)
- [이전 체크리스트 보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_EXECUTION_CHECKLIST.md)
