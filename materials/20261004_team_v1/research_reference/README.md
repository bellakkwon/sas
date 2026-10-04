# 비공개 연구의 참고 코드와 고정 계획

공유판은 실제 사용한 실험 코드·계획의 참고 복사본이다. 개인 경로를 ${PROJECT_ROOT}, ${PRIVATE_ROOT}, ${LOCAL_PATH}로 치환했다. 원 입력·체크포인트·특징 모델·행별 대조군·전체 의존 코드가 공개되어 있지 않으므로 이 폴더만으로 원 실험을 재실행할 수 없다. 바로 실행 가능한 코드는 [python 폴더](../python/README.md)와 [공개 재계산 스크립트](../scripts/README.md)다.

| 단계 | 참고 실행기 | 고정 조건·의존 |
|---|---|---|
| 기본 모델·URL | `train_text_baselines.py`, `train_url_baseline.py` | 비공개 고정 분할/특징 |
| 증강·KcBERT | `prepare_*augmentation.py`, `run_matched_kcbert_*` | 원 학습판·동일 업데이트 수 |
| 고정 KISA·OCR | `evaluate_external_kisa_*`, `run_kisa_ocr_diagnostics_*` | 모델과 임계값 고정 |
| DUP 한 건 | `run_kisa_one_example_20261004.py prepare/run/check` | ONE_EXAMPLE_PLAN; 원본·입력·baseline 검증 |
| 전체 신경망 한 건 | `run_kisa_all_models_neural_20261004.py prepare/run/check` | NEURAL_PLAN; 원본 초기화 |
| 선형·결합 한 건 | `run_kisa_all_models_linear_20261004.py prepare/run/check` | LINEAR_PLAN; 신경망 대조군 선행 |
| 전체 한 건 검산 | `reviewers/all_models/` | 원 private 예측·가중치·영수증 필요 |
| 두·세 건 준비 | `kisa_few_example_common_20261004.prepare()` | 이전 한 건 결과 완결·해시 확인 |
| 두·세 건 신경망 | `run_kisa_few_example_neural_20261004.py run --model-id <id>` | 모델별 순차 실행, MPS 요구 |
| 두·세 건 선형 | `run_kisa_few_example_linear_20261004.py run` | 공통 준비와 기존 한 건 결과 |
| 두·세 건 집계 | `analyze_kisa_few_example_20261004.py --check`, reviewer | private 결과와 최종 집계 대조 |

torch/transformers·numpy·pandas·scipy·scikit-learn·joblib 등의 실제 버전은 비공개 실행 receipt를 따른다. 새 비공개 재현 환경은 설치 버전과 device를 기록하고 기존 출력 덮어쓰기 없이 사전 검증한다. 공개 경로 플레이스홀더를 그대로 실행하거나 원 해시 계약에 대입하지 않는다.

`docs/experiments/`는 기존 고정 실험 계획, `src/scamlens/`는 관련 특징 코드, `reviewers/`는 메인 검산 방법이다. 사용법과 경계는 [비공개 입력 안내](../docs/PRIVATE_INPUTS.md)를 먼저 읽는다. [SAS 최신 CSV 참고](sas/README.md)는 저장 집계 읽기만 수행한다.
