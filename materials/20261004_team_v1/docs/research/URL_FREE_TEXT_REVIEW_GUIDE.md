# URL 없는 문자 본문 검수 안내

이 검수는 문자만 읽고 실제 사기 여부를 확정하는 절차가 아니다.
본문에서 관찰할 수 있는 요구와 맥락을 기록한다. 원래 데이터의 분류 정답은
보존하며, 결과를 학습에 반영하려면 별도 결정과 새 실험판이 필요하다.

## 검수자에게 주는 파일

`data/research/url_free_label_review_20260909/reviewer_a.json`과
`reviewer_b.json`을 서로 다른 검수자가 맡는다. 한 사람의 파일을 다른 사람이
미리 보지 않는다. 관리용 `private_key.json`, `heuristic_cues.json`,
`normal_matches.json`과 모델 예측 파일은 검수자에게 주지 않는다.

원래 정상과 악성 라벨이 섞여 있고 순서는 가려져 있다. 본문은 추가 마스킹한
복사본이므로 `#`나 `[연락수단]` 때문에 판단하기 어려우면 추측하지 않는다.
원자료를 외부에 공유하거나 URL·연락처에 접근하지 않는다. 개인정보가 남아
있다고 의심되면 해당 내용을 복사하지 말고 `privacy_issue`에 위치와 종류만 쓴다.

## 기록 항목

`reviewer_id`에는 실명이 아닌 구분용 별칭을, `reviewed_at`에는 검수일을 쓴다.
`text_judgment`에는 다음 중 하나를 고른다.

- `risky_request_visible`: 본문에 송금, 인증정보 전달, 원격 접근 등 위험한 요구가 보인다.
  요구가 보인다는 뜻이지 범죄나 발신자 사칭을 확인했다는 뜻은 아니다.
- `promotion_without_clear_scam_request`: 대출·일자리 등의 홍보가 보이지만 구체적인
  사기 요구를 본문만으로 확인하기 어렵다. 적법한 광고라는 판정도 아니다.
- `ordinary_notice_or_conversation_possible`: 정상 안내·개인 대화로도 해석할 수 있다.
- `insufficient_context`: 앞뒤 대화, 발신자 확인 또는 마스킹된 정보가 없으면 판단하기 어렵다.

`visible_actions`에는 `payment_or_transfer`, `credentials_or_verification`,
`app_or_remote_access`, `contact_channel_change`, `callback`, `none_visible`,
`unclear` 중 관찰되는 항목을 기록한다. 예방 안내나 부정문을 실제 요구로 세지 않는다.
인용·경고·조건부 설명인지도 `evidence_note`에 짧게 남긴다. 외부 주소나 연락처는 쓰지 않는다.

검수를 완료한 행만 `human_review_status`를 `completed`로 바꾼다.
`actual_scam_verified`는 반드시 `false`로 둔다. 본문 검수로 이를 승격할 수 없다.

## 비교와 해석

두 검수자의 판단과 행동 항목이 같으면 ‘본문 판단 일치’, 다르면 ‘합의 필요’로
남긴다. 같은 검수자가 두 파일을 작성한 경우 독립 검수로 인정하지 않는다.
사람 검수 완료율, 일치도, 판단 불가 비율을 보고하되 실제 사기 검증률로 바꾸지 않는다.
현재 양식은 준비 단계이며 사람이 검수한 결과가 아직 들어 있지 않다.

## 수합과 원문 보존 검사

응답 항목만 편집한다. `review_id`와 `text_for_local_review`는 바꾸지 않는다.
`none_visible` 또는 `unclear`는 다른 행동 선택과 함께 쓰지 않는다. 완료 행에는
검수자 별칭·날짜·근거 메모가 필요하다. 개인정보 의심 항목이 남아 있으면
완료 처리하지 않는다.

두 파일을 받은 관리자는 아래 절차로 본문·ID 불변성과 독립 검수 조건을 확인하고
본문이 없는 수합 상태만 갱신한다. 원본 라벨과 학습 자료는 변경되지 않는다.

```sh
PYTHONPATH=src python3 scripts/build_url_free_label_review.py --check
PYTHONPATH=src python3 scripts/merge_url_free_text_reviews.py
PYTHONPATH=src python3 scripts/merge_url_free_text_reviews.py --check
```

수합 결과는 `reports/generated/url_free_text_review_status_20260909.json`에 남는다.
두 사람이 모두 끝낸 행만 일치도 분모에 넣는다. 완료 쌍이 없거나 판단 범주가
하나뿐이라 kappa를 계산할 수 없으면 미산출 사유를 남긴다. 일치도는 정확도가 아니다.
