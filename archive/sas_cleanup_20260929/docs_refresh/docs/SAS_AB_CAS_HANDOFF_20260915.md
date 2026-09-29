> **2026-09-29 안내:** 아래는 이전 실행 이력입니다. 현재 실행 파일은 [00_RUN_ALL.sas](../sas/00_RUN_ALL.sas) 하나이며 [RUNBOOK](../sas/RUNBOOK.md)을 따릅니다. 옛 실행기는 `archive/sas_cleanup_20260929/`에 보존했습니다.

# SAS 11·12 보완과 CAS 전달 — 2026-09-15

## 이번 변경의 의미

기존 분석을 다시 설계한 것이 아니라, 같은 결과를 더 안전하게 확인하고 시각화로
넘기기 위한 보완이다. 모델 학습·임계값·정답 라벨·원본 CSV는 바꾸지 않는다.
이 분석은 이전 A/B 본문 검수 자료에 대한 것이며, 이름형 토큰 검수나 진행 중인
URL 편집 검수의 독립성 확인을 가져다 쓰지 않는다.

| 파일 | 변경 | 그대로 유지하는 것 |
|---|---|---|
| `sas/11_reviewer_ab_agreement.sas` | `11_final_category_cells.csv` 추가: 최종 범주별 n·proportion | 합의 전 일치도·비가중 kappa·기존 출력 |
| `sas/12_consensus_model_comparison.sas` | 검수 CSV와 ID·최종 범주 교차 확인, 같은 ID의 시드 간 라벨·범주 일관성 확인 | 기존 모델·시드·분할·계산식·출력 |
| `sas/00_RUN_AB.sas` | 상태 테이블 생성·추가·저장 오류 검사, 성공한 실행 문맥 생성 | 새 출력 폴더 생성, 11→12 순서 |
| `sas/13_publish_ab_to_cas.sas` | 집계만 담은 시각화용 WORK 테이블 준비 및 선택적 CAS 적재 | 기본값은 CAS 연결·적재 없음 |
| `sas/00_RUN_AB_CAS.sas` | 11→12→개인 CASUSER 적재·승격 통합 실행 | 집계 allowlist·읽기 대조·덮어쓰기 방지 |
| `sas/00_RUN_ALL_AB_CAS.sas` | 과거 01~08→상태 검사→11→12→CAS 통합 실행 | 선택 단계 skip 정책·오류 시 CAS 진입 차단 |

11은 합의 전 검수자 판단의 일치도를 계산한다. 추가한 최종 범주표는 합의 후 구성비이며
일치도와 다른 개념이다. 12의 오류 판정 기준은 계속 `original_label`이다.
`final_category`는 결과를 나누어 보는 층일 뿐 새 정답이 아니다.
URL 없는 선택된 development 행에 대한 기술적 분석이며 일반화 성능이나 인과효과로 해석하지 않는다.

## 통합 실행기

새 UTF-8 Compute 세션에서 현재 A/B 분석과 CAS 적재만 실행하려면
`sas/00_RUN_AB_CAS.sas` 전체를 실행한다. 과거 공통 단계까지 모두 재현하려면
`sas/00_RUN_ALL_AB_CAS.sas`를 실행한다. 후자는 `00_RUN_ALL` 상태표에
`requires_review`가 하나라도 있으면 A/B와 CAS 단계로 넘어가지 않는다.

두 통합 실행기는 개인 `CASUSER`, `upload=1`, `promote=1`, `save=0`이 기본이다.
CAS 대상 이름에는 실행 `run_tag`에서 만든 새 12자 이하 접미사가 자동으로 붙는다.
`Public`을 기본으로 사용하지 않고 기존 대상을 삭제하거나 덮어쓰지 않는다. 영구 저장이
필요한 경우에만 실행 전 `scabcas_save=1`로 바꾼다. 실제 성공은 로그의
`SCAMLENS_AB_CAS_RUN_COMPLETE` 또는 `SCAMLENS_ALL_AB_CAS_RUN_COMPLETE`와
`SCAMLENS_CAS_UPLOAD_VERIFIED`를 모두 확인한다.

## 먼저 해야 할 일: 새 00_RUN_AB 실행

