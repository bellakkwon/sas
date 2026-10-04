# ScamLens 팀 공유 자료 — 2026-10-04

모델 비교와 증강 평가, 실제 신고 사례의 오류 진단, 한·두·세 건 추가학습 결과 및 현재 발표를 한곳에서 확인한다. 알려진 오류의 사후 진단이며 미래 유형의 운영 성능이 검증된 결과가 아니다.

## 처음 받은 팀원

1. [프로젝트 요약과 결과](docs/RESULTS_SUMMARY.md)를 읽는다.
2. [전체 실행 순서](docs/EXECUTION_ORDER.md)에서 공개 자료 확인과 비공개 재학습을 구분한다.
3. [데이터 안내](data/README.md), [연구·공유 가이드라인](docs/GUIDELINES.md)을 확인한다.
4. [현재 발표](presentation/README.md)와 [페이지별 대본](presentation/SPEAKER_NOTES.md)을 확인한다.
5. 담당 작업과 생성물을 [팀원 체크리스트](docs/TEAM_CHECKLIST.md)에 따라 기록한다.

## 바로 실행 — 저장소 루트에서

```sh
python3 materials/20261004_team_v1/scripts/verify_bundle.py
python3 materials/20261004_team_v1/scripts/reproduce_public.py
python3 materials/20261004_team_v1/python/scripts/offline_demo.py
```

Python 3.10 이상에서 표준 라이브러리로 실행한다. 공개 결과 재계산과 합성 입력의 전처리 예시이며 모델 학습·추론이나 새 SAS 실행을 수행하지 않는다. 합성 테스트는 `python -m pip install pytest` 후 [Python 안내](python/README.md)에 따라 실행한다.

## 폴더 지도

| 폴더 | 내용 | 시작 파일 |
|---|---|---|
| `data/aggregates/` | 원문 없는 기존 평가·추가학습 전체 JSON | [집계 설명](data/aggregates/README.md) |
| `data/derived/` | 위 JSON에서 재계산한 비교 CSV·요약 | [CSV 열 설명](data/derived/README.md) |
| `data/samples/` | 합성 문자·Hard Negative·빈 반입 양식 | [예시 설명](data/samples/README.md) |
| `docs/` | 실행 순서·데이터 사용·팀 협업·결과 해석 | [문서 지도](docs/README.md) |
| `docs/research/` | 최신 보고서·데이터/모델/분할 카드 | [연구 문서](docs/research/README.md) |
| `presentation/` | 현재 Canva 링크·54장 본문·대본 | [발표 안내](presentation/README.md) |
| `python/` | 실행 가능한 오프라인 전처리와 합성 테스트 | [Python 실행](python/README.md) |
| `research_reference/` | 실제 실험 코드와 고정 계획의 공유용 참고판 | [비공개 재현 안내](research_reference/README.md) |
| `scripts/` | 무결성 검사·집계 재계산 | [스크립트 설명](scripts/README.md) |
| `outputs/` | 선택 재계산 결과, Git 제외 | 실행 시 생성 |

현재 SAS 서버 실행은 저장소 루트의 [sas/RUNBOOK.md](https://github.com/kimchikingdom/sas/blob/main/sas/RUNBOOK.md), [sas/00_RUN_ALL.sas](https://github.com/kimchikingdom/sas/blob/main/sas/00_RUN_ALL.sas)를 따른다. 이 파일들은 기존 실행의 진입점이며 추가학습을 실행하지 않는다. 10-04 추가학습 CSV를 SAS로 읽는 선택 예시는 [별도 안내](research_reference/sas/README.md)에 있다.

원문·원 URL 행·행별 점수·모델 가중치·기증 자료는 Git에 포함하지 않았다. 원 데이터별 권리·접근과 재현 조건은 [비공개 입력 안내](docs/PRIVATE_INPUTS.md), 소스 귀속은 [라이선스 안내](LICENSE_NOTICE.md)를 따른다. 집계 정본의 출처와 변환, 해시는 [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)과 [MANIFEST.json](MANIFEST.json)에 있다. 개인 경로를 치환한 연구 참고판은 원 실행과 바이트가 다르므로 원 실행의 무결성 검사를 대체하지 않는다.
