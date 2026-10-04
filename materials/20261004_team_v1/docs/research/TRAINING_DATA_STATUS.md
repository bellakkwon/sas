# 학습 데이터 추가 확보 현황

확인일: 2026-07-31

## 이번에 실제로 추가한 데이터

라이선스가 확인된 `DimensionV/KR-MOB-SMISHING-v2`의 로컬 JSON 100개에서 SMS
표본만 추출했다. 외부 URL은 한 번도 접속하지 않았다.

| 항목 | 결과 |
|---|---:|
| 원본 SMS 표본 | 111 |
| URL 마스킹 후 제거된 중복 | 2 |
| 학습 가능 고유 문자 | 109 |
| 정상 | 33 |
| 스미싱 | 76 |
| 기존 정제 데이터 완전 중복 | 0 |
| 기존 validation/test 유사도 0.90 이상 | 0 |
| 기존 train | 12,312 |
| 증강 train | 12,421 |
| validation | 2,182, 변경 없음 |
| test | 2,282, 변경 없음 |

정제 과정에서 모든 `[TRAINING]` 워터마크를 제거하고 URL을 `[URL]`로 바꿨다.
전화번호·긴 숫자·활성 URL 잔존 검사는 모두 0건이다. 이 자료는 합성이므로 실제
환경 성능을 주장하는 평가셋으로 사용하지 않는다.

## 라벨 정책

- `benign` → `normal`
- `benign_lookalike` → `smishing`
- `malicious` → `smishing`

`benign_lookalike`는 이름과 달리 게시자가 “공격은 존재하지만 사용자가 중단한
경우”로 정의한다. 피해가 완료되지 않았어도 수신된 유인 문자는 스미싱이므로 문자
수준 라벨은 `smishing`으로 처리했다.

## 바로 사용할 파일

- `data/processed/kr_mob_smishing_v2_messages.csv`
- `data/processed/messages_split_augmented.csv`
- `reports/generated/training_augmentation_summary.json`

재생성:

```bash
python3 scripts/prepare_training_augmentation.py
```

## 아직 남은 실제 데이터 부족

이번 109건은 새 학습 행이지만 합성이다. 실제 한국어 정상 안내문자는 새로 들어오지
않았다. 따라서 다음 확보 순서는 아래와 같다.

1. 팀원·지인 동의를 받아 금융·택배·공공기관·인증·계정보안 정상 문자 각 20건,
   총 100건 이상을 수집한다.
2. `scripts/import_consented_sms.py`로 저장소 밖 원문을 즉시 비식별화한다.
3. 두 명이 정상 여부와 카테고리를 검수한 행만 학습 후보로 편입한다.
4. KISA 사이버보안 빅데이터센터에 연도별 실제 스미싱 데이터 이용을 신청한다.
5. AI Hub SNS 대화는 일상 대화 다양성 보조 실험으로만 검토하고 정상 안내문자를
   대신하게 하지 않는다.

현재 공개 웹에서 발견한 대량 한국어 문자 자료는 라이선스 미표시 또는 개인정보·활성
URL 위험 때문에 병합하지 않았다. 양보다 사용 권한과 라벨 신뢰도를 우선한다.