1. GitHub 연동 폴더의 새 코드가 SAS 서버까지 전달됐는지 확인한다. 로컬 파일 수정만으로 원격 동기화를 증명할 수 없다.
2. 새 Compute 세션에서 `sas/00_RUN_AB.sas`의 `projroot`가 서버 실제 프로젝트 루트인지 확인한다. 기본은 `/home/student/github`이다.
3. **11·12를 각각 실행하지 말고 00_RUN_AB 전체를 실행한다.** 입력 누락 오류라면 오류에 나온 경로와 파일 존재부터 확인한다. 새 검사를 삭제해서 통과시키지 않는다.
4. 새 `outputs/ab_20260914_.../` 폴더의 로그·HTML·CSV를 보관한다. 접두 날짜는 입력 버전이며 새 코드가 과거 버전이라는 뜻은 아니다.
5. 기존 분석 CSV에 `11_final_category_cells.csv`가 추가됐는지 확인한다. `run_status.csv`는 별도 실행 상태 파일이다.
6. 아래 새 MANIFEST와 출력 폴더를 함께 반환해 검산한다. 완료 NOTE만 보고 수치 검증을 생략하지 않는다.

로컬 프로젝트에서 반환 검산:

```sh
python scripts/verify_sas_ab_cas_return_20260915.py /반환받은/새실행폴더 \
  --manifest dist/sas/20260915_ab_cas_v1/MANIFEST.json
```

새 검증기는 기존 모든 결과·로그·HTML·상태 검사를 유지하고 최종 범주표를 입력 CSV에서
다시 계산해 대조한다. 과거 v2.1 MANIFEST는 과거 코드의 지문이므로 새 코드 검사에 사용하면
불일치하는 것이 정상이다. 과거 ZIP·MANIFEST·반환 결과는 덮어쓰지 않는다.

## CAS 사용: 준비와 적재를 나눠 실행

새 00_RUN_AB가 성공한 **같은 Compute 세션**에서 실행한다. 한국어 표시 열을 위해 UTF-8
세션을 사용한다. 새 코드를 실행하지 않은 과거 WORK 테이블은 실행 문맥 검사에서 거부한다.

우선 미적재 점검:

```sas
%let slva_upload=0;
%let slva_promote=0;
%let slva_save=0;
%include "&projroot./sas/13_publish_ab_to_cas.sas";
```

`SCAMLENS_CAS_PREPARED_NOT_UPLOADED`와 `work.slva_...` 테이블을 확인한다.
이는 CAS 성공 표시가 아니다. 실제 적재는 반환 검산과 대상 caslib·권한 확인 후에만 진행한다.

아래는 사용자가 직접 실행하는 **예시**다. `MY_CASLIB`은 실제 허용된 이름으로 바꾸고,
`v0915a`는 사용한 적 없는 접미사로 정한다. caslib와 접미사는 V7 이름, 접미사는 최대 12자다.

```sas
%let slva_caslib=MY_CASLIB;
%let slva_suffix=v0915a;
%let slva_upload=1;
%let slva_promote=0;
%let slva_save=0;
%include "&projroot./sas/13_publish_ab_to_cas.sas";
```

