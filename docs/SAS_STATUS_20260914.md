# SAS 프로그램 및 실행 현황 (2026-09-14)

> **안내:** 현재 SAS 파이프라인은 단일 진입점 [sas/00_RUN_ALL.sas](../sas/00_RUN_ALL.sas)을 통해 통합 실행되며, 세부 실행 규약은 [RUNBOOK](../sas/RUNBOOK.md)을 따릅니다. 이전 상태 문서는 [보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_STATUS_20260914.md)에 보존되어 있습니다.

본 문서는 ScamLens 저장소의 활성 프로그램 구성, 데이터 입력 체계, 고유 격리 출력 구조 및 상태 검수 지침을 기술합니다.

---

## 1. 실행 체계 및 단일 진입점

과거의 개별 실행기들은 아카이브로 이전되었으며, 현재 저장소의 모든 활성 분석은 `sas/00_RUN_ALL.sas` 하나로 통일되었습니다.

- **서버 저장소 루트**: `/home/student/github`
- **활성 프로그램 위치**: 모든 활성 프로그램은 `sas/` 디렉터리 바로 아래에 위치하며, 전체 프로그램 및 지원 모듈 목록은 [조직화 매니페스트](../manifests/sas_organization_20260929.json)를 참조하십시오.

### 활성 프로그램 및 단계별 입력 데이터 명세

| 단계 | 모듈 파일명 (`sas/`) | 주요 역할 | 요구 입력 데이터 |
|---|---|---|---|
| Step 1 | `07_composition_and_novelty.sas` | 독립 외부 평가 분석 | `data/processed/sas/sas_external_evaluation.csv` |
| Step 2 | `01_load_and_audit.sas` | 데이터 적재 및 무결성 감사 | `data/processed/sas/sas_message_scores.csv`, `sas_message_text.csv` |
| Step 3 | `02_meta_classifier.sas` | 문자·URL 결합 메타 분류기 | Step 2 감사 통과 데이터 (`sas_oof_ready=1`) |
| Step 4 | `03_model_comparison.sas` | 고정 test 점수 ROC-AUC 비교 | Step 2 감사 통과 데이터 |
| Step 5 | `06_transformer_contrast.sas` | 트랜스포머 vs ML 대조 분석 | Step 2 감사 통과 데이터 |
| Step 6 | `05_visuals.sas` | 베이스라인 종합 시각화 | `data/processed/sas/sas_robustness.csv` |
| Step 7 | `04_korean_text_model.sas` | 한국어 n-gram 텍스트 모형 (선택) | Step 2 감사 통과 데이터 (`sl_run_text=1` 시) |
| Step 8 | `08_fage_gate.sas` | 실패조건 FAGE 게이트 검증 | `data/processed/sas/sas_fage_abc_rows.csv` |
| Step 9 | `11_reviewer_ab_agreement.sas` | 검수자 A/B 원응답 일치도 | `data/processed/sas/sas_reviewer_ab_20260914.csv` |
| Step 10 | `12_consensus_model_comparison.sas` | 최종 합의 범주별 모델 판정 비교 | `data/processed/sas/sas_consensus_predictions_20260914.csv` |
| Step 11 | `13_publish_ab_to_cas.sas` | A/B 합의 집계 CAS 적재 (선택) | Step 9 및 10 완료 문맥 (`sl_run_cas=1` 시) |
| Step 12 | `14_kcbert_visuals.sas` | KcBERT 15-Arm 시각화 | 독립 내장 공개 datalines (01 감사 의존성 없음) |
| Step 13 | `15_publish_kcbert_to_cas.sas` | KcBERT 집계 CAS 적재 (선택) | Step 12 완료 문맥 (`sl_run_cas=1` 시) |
| Step 14 | `21_followup_diagnostics.sas` | 후속 진단 4단계 종합 파이프라인 | `data/aggregates/followup/` 하위 CSV |
| Step 15 | `99_ZIP_FOLLOWUP_OUTPUTS.sas` | 후속 진단 산출물 네이티브 ZIP 압축 | Step 14 완료 산출물 (`sl_run_zip=1` 시) |
| 보조 30 | `30_load_final_aggregates.sas` | 최종 공개 집계 로더 (31/32 내부 include) | `data/aggregates/final/` 하위 CSV |
| Step 16 | `31_final_visualization.sas` | 최종 종합 ODS HTML5 시각화 | 보조 30 로드 데이터 |
| Step 17 | `32_publish_final_to_cas.sas` | 최종 집계 CAS 적재 (선택) | 보조 30 로드 데이터 (`sl_run_cas=1` 시) |

---

## 2. 데이터 입력 및 산출물 경로 체계

### 입력 데이터 경로
- **공개 최종 집계**: `data/aggregates/final/` (`u5_models.csv`, `u5_features.csv`, `u5_truncation.csv`, `kisa_conditions.csv`, `jev_comparison.csv`, `jev_fusion.csv`)
- **공개 후속 집계**: `data/aggregates/followup/` (`u5/`, `comparison/`, `fusion/`, `kisa_ocr_diagnostics_20260921.csv`)
- **비공개 원본 입력**: `data/processed/sas/` (원문, 개별 예측값 등 비공개 자료)

### 산출물 경로 및 규약
- **고유 실행 루트**: `outputs/run_<UUID>/` (실행별 완전 격리, 이전 결과 덮어쓰기 방지)
- **마스터 실행 파일**:
  - `run_status.csv`: 단계별 실행 상태
  - `master_run.log`: 마스터 실행 로그
  - `run_summary.html`: 실행 요약표
- **후속 진단 산출물**: `outputs/run_<UUID>/followup/run_<UUID>/`
  - ZIP 아카이브: 전역 매크로 변수 `sl_followup_zip_path` 반환 경로
- **최종 시각화 리포트**: `outputs/run_<UUID>/final/run_<UUID>/final_visualization.html`
- **CAS 배포 증거 및 테이블**:
  - CAS 최종 증거 파일: `outputs/run_<UUID>/final/cas_<UUID>/cas_status.txt`
  - 인메모리 테이블: `CASUSER.va_kcbert_*_<suffix>`, `CASUSER.slf_*_<suffix>` (auto fresh 접미사)

---

## 3. 검수 원칙 및 상태 판정

1. **상태 판정**: `run_status.csv`의 `completed_check_log`는 절차적 성공을 의미합니다.
2. **로그 수동 검수**: 연구자가 개별 로그의 ERROR/WARNING 여부 및 반환 수치를 직접 확인하기 전에는 런타임/VA 완료를 단정하지 않습니다.
3. **가드 준수**: 비공개 데이터가 필요한 모듈은 데이터 부재 시 `skipped_missing_input`, 선행 모듈 미완료 시 `skipped_missing_upstream`으로 차단되며 가드를 우회하지 않습니다.

---

## 4. 관련 문서

- [SAS 통합 런북](../sas/RUNBOOK.md)
- [이전 SAS 현황 보관본](../archive/sas_cleanup_20260929/docs_refresh/docs/SAS_STATUS_20260914.md)
