# SAS 전체 파일·실행 현황 — 2026-09-14

> 보존 문서: 아래 상태는 작성 당시 기준이다. 2026-09-21 정리에서 기존 출력은 `archive/sas_outputs_20260914/`로, 과거 루트 manifest는 `archive/manifests_20260914/`로 옮겼다. 원문·행별 입력은 로컬 전용이다. 최신 반환 상태는 [자료 모음](../materials/20260921/README.md)을 따른다.

2026-09-14 수치·해시 스냅샷은 `reports/generated/sas_inventory_20260914.json`에 보존한다.
현행 실행 코드와 위치는 2026-09-15 저장소 정리를 반영했다.

현재 실행은 **`sas/00_RUN_AB.sas` → 11 → 12**다. 11은 합의 전 A/B 원응답 일치도,
12는 최종 합의 범주별 저장 모델 판정이다. 과거 A 단독 09·10은 `archive/`로 이동해
현행 SAS 목록과 실행기에서 제외했다.

01·02·03·05·06·07은 기존 실행 로그와 HTML을 확인했다. 08은 반환 CSV에 더해 이전 대화의 사용자 제공 출력표·로그를 회수해 대조했다. 04는 선택 실험이며 필수 실행에서 제외한다. `00_RUN_ALL.sas`는 전체 과거 분석 재현용으로 남겼다.

| 프로그램 | 상태 | 입력 CSV |
|---|---|---|
| `00_RUN_AB.sas` | 현재 실행 진입점 | sas_consensus_predictions_20260914.csv, sas_reviewer_ab_20260914.csv |
| `00_RUN_ALL.sas` | 과거 공통 단계 재현 | sas_fage_abc_rows.csv |
| `00_RUN_PENDING.sas` | 과거 진입점 안내 후 종료 | 하위 단계 입력 없음 |
| `01_load_and_audit.sas` | 기존 로그·HTML 확인 | sas_message_scores.csv, sas_message_text.csv |
| `02_meta_classifier.sas` | 기존 로그·HTML 확인 | 하위 단계 입력/WORK 데이터 |
| `03_model_comparison.sas` | 기존 로그·HTML 확인 | 하위 단계 입력/WORK 데이터 |
| `04_korean_text_model.sas` | 선택 실험·미실행 | 하위 단계 입력/WORK 데이터 |
| `05_visuals.sas` | 기존 로그·HTML 확인 | sas_robustness.csv |
| `06_transformer_contrast.sas` | 기존 로그·HTML 확인 | 하위 단계 입력/WORK 데이터 |
| `07_composition_and_novelty.sas` | 기존 로그·HTML 확인 | sas_external_evaluation.csv |
| `08_fage_gate.sas` | 반환 CSV·회수 로그/표 검산 완료 | sas_fage_abc_rows.csv |
| `11_reviewer_ab_agreement.sas` | A/B 원응답 일치도·실제 실행 결과 보존 | sas_reviewer_ab_20260914.csv |
| `12_consensus_model_comparison.sas` | 최종 합의별 모델 비교·실제 실행 결과 보존 | sas_consensus_predictions_20260914.csv, sas_reviewer_ab_20260914.csv |
| `13_publish_ab_to_cas.sas` | 선택적 CAS 공유·저장 어댑터 | 같은 세션의 11·12 완료 문맥 |

## 08 결과 검산

최신 A/B/C 비교판: 5시드, fold 0, 9방법, 임계값 45행, 예측 92,736행. URL 없는 원 악성은 고유 177개이며, 모델당 시드 반복 분모는 238행이다.

| SAS 방법 | 시드 평균 URL 없는 악성 Recall (%) | 시드 평균 전체 정상 FPR (%) |
|---|---:|---:|
| lr_a | 66.685 | 1.191 |
| lr_b | 63.919 | 0.853 |
| lr_c | 79.674 | 1.160 |
| word | 59.287 | 0.908 |
| kcbert | 90.460 | 0.839 |
| stacking | 91.270 | 1.209 |
| fage | 90.589 | 1.190 |
| fage_a | 90.589 | 1.194 |
| fage_c | 90.887 | 0.880 |

FPR의 분모는 URL 유무를 합한 전체 정상이다. 직전 공통 검수 비교표의 URL 없는 정상 FPR와 범위가 다르다. 시드별 비율 평균과 시드 합산 적중률을 혼용하지 않는다. A/B/C는 모델 조건이며 검수자 이름이 아니다.

회수된 텍스트에서 실제 ERROR 0건, WARNING 0건을 확인했다. 표와 로그를 합친 자료이므로 수렴 문구 횟수를 학습 횟수로 세지 않았다. native ODS HTML 파일 자체는 회수하지 못했다. 저장된 단일 전문가 보정 25개 시드·방법 조합은 원 입력 점수로 비율을 재검산했다. 재적합 게이트의 보정 점수 CSV는 없어 그 부분은 반환 임계값 표와 출력표·로그에 근거한다.

FAGE 채택 기준 미충족 판단은 유지한다. 이전 규칙 탐색 문서의 높은 적중률은 별도 Python 규칙을 같은 자료에서 확인한 것으로, SAS 08 성능이나 독립 검증 결과로 사용하지 않는다.

## 파일 위치와 정본

| 위치 | 역할 |
|---|---|
| `sas/` | 실행 코드·런북·현재 안내 |
| `data/processed/sas/` | 버전 고정 입력 CSV |
| `reports/sas_runs/20260908_final/` | 기존 단계별 로그·HTML·그림 |
| `reports/sas_runs/20260911_fage_abc/` | 최신 08 CSV·출처·회수 증거 |
| `reports/sas_runs/20260911_fage_unweighted/` | 이전 무가중 실행판 |
| `reports/generated/sas_inventory_20260914.json` | 2026-09-14 A 단독 전달판 목록·수치·해시 스냅샷 |
| `reports/generated/fage_results_20260911.*` | 기존 Python/SAS 비교 보고서 |
| `outputs/ab_20260914_*/` | 실제 11·12 실행 로그·HTML·CSV·상태표 |
| `archive/sas_reviewer_a_only_20260912/` | A 단독 09·10 재현 코드 보관본 |
| `manifests/ab_cas_20260915_v1.json` | 11·12와 CAS 어댑터 전달 manifest |

## 사용자 실행 순서

1. 저장소의 `sas/`, `data/`, `reports/`, `docs/`, `outputs/`를 `/home/student/github/` 아래에 함께 배치한다.
2. UTF-8 SAS 세션에서 `sas/00_RUN_AB.sas` 전체를 실행한다.
3. 생성된 새 `outputs/ab_20260914_실행별코드/` 전체와 사용한 manifest를 함께 보관한다.
4. 11·12 로그·HTML·CSV·`run_status.csv`를 입력 판본과 대조한다.

11·12의 기존 실제 SAS 실행 결과는 `outputs/`에 보존되어 있다. 이번 09·10 archive 이동과
런올 수정 자체는 새 SAS 런타임 실행으로 검증하지 않았다.

실행 절차는 `sas/RUNBOOK.md`, CAS 후속 절차는 `docs/SAS_AB_CAS_HANDOFF_20260915.md`를 따른다.
