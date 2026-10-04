# 비공개 입력과 데이터 접근

공개 저장소에는 결과 집계와 합성 예시만 있다. 실제 원 데이터와 학습 모델은 권한 있는 팀원이 별도의 승인된 비공개 채널에서 받아야 한다. 이 문서는 데이터 업로드·배포 권한을 새로 부여하지 않는다.

| 입력 | 비공개 작업공간의 논리 경로 | 필요한 단계 |
|---|---|---|
| 원 한국어 코퍼스·출처/이용 조건 | `data/raw/kor_smishing_message.csv` | 기존 학습 재현 |
| 고정 분할·URL 대응표 | `data/processed/messages_split.csv`, `message_urls.csv` | 같은 분할 비교 |
| 고정 그룹/fold 및 전문가 모델 | `data/research/url_free_stability_20260909/`, `models/` | 선형·결합 재현 |
| KISA 입력·정상 후보 | `${PRIVATE_ROOT}/kisa_ocr_diagnostics_20260921_v1/` | 평가·추가학습 |
| 원 KcBERT 체크포인트·토크나이저 | `${PRIVATE_ROOT}/local_kcbert_u5_20260918_v1/` 등 | 원본 초기화 및 baseline replay |
| 기존 한 건 예측과 완결 영수증 | `${PRIVATE_ROOT}/kisa_all_models_*_20261004_v1/` | 두·세 건의 동일 대상 대조군 |
| SAS 본문·OOF·개별 점수 | 승인된 `data/processed/sas/` | PUBLIC 외의 기존 분석 |

반입 전에 출처·라이선스·수집일·실제/합성·동의 범위·해시·행 수·라벨·중복 그룹을 확인한다. KISA C-TAS 원문은 재배포 불가 기록을 따르며 공개 저장소에 넣지 않는다. 한국어 합성 계열의 비상업·공유 조건, URL 피드 조건은 [데이터 계보](research/DATA_LINEAGE.md)와 [소스 귀속](../LICENSE_NOTICE.md)을 읽고 공급처에서 확인한다.

현재 공유판의 ${PROJECT_ROOT}, ${PRIVATE_ROOT}, ${LOCAL_PATH}는 경로를 가린 문자열이다. 참고 코드를 그대로 실행할 수 있는 환경변수가 아니다. 비공개 실행판에서 실제 경로를 설정하고 새 해시 계약을 만든다. 원 실행의 해시를 수정한 코드에 재사용하지 않는다.
