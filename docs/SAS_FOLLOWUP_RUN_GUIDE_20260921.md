> **2026-09-29 안내:** 아래는 이전 실행 이력입니다. 현재 실행 파일은 [00_RUN_ALL.sas](../sas/00_RUN_ALL.sas) 하나이며 [RUNBOOK](../sas/RUNBOOK.md)을 따릅니다. 옛 실행기는 `archive/sas_cleanup_20260929/`에 보존했습니다.

# SAS 후속 실행 안내 (S1, 2026-09-21)

집계 전용 전달본이다. 원문·행 ID·개별 점수·모형·인증 정보를 포함하지
않는다. SAS 실제 실행은 사용자가 수행하며, 메인은 반환 증거로 실행 범위를 확인한다.
아래 정적 점검(Python 스키마·바이트 검사)은 SAS 실행 증명이 아니다.

## 실행 (SAS 서버에서 순서대로)

1. 연동 저장소 최신판 받기 (SAS 서버 셸에서, push는 메인이 수행):

```sh
git -C /home/student/github pull --ff-only
```

체크아웃 경로가 다르면 해당 경로로 교체한다. `followup_20260921_v1/`이
있는 폴더를 `projroot`로 지정한다.

2. SAS Studio / Enterprise Guide에서 정확히 두 줄을 제출한다.
`projroot` 기본값은 `/home/student/github`이다.

```sas
%let projroot = /home/student/github;
%include "&projroot./followup_20260921_v1/sas/00_RUN_FOLLOWUP_20260921.sas";
```

실행기는 4단계(U5 오류 진단·Jev 비교·Jev 결합·KISA OCR 진단)를 순서대로
수행한다. 매 실행마다 `outputs/run_<UUID>/` 새 폴더가 생기며, 기존 폴더를
덮어쓰지 않는다(같은 UUID가 있으면 즉시 중단). 단계 오류(SYSCC/SYSERR)나
산출물 누락이 있으면 즉시 중단하며, 파일 존재만으로 성공 처리하지 않고
기존 로그를 지우지 않는다. 결합 단계는 포함 시점에 검증을 정확히 1회만
수행한다.

## 산출물 위치

실행할 때마다 `outputs/run_<UUID>/` 새 폴더가 생긴다.

- `stage_u5.log`, `stage_cmp.log`, `stage_fus.log`, `stage_kisa.log`:
  단계별 로그. 오류 확인용으로 이 파일을 먼저 본다.
- `stage_u5/outputs/u5_error_diagnostics_report.html`,
  `stage_cmp/outputs/jev_kcbert_comparison_summary.html`,
  `stage_fus.html`, `kisa_stage.html`: 단계별 보고서(ODS).
- `kisa_verified_readback.csv`: KISA 검증 통과 집계의 SAS 재출력.
- `followup_summary.html`, `run_status.txt`: 전체 요약과 상태.

KISA 단계에는 C2 실측 집계(`data/kisa_ocr_diagnostics_20260921.csv`,
19열 계약·3코호트×5시드×7조건=105행)가 필요하다. 코드 전용 전달본에서는
해당 단계가 자료 없음으로 중단되며, 이는 정상적인 실패 닫힘이다.

## 메인에게 반환할 파일

실행 결과는 `.gitignore`의 `/followup_20260921_v1/outputs/` 규칙으로
Git 추적에서 제외된다. GitHub push는 코드 전달용이다. SAS Studio에서 폴더를
통째로 다운로드할 수 없다면 **서버에서 ZIP 하나를 만든 뒤 그 파일을 다운로드**한다.

### ZIP 하나로 받기

1. SAS의 Git 기능에서 최신 main을 Pull한다.
2. 새 SAS 프로그램에 아래 코드를 실행한다. `zip_run`은 받을 실행 폴더 이름이다.

```sas
%let zip_run = run_da5c44c3-0b3d-b342-903c-29f4cbfd619a;
%include "/home/student/github/sas/99_ZIP_FOLLOWUP_OUTPUTS.sas";
```

체크아웃 경로가 다르면 `projroot`을 해당 경로로 설정하고 include 경로도 맞춘다.
[ZIP 반환 도우미](../sas/99_ZIP_FOLLOWUP_OUTPUTS.sas)는 이미 생성된 결과 파일만 묶는다.
분석 실행기를 다시 실행하지 않는다. 이 도우미는 후속 집계 패키지 밖의 별도
전달 도구이며, 기존 패키지의 코드·입력·manifest를 바꾸지 않는다.

3. 성공 로그에 표시된 ZIP 경로를 확인한다. ZIP은
   `/home/student/github/followup_20260921_v1/outputs/` 바로 아래에 생성된다.
4. SAS 파일 목록을 새로고침하고 그 ZIP 파일 하나를 내려받아 전달한다.

