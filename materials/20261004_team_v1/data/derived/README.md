# 재계산 CSV

- `one_example.csv`: 단일 DUP 조건의 support별·업데이트별 회복·유지·정상 경고.
- `all_models_one_example.csv`: 모든 모델·support·업데이트 조건. support_was_missed는 해당 모델의 기존 오답 여부.
- `few_example.csv`: 모델·학습 묶음·업데이트별 값. common_*는 고정 공통 미탐 부분집합, recovered/miss_denominator는 해당 모델의 전체 평가 미탐 회복.
- `summary.json`: 같은 정본에서 재계산한 핵심 결론과 분모.

`clean_recovery`는 회복이 있으면서 새 미탐과 새 정상 경고가 없는 관측이다. 이 조건만으로 학습 support를 성공적으로 배웠다는 뜻은 아니다. support_detected와 원래 오답 여부를 함께 봐야 한다. folds/groups의 관측은 사례를 반복 사용한 것이며 고유 문자 수가 아니다. 불리언은 CSV에서 True/False 문자열이다.

현재 CSV를 SAS에서 import하면 임의 열 타입 추정이 필요하다. 모델/그룹/불리언 문자는 character로 읽고 미탐 분모와 업데이트 수는 numeric로 확인한다. 재계산 명령은 `python3 scripts/reproduce_public.py`다. 새 추론이나 추가학습이 아니다.
