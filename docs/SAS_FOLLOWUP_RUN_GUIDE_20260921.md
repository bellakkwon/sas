# SAS 후속 실행 및 진단 산출물 가이드 (2026-09-21)

> **안내:** 현재 후속 진단 분석은 단일 진입점 [sas/00_RUN_ALL.sas](../sas/00_RUN_ALL.sas)을 통해 통합 실행되며, 실행 상세는 [RUNBOOK](../sas/RUNBOOK.md)을 따릅니다. 이전 개별 패키지 안내는 [보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_FOLLOWUP_RUN_GUIDE_20260921.md)에 보존되어 있습니다.

본 문서는 ScamLens 후속 진단 파이프라인(U5 오류 진단, Jev KcBERT 비교, Jev 결합 모형, KISA OCR 진단) 및 산출물 ZIP 패키징의 실행과 검수 지침을 기술합니다. 비공개 원문이나 개인정보 없이 공개 집계 데이터만으로 분석을 완결할 수 있습니다.

---

## 1. 실행 환경 및 방법

모든 활성 SAS 프로그램은 `sas/` 디렉터리에 위치하며, 단일 실행기 `sas/00_RUN_ALL.sas`가 전체 단계를 순차 오케스트레이션합니다.

### 실행 코드 (SAS Studio / Enterprise Guide)

```sas
%let projroot = /home/student/github;
%let sl_profile = PUBLIC; /* 또는 AUTO */
%let sl_run_zip = 1;      /* 후속 진단 산출물 ZIP 패키징 활성화 (기본값) */
%include "&projroot./sas/00_RUN_ALL.sas";
```

- **입력 데이터 위치**: `&projroot./data/aggregates/followup/`
  - `u5/`: `eval_metadata_summary.csv`, `model_seed_diagnostics.csv`, `error_breakdown_by_feature.csv`, `truncation_audit_summary.csv`, `persistent_error_summary.csv`, `paired_transition_summary.csv`
  - `comparison/`: `aggregate.csv`
  - `fusion/`: `aggregate.csv`
  - `kisa_ocr_diagnostics_20260921.csv`
- **프로그램 단계**:
  - Step 14: `sas/21_followup_diagnostics.sas` (후속 4대 진단 오케스트레이션)
  - Step 15: `sas/99_ZIP_FOLLOWUP_OUTPUTS.sas` (후속 산출물 순수 SAS 네이티브 ZIP 압축)

---

## 2. 산출물 구조 및 위치

실행마다 `outputs/run_<UUID>/` 고유 폴더가 생성되며, 후속 진단 산출물은 해당 마스터 폴더 하위에 격리 저장됩니다:

- **마스터 실행 기록**:
  - `outputs/run_<UUID>/run_status.csv`: 단계별 상태 (Step 14: `21_followup`, Step 15: `99_zip_followup`)
  - `outputs/run_<UUID>/master_run.log`: 마스터 실행 로그
  - `outputs/run_<UUID>/run_summary.html`: 실행 요약표
- **후속 진단 상세 산출물**: `outputs/run_<UUID>/followup/run_<UUID>/`
  - 단계별 상세 로그: `stage_u5.log`, `stage_cmp.log`, `stage_fus.log`, `stage_kisa.log`
  - 단계별 ODS 보고서: `stage_u5/outputs/u5_error_diagnostics_report.html`, `stage_cmp/outputs/jev_kcbert_comparison_summary.html`, `stage_fus.html`, `kisa_stage.html`
  - KISA 검증 재출력: `kisa_verified_readback.csv`
  - 진단 요약 및 상태: `followup_summary.html`, `run_status.txt`

---

## 3. 후속 진단 산출물 ZIP 패키징

SAS Studio 등 폴더 전체 직접 다운로드가 지원되지 않는 환경을 위해, `sas/99_ZIP_FOLLOWUP_OUTPUTS.sas`가 생성된 진단 결과물을 단일 ZIP 아카이브로 자동 패키징합니다.

- **ZIP 파일 경로 규약**: ZIP 아카이브의 실제 파일명은 사후 검증 통과 후 권위 있는 전역 매크로 변수 `sl_followup_zip_path`를 통해 반환됩니다 (경로 패턴: `outputs/run_<UUID>/followup/run_<UUID>_evidence_<UUID>.zip`).
- **주의 사항**:
  - `master_run.log`에는 이 ZIP 경로가 출력되지 않습니다.
  - 실제 생성 경로는 SAS Studio 로그의 `SCAMLENS_FOLLOWUP_ZIP_COMPLETE` 마커 라인 및 반환된 전역 매크로 변수 `sl_followup_zip_path`를 통해 확인하십시오.
  - ZIP 파일명을 임의로 추측하거나 고정 파일명으로 가정하지 마십시오.
  - 과거 삭제된 패키지 루트 경로를 참조하지 마십시오.

---

## 4. 검수 및 연구 무결성 원칙

1. **상태 판정**: `run_status.csv`에 기록되는 `completed_check_log`는 절차적 정상 완료를 의미합니다.
2. **로그 수동 검수**: 각 단계별 로그(`stage_*.log`)의 ERROR/WARNING 부재 및 수치 출력 정상성을 연구자가 반드시 직접 검수해야 합니다.
3. **결과 해석 주의**: SAS 런타임 결과는 정적 코드 검사와 구별되며, 실제 실행 로그 및 반환 수치 대조 전에는 검증 완료로 간주하지 않습니다.

---

## 5. 관련 문서

- [SAS 통합 런북](../sas/RUNBOOK.md)
- [이전 후속 실행 가이드 보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_FOLLOWUP_RUN_GUIDE_20260921.md)
