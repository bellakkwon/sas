# KcBERT U5 확증 프로토콜 — 2026-09-18

09-17 15조건은 개발 리드아웃을 본 탐색이다. U5는 그 점수를 다시 고르지 않는다.
원래 `messages_split`의 test를 한 번 읽는다. Two-track은 쓰지 않는다.

## 잠근 E

300쌍 중 검수 응답과 토큰 변화를 통과한 281쌍이 E다. 미통과 19쌍은 넣지 않는다.
URL 재확인 16건의 pair_id는 19쌍 안에 있고, 281에는 없다. 사람 재확인은
14건 본문 변화, 2건 판단 불가였다.

자연스러움 기준 `자연스러움`은 2026-09-16에 검수 반환을 본 뒤 적용됐다. 그
역사를 지우고 사전 등록인 척하지 않는다. 미사용 test를 보기 전에 그 기준과
281 목록을 고정한다.

정본: `reports/generated/matched_kcbert_u5_e_lock_20260918_v1.json`.

## 평가

- 임계값: 원래 train 안 `threshold_calibration`, 정상 FPR ≤ 1.0%.
- 1차: 원래 test. 유사도 그룹이 train과 겹치지 않는다. 매칭 입력에도 없다.
- 2차: 원래 validation. 이 저장소의 다른 모형이 쓴 분할이라 1차가 아니다.
- 개발 리드아웃은 학습이 도는지 보는 용도이며 U5 주장의 분모가 아니다.

test 문장은 `normalize_text(text_raw_masked)`다. train fit은 이름 토큰 검수
마스크를 한 번 더 썼다. 그 차이를 숨기지 않는다.

## 학습

09-17 가중치는 저장되지 않았다. 같은 281·같은 시드·같은 예산으로 다시 학습하고
가중치를 private 디렉터리에 남긴다. MPS라 09-17 탐색 가중치와 비트 단위로
같다고 보지 않는다. 출력은
`~/scamlens_private/local_kcbert_u5_20260918_v1/` (권한 700).

## 하지 않는 것

- test를 보고 E, 임계값, 게이팅을 다시 고른다
- Two-track
- 개발 리드아웃 우열로 U5를 채택한다
- 원문·가중치를 git에 넣는다

## 재현

```bash
python3 scripts/lock_matched_kcbert_e_u5_20260918.py
python3 scripts/prepare_matched_kcbert_unused_eval_20260918.py
python3 scripts/run_matched_kcbert_u5_20260918.py run --max-arms 15 --device mps
python3 scripts/run_matched_kcbert_u5_20260918.py check
```
