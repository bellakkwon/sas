# SAS 실행·폴더 정리 — 2026-09-29

현재 시작 파일은 [00_RUN_ALL.sas](../sas/00_RUN_ALL.sas) 하나입니다. 모든 활성 SAS 프로그램을 `sas/` 바로 아래로 모았습니다. [설정·실행 안내](../sas/RUNBOOK.md)를 따르면 됩니다.

| 폴더 | 용도 |
|---|---|
| `sas/` | 단일 실행기와 분석·시각화·CAS·ZIP 모듈 |
| `data/aggregates/` | 공개 후속 진단·최종 보고서 입력 |
| `outputs/run_<UUID>/` | 매 실행의 상태표·로그·보고서·반환 자료. Git 제외 |
| `docs/`, `materials/`, `reports/` | 실행 안내·발표·기존 결과 근거 |
| `archive/sas_cleanup_20260929/` | 옛 실행기·복사본·전달 패키지·Compute 재학습 인계 |

이전 루트의 `followup_20260921_v1/`, `visualization_20260921_v1/`와 SAS 하위의 `kcbert_matched_20260917/`는 보관 폴더로 옮겼습니다. 이전 파일 바이트와 패키지 manifest를 보존했습니다. 활성 입력에는 같은 공개 집계 CSV를 사용합니다. 상세 출처와 해시는 [정리 manifest](../manifests/sas_organization_20260929.json)에 있습니다.

`AUTO`는 가능한 분석을 순서대로 실행하고, 비공개 입력이 없으면 상태표에 이유를 남깁니다. `PUBLIC`은 공개 집계만 실행합니다. `FULL`은 기존 분석의 필수 입력이 부족하면 중단합니다. CAS와 SAS 문자 모델은 각각 설정을 켠 경우 실행합니다. KcBERT 재학습은 기존 로컬 경로를 유지하며 SAS 통합 분석과 구분합니다.

검사 명령:

```sh
python3 scripts/verify_sas_layout.py
python3 scripts/build_project_readme.py --check
python3 scripts/verify_materials.py
git diff --check
```

검사기는 활성 파일 목록, 과거 파일·집계 해시, include 경로, 실행 계약, 현재 안내 링크를 대조합니다. 코드·폴더 정리 검증이며 새 SAS Studio·CAS·VA 실행 증거를 대신하지 않습니다. 비공개 데이터와 기존 반환 결과·발표 자료는 수정하지 않았습니다.