HTML·CSV·로그·그래프 이미지의 하위 경로를 보존한다. 결과 ZIP도 기존 Git 제외
경로에 있으므로 `.gitignore` 해제나 강제 추가가 필요 없다. 압축 성공은 원래 분석의
성공 판정과 별개이며, 반환 후 `run_status.txt`와 CSV·그래프를 검사한다.
이 환경에는 SAS 런타임이 없어 압축 실행 자체는 서버에서 확인해야 한다.
구현 방식은 [SAS 공식 ZIP 예제](https://blogs.sas.com/content/sasdummy/2016/03/04/add-files-to-a-zip-archive-with-filename-zip/)를 참고했다.

압축을 사용하지 않을 경우 아래 파일을 개별 다운로드할 수도 있다.

- `run_status.txt`, `followup_summary.html`
- 단계별 로그 4건(`stage_u5.log`, `stage_cmp.log`, `stage_fus.log`,
  `stage_kisa.log`)
- 단계별 보고서 HTML(`u5_error_diagnostics_report.html`,
  `jev_kcbert_comparison_summary.html`, `stage_fus.html`, `kisa_stage.html`)
- U5 재출력 CSV 3건(`sas_model_readback.csv`, `sas_arm_readback.csv`,
  `sas_transition_readback.csv`)
- `kisa_verified_readback.csv` (KISA 단계가 통과한 경우)

## 현재 상태와 한계

- 전달본은 집계 패키지 완성 상태다. C2 실측 집계
  (`data/kisa_ocr_diagnostics_20260921.csv`, 19열 계약·105행,
  코호트별 n=22/18/250)를 포함하며
  `python3 scripts/build_sas_followup_20260921.py` 풀 빌드와 `--check`
  읽기 전용 검증(매니페스트·정식 원본 바이트·스키마 재검사)을 통과했다.
- SAS 정적 점검(금지문·실패 중단 존재)과 Python 스키마 검사를 마쳤고,
  수정 후 네 단계 로그의 무오류·결합 HTML 원본 일치를 확인했다. 실행기 최종 완료 표식과 반환 CSV·그래프 검수는 대기다. 첫 실행에서 확인된 범위와 수정은 아래와 같다.
  SAS 서버 실행과 결과 검수는 메인 확인을 거쳐 진행한다.

## 첫 서버 실행에서 확인된 오류와 수정

사용자가 반환한 stage_u5.log에서는 입력 검증·집계·그래프 생성과 CSV 내보내기가 끝났다.
완료 안내문의 `%put` 안에 있던 세미콜론 때문에 뒤의 안내 문장이 SAS 코드로
해석되어 ERROR 180-322가 발생했다. 실행기의 실패 안내문에도 같은 오류가 있었다.
두 안내문을 수정하고 실패 시 SYSCC/SYSERR 값과 단계 로그의 오류 부분을
SAS Studio 로그에 함께 출력하도록 보완했다. 데이터·분모·검증 기준은 바꾸지 않았다.

수정 후 새 실행의 네 단계 로그는 반환·검사됐다. 현재는 해당 실행의 outputs 폴더 전체를 반환해 최종 완료 표식·CSV·그래프를 확인한다. 받은 로그에서 추가 재실행이 필요한 오류는 발견되지 않았다.
앞선 실패 실행의 outputs 폴더는 보존한다. 최신 실행의 최종 완료 표식과
산출물이 반환돼야 전체 검수를 마칠 수 있다. 오류 상태를 강제로 초기화하거나
압축 성공을 분석 성공으로 표시하지 않는다.

## ZIP 도우미의 정상 실행 폴더명 거부 수정

최초 ZIP 실행에서는 정상적인 `run_<UUID>`가 형식 오류로 거부됐다. `zr`이
고정 길이 문자 변수라서 `zr = strip(...)` 대입 후 뒤쪽이 다시 공백으로 채워지고,
문자열 끝을 검사하는 정규식과 일치하지 않았다. 두 `PRXMATCH` 호출의 입력을
`strip(zr)`로 수정했다. 경로 내 파일명 검사는 이미 호출 지점에서 공백을 제거한다.

원본 코드의 정상 이름 거부를 고정 길이 문자열 모사로 재현하고, 수정 코드의
정상 이름 허용·잘못된 이름 및 경로 변형 거부를 확인했다. 이는 SAS 실행 시험이
아니다. 최신 main을 Pull한 후 위 ZIP 생성 두 줄을 다시 실행해 서버 결과를 확인한다.

## 최종 반환 ZIP 검수 결과

최종 완료 표식·단계별 로그·재출력 집계 대조·그래프 검수를 마쳤다. 반환된 집계
실행은 완료로 확인했으며 추가 재실행은 필요하지 않다. 이 결과가 앞선 대기 안내를
대체한다. U5 HTML의 이미지가 서버 절대경로를 가리키는 문제는 로컬 열람본에서
상대경로로 수정했다. 향후 실행 소스에도 GPATH의 URL=NONE 옵션을 추가했으며
수치 계산 로직·입력 CSV·PNG 이미지는 바꾸지 않았다. 변경한 경로 옵션 자체의
SAS 서버 재실행은 아직 하지 않았다.
