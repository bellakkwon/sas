# 집계 정본 JSON

| 파일 계열 | 역할 |
|---|---|
| `model_comparison.json` | 기존 문자 기준 모델 비교 |
| `matched_kcbert_u5_unused_*` | 고정 U5 증강 비교 및 개발/시험 결과 |
| `external_kisa_evaluation_*`, `kisa_ocr_diagnostics_*` | 고유 KISA·대표 부분집합·입력 진단 |
| `u5_error_diagnostics_*` | 조건·하위집단·전이 진단 |
| `jev_kcbert_*` | LLM 판정 대체·특징 결합, 서로 다른 평가 역할 |
| `kisa_one_example_*` | 단일 DUP의 한 건 추가학습 |
| `kisa_all_models_*` | 전체 저장 모델·파생 조건 한 건 진단 |
| `kisa_few_example_*` | 고정 두·세 건 조합과 같은 대상 대조군 |
| `training_augmentation_summary`, `counterfactual_augmentation` | 당시 증강 구성 |
| `url_baseline`, `external_intake_index_*`, `normal_candidate_review_*` | URL 기준선·반입 역할·정상 후보 검수 |

같은 자료를 여러 조건에서 재사용했으므로 서로 독립인 데이터셋으로 더하지 않는다. 정상 후보는 개발용이며 KISA 양성 자료만으로 정상 FPR을 계산하지 않는다. `kisa_few_example`의 조합은 전체 조합이 아닌 사전 고정 부분집합이다. JSON의 원 수치와 역할·한계 필드를 유지했다.
