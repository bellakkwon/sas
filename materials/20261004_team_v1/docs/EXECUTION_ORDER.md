# 실행 순서

## 1. 공유 자료 받기

```sh
git clone https://github.com/kimchikingdom/sas.git
cd sas
```

이미 저장소가 있으면 작업 변경을 확인한 뒤 `git pull --ff-only origin main`을 실행한다. 실패하면 기존 변경을 보존하고 원인을 확인한다.

## 2. 자료 무결성과 결과 확인 — 공개 입력만 필요

```sh
python3 materials/20261004_team_v1/scripts/verify_bundle.py
python3 materials/20261004_team_v1/scripts/reproduce_public.py
python3 materials/20261004_team_v1/python/scripts/offline_demo.py
```

첫 명령은 파일 목록·SHA-256·문서 링크·공개 범위를 검사한다. 둘째는 저장된 추가학습 집계를 별도로 재계산하고 비교 CSV와 일치를 확인한다. 셋째는 합성 문자만 전처리한다. 세 단계 모두 외부 접속, 모델 다운로드, 실제 URL 접속 없이 실행한다. 추가 결과 사본이 필요하면 둘째 명령에 `--write`를 붙인다. 결과는 `outputs/recalculated/`에 저장한다.

## 3. 오프라인 코드의 합성 테스트

```sh
cd materials/20261004_team_v1/python
python3 -m venv .venv
. .venv/bin/activate
python -m pip install pytest
PYTHONPATH=src python -m pytest tests -q
```

테스트 통과는 전처리·URL 문자열·난독화 코드의 검사이며 실제 스미싱 탐지율의 증거가 아니다.

## 4. 기존 SAS 집계·시각화

저장소 루트로 돌아간다. SAS Studio 서버에 최신 저장소가 있어야 한다. 경로가 다르면 projroot를 변경한다.

```sas
%let projroot=/home/student/github;
%let sl_profile=PUBLIC;
%let sl_run_cas=0;
%include "&projroot./sas/00_RUN_ALL.sas";
```

CAS 게시가 필요하면 본인 권한을 확인한 뒤 `sl_run_cas=1`을 지정한다. 상세 설정은 [현재 RUNBOOK](https://github.com/kimchikingdom/sas/blob/main/sas/RUNBOOK.md)을 따른다. `outputs/run_<UUID>/run_status.csv`와 로그·HTML을 검사한다. 건너뜀과 RUNNING 종료를 완료로 기록하지 않는다. 10-04 추가학습은 Python에서 수행한 결과이며 기존 RUN_ALL이 재학습하지 않는다. 최신 CSV를 읽는 선택 SAS 코드는 [참고판](../research_reference/sas/README.md)이며 이번 공유에서 실제 SAS 실행은 하지 않았다.

## 5. 비공개 연구 재현 — 권리·입력 확보 후

[비공개 입력](PRIVATE_INPUTS.md)을 확보하고 [실험 참고판](../research_reference/README.md)과 각 고정 계획을 읽는다. 경로·계획·실행 코드를 복원한 새 비공개 작업공간에서 입력·원본 모델·임계값의 해시와 baseline replay를 먼저 확인한다. 공개 clone만으로 재학습할 수 없다. 원본의 출력 폴더를 재사용하거나 덮어쓰지 않는다.

실험 순서는 원 데이터 정리·유사 그룹 분할 → 기본 모델/URL 학습 → 동일 업데이트 증강 비교 → 고정 U5 평가 → KISA 고정 평가·OCR 진단 → 한 건 원본 초기화 실험 → 전체 모델 한 건 실험 → 한 건 대조군을 보존한 두·세 건 실험 → 집계 검산이다. 각 단계 결과가 검증된 후 다음 단계로 간다.

## 6. 발표와 기록

[발표자 대본](../presentation/SPEAKER_NOTES.md)을 Canva 실제 페이지 순서로 사용한다. 실험 변경은 별도 브랜치·새 날짜 판으로 만들고 입력·출력·실행 명령·검증·해석 범위를 기록한다. 기존 test를 본 뒤 임계값이나 업데이트 횟수를 다시 고르면 새 독립 평가가 필요하다.