어댑터는 모든 대상 테이블의 부재를 먼저 확인하고 적재 후 Compute로 읽어 와 키 정렬·
전체 값 비교를 한다. 원문·review_id·검수 사유는 적재 대상에서 제외한다.
공유가 필요하면 별도 실행 전에 `slva_promote=1`, 영구 파일 저장이 필요하면
`slva_save=1`로 명시한다. 기본 0이므로 세션 적재만으로 VA에서 보이거나 재접속 후
남는다고 가정하면 안 된다. [SAS CAS 문서](https://documentation.sas.com/api/docsets/pgmdiff/3.5/content/pgmdiff.pdf?locale=en)의
세션/전역 범위와 영구 저장 구분을 따른다. CASUSER의 전역 테이블도 모든 사용자에게 공개된다는 뜻은 아니다.

같은 접미사로 재실행하면 기존 테이블을 덮어쓰지 않고 중단한다. 기존 SLVCAS libref가
남아 있어도 중단한다. 재시도 전 로그와 부분 산출물을 확인하고 새 Compute 문맥·새 접미사를
사용한다. 실패 시 일부 새 CAS 테이블·파일이 남을 수 있으며 자동 삭제·롤백하지 않는다.
적재 전후 비교는 [PROC COMPARE SYSINFO](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a000146743.htm)를
즉시 읽어 값·키·행/열·자료형 차이를 검사한다. CAS의 표시 형식·길이 등 메타데이터 차이는 허용한다.

## 올릴 테이블과 시각화

CAS 이름은 아래 이름 뒤에 `_접미사`가 붙는다. 각 테이블에는 실행 ID와 입력/분석 버전이 붙는다.

| CAS 테이블 | 권장 그림 | 반드시 지킬 집계 기준 |
|---|---|---|
| `ab_category` | A 범주 × B 범주 히트맵 | 셀 `n` 합계. 합의 전 판단 |
| `ab_agreement` | 항목별 일치율·kappa 별도 막대 | `measure`별 한 행. kappa는 백분율이 아니며 음수도 유지 |
| `ab_action` | 행동별 A/B 교차표 | 한 행동 안에서만 `n` 합계. 행동 전체를 더해 사람 수로 표시하지 않음 |
| `ab_final` | 최종 범주 구성비 막대 | 합의 후 구성비. `proportion`은 백분율 표시만 적용 |
| `model_seed` | 모델별 시드 점·범위, recall/FPR/F1 별도 그림 | 시드별 비율과 분모 표시. 범위를 신뢰구간으로 부르지 않음 |
| `model_strata` | 최종 범주별 recall 또는 FPR 히트맵 | 시드·원 라벨 필터. 양성 분모는 recall, 음성 분모는 FPR |
| `model_mean` | 모델별 recall·FPR·F1 요약 | 이미 계산한 시드별 비율의 비가중 평균. SUM 금지 |

첫 화면은 `ab_category`·`ab_final`·`model_mean`, 세부 탐색은 나머지 테이블이 적절하다.
VA에서 비율은 합계를 기본 집계로 두지 않는다. 시드를 합쳐 혼동행렬로 다시 계산한 비율은
`model_mean`의 비가중 평균과 다른 지표다. 시드 사이 같은 review가 겹치므로 독립 표본으로
취급하지 않는다. 층별 `n=0`은 빈 층이며 recall/FPR 결측을 0으로 바꾸지 않는다.
`positive_n`·`negative_n`·`sample_present`를 툴팁/필터에 사용한다.

## 검증 범위와 남은 작업

분석 검증 스킬에 따라 기존 계산 보존과 새 오류 차단을 분리했다. Luna가 11·12·실행기와
반환 검증기를 담당했고 메인이 실제 차이·테스트를 읽고 수정·재검사했다. CAS 코드는 메인이
구현하고 별도 검토했다. 실행 의존성 기록은 `docs/SAS_AB_EXECUTION_20260914.md`에 있다.

로컬 검증 명령:

```sh
python -m unittest tests/test_sas_ab_cas_20260915.py \
  tests/test_sas_ab_return_20260914.py tests/test_sas_ab_cas_return_20260915.py
python -m pytest -q tests/test_sas_ab_bundle_20260914.py
python scripts/create_sas_ab_cas_bundle_20260915.py --check \
  dist/sas/20260915_ab_cas_v1/scamlens_sas_ab_cas_20260915_v1.zip
```

테스트는 과거 코드의 계산 블록 불변, 실제 입력 기반 SQL 조건 검산, 오류 입력 거부,
추가 표의 원자료 대조, 기본 미적재·집계 열 제한을 검사한다. SQLite 대조와 SAS 어휘 검사는
실제 SAS 컴파일/실행이 아니다. 테스트 결과·불변 파일 검사는
`reports/generated/sas_ab_cas_local_validation_20260915.json`에 기록한다.

**남은 필수 확인:** 새 SAS 실행 → 반환 검산 → 실제 CAS 적재/읽기 대조 → VA에서
표시·집계·접근 권한 확인. 이번 수정만으로 이 단계들이 완료되지는 않는다.
Git 커밋·푸시와 원격 업로드는 수행하지 않는다.
