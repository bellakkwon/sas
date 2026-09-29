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

`AUTO`는 가능한 분석을 순서대로 실행하고, 비공개 입력이 없으면 상태표에 이유를 남깁니다. `PUBLIC`은 공개 집계만 실행합니다. `FULL`은 기존 분석의 필수 입력이 부족하면 중단합니다. CAS는 Viya에서 기본 활성, SAS 9.4에서 기본 비활성이며 호출자의 설정을 유지합니다. SAS 문자 모델은 설정을 켠 경우 실행합니다. KcBERT 재학습은 기존 로컬 경로를 유지하며 SAS 통합 분석과 구분합니다.

검사 명령:

```sh
python3 scripts/verify_sas_layout.py
python3 scripts/build_project_readme.py --check
python3 scripts/verify_materials.py
git diff --check
```

검사기는 활성 파일 목록, 과거 파일·집계 해시, include 경로, 실행 계약, 현재 안내 링크를 대조합니다. 코드·폴더 정리 검증이며 새 SAS Studio·CAS·VA 실행 증거를 대신하지 않습니다. 비공개 데이터와 기존 반환 결과·발표 자료는 수정하지 않았습니다.

## SAS Studio 상태 기록 오류 수정

사용자 실행 로그에서 `The keyword parameter SL_RUN_TEXT was not defined with the macro.` 오류를 확인했습니다. 비활성화 이유의 `sl_run_text=0`이 매크로 키워드 인자로 해석된 원인입니다. 텍스트 모델·CAS·ZIP 안내의 등호 문구는 `%nrstr`, 실행 결과 변수를 포함한 문구는 `%bquote`, 함수 간 설명문 전달은 `%superq`로 보호했습니다. 이전 실패 호출과 마스킹 누락은 `python3 scripts/test_sas_layout.py -q`로 검사합니다.

SAS 서버의 `/home/student/github`에서 `git pull --ff-only origin main` 후 새 Compute 세션에서 `sas/00_RUN_ALL.sas`를 실행하면 됩니다. 사용자 로그의 비공개 CSV 누락 상태는 AUTO의 건너뜀이며, 전체 원본 분석에는 해당 입력이 별도로 필요합니다. 이 수정의 로컬 검증은 오프라인 검사이고 실제 SAS 재실행은 대기 중입니다.

## CAS 기본 실행과 마지막 요약 출력

후속 로그에서 `32_cas_final / skipped_disabled_by_option / sl_run_cas=0`을 확인했습니다. CAS를 실행하지 않은 원인은 당시 기본값이 0이었던 설정입니다. 단일 실행기의 Viya 기본값을 1로 바꾸고 SAS 9.4 기본값과 호출자 설정은 유지했습니다. 기존 세션의 0을 켜려면 `%let sl_run_cas=1;`을 먼저 제출합니다. 게시 모듈의 UUID 이름·읽기 대조·승격 및 기존 테이블 보존 절차는 그대로 사용합니다.

자체 보고서가 ODS 목적지를 닫은 뒤에도 마지막 요약표를 출력하도록 `run_summary.html` 전용 목적지를 열고 출력 결과와 파일을 검사합니다. `CAS_KCBERT_TABLES=`·`CAS_FINAL_TABLES=` 로그로 이번 CASUSER 테이블 접미사를 확인합니다. 이는 코드·오프라인 검사 변경이며 새 CAS 실행 성공은 서버 로그로 별도 확인합니다. Viya 버전 판별은 [SAS 공식 설명](https://blogs.sas.com/content/iml/2022/02/28/release-license-sas-viya.html), 닫힌 ODS 목적지의 재개 필요성은 [SAS ODS 설명](https://support.sas.com/documentation/cdl/en/odsug/65308/HTML/default/n1sqlptpa8rdtsn1g45nrh7yoff6.htm)을 따릅니다.
