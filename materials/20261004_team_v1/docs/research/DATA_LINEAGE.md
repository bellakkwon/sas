# 데이터 계보 — 라이선스·실제성·검수 상태

문서 유형: 데이터 준비 단계 산출물 · 자동 생성 · 수치는 저장소 파일에서 다시 센다

생성일: 2026-08-31 · 네트워크 접속: False

이 표가 데이터 인벤토리 (원 작업공간 경로: `DATA_INVENTORY.md`)의 원본 품질 감사와 다른 점: 여기는
**지금 디스크에 있는 모든 배치**의 사용 가능 범위다. 인벤토리 문서의 분할 행 수는
분할 결함 수정 이전 값일 수 있으므로 인용하지 않는다.

---

## 1. 사람 작업이 잠그고 있는 것

기계가 채울 수 없는 게이트다. 아래가 비어 있으면 해당 주장을 하지 않는다.

| 게이트 | 현재 | 막고 있는 주장 | 필요한 일 |
|---|---|---|---|
| hard_negative_review | **해소됨** · 판정 389/389 · 검수자 3인 · kappa 0.7287 | 분석 질문 4 — 카테고리별 FPR | — |
| official_procedure_verification | verified 0/10 | 여정 모순 근거와 Evidence RAG | 사람 2인이 source_checked를 verified로 승격 |
| consented_normal_sms | 미확보 | 현실 정상 문자 외부 FPR | 동의 기반 실제 정상 문자 100건 이상 |
| agency_impersonation_eval | 테스트 0건 (분포 보고서) | 선언한 첫 타깃(기관사칭) Recall | 학습과 분리된 기관사칭 평가 전용 100건 |
| real_attack_journeys | 정상 여정 4497건 pending, 실제 공격 여정 0건 | 다음 피해 행동 성능 주장 | 검수된 실제 공격 여정. 합성 시연 2건은 해당 없음 |

---

## 2. 배치 총괄

13/17개 배치가 디스크에 있다. 미확보: `consented_sms`, `iscx_url2016`, `cic_trap4phish_url_strings`, `voice_phishing_transcripts`

| source_id | 이름 | 파일 | 규모 | 라이선스 | 수집일 | 실제/합성 | 권리 | 검수 | 학습 | 평가 | 평가 범위 |
|---|---|---|---:|---|---|---|---|---|---|---|---|
| `kor_smishing_message` | jmjmjm3/kor-smishing-message | 있음 | 16,773 message | CC BY-NC-SA 4.0 | 2026-07-30 | unknown | yes | n/a | yes | yes | internal_holdout |
| `kisa_ctas_smishing` | KISA C-TAS yearly smishing export | 있음 | 5,430 message | agency_export_not_for_redistribution | 2026-08-01 | real | yes | n/a | no | yes | external_malicious_only |
| `kr_mob_smishing_v2` | DimensionV/KR-MOB-SMISHING-v2 | 있음 | 109 message | CC BY-NC 4.0 | 2026-07-31 | synthetic | yes | n/a | yes | no | none |
| `url_free_malicious_audit` | URL-free malicious slice of kor-smishing-message | 있음 | 380 message | CC BY-NC-SA 4.0 | 2026-08-01 | unknown | yes | n/a | no | yes | internal_slice |
| `hard_negative_review_packet` | Hard Negative blind review packet | 있음 | 389 review_row | mixed_public_corpus_and_disaster_alerts | 2026-08-20 | mixed | partial | verified | no | yes | gated_on_human_review |
| `realistic_normal_candidates` | Mined realistic-normal candidates from the public corpus | 있음 | 250 message | CC BY-NC-SA 4.0 | 2026-08-01 | unknown | yes | pending | no | no | development_only |
| `disaster_alerts` | safetydata.go.kr emergency alerts | 있음 | 47,555 message | public_data_api | 2026-08-01 | real | yes | pending | no | no | gated_on_human_review |
| `consented_sms` | Consented real normal SMS | **없음** | 0 message | consent_required | — | real | no | missing | no | no | not_collected |
| `phiusiil_lexical` | UCI PhiUSIIL (recomputed lexical features only) | 있음 | 235,370 url | CC BY 4.0 | 2026-07-30 | unknown | yes | n/a | yes | yes | url_lexical_holdout |
| `external_url_feeds` | PhishTank + OpenPhish + Tranco lexical snapshot | 있음 | 117,069 url | mixed_feed_terms | 2026-07-30 | real | partial | n/a | no | yes | url_external |
| `iscx_url2016` | UNB ISCX-URL2016 benign path URLs | **없음** | 0 url | cic_form_required | — | real | no | missing | no | no | not_collected |
| `cic_trap4phish_url_strings` | CIC-Trap4Phish 2025 URL Strings subset | **없음** | 0 url | cic_form_required | — | mixed | no | missing | no | no | not_collected |
| `aihub_normal_journeys` | AI Hub financial counselling → normal journeys | 있음 | 4,497 journey | aihub_terms_no_redistribution | 2026-08-01 | real | yes | pending | no | no | gated_on_human_review |
| `synthetic_scam_journeys` | Synthetic court-impersonation journey samples | 있음 | 2 journey | project_synthetic | 2026-08-01 | synthetic | yes | verified | no | no | demo_only |
| `official_procedures` | Official institution procedure registry | 있음 | 10 procedure | official_public_notice_reference_only | 2026-08-01 | real | partial | source_checked | no | no | gated_on_human_review |
| `voice_phishing_transcripts` | Permitted voice-phishing transcripts | **없음** | 0 transcript | consent_or_institutional_agreement_required | — | real | no | missing | no | no | not_collected |
| `synthetic_hard_negative_samples` | Checked-in synthetic hard-negative samples | 있음 | 5 message | project_synthetic | 2026-07-31 | synthetic | yes | verified | no | no | none |

학습에 쓸 수 있는 배치: `kor_smishing_message`, `kr_mob_smishing_v2`, `phiusiil_lexical`

평가에 쓸 수 있는 배치: `kor_smishing_message`, `kisa_ctas_smishing`, `url_free_malicious_audit`, `hard_negative_review_packet`, `phiusiil_lexical`, `external_url_feeds`

`eligible_for_evaluation=yes` 는 “실서비스 성능을 말해도 된다”가 아니다. 내부
홀드아웃과 외부 악성 전용 평가가 여기 포함된다. Hard Negative FPR과 여정 성능은
사람 게이트가 열린 뒤에만 해당 열이 yes 가 된다.

---

## 3. 배치 상세

### `kor_smishing_message`

- 파일: `data/processed/messages_split.csv` (10,984,375 bytes)
- SHA-256: `2451b94b6918e4362f1fb03fa7ba99d60297e3e9b63e16e24c03d952859551f4`
- 의도된 용도: text-model training and internal evaluation
- 금지: real-world FPR; treat as verified live SMS
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `label`: normal 11812, smishing 4961
  - `split`: train 12100, validation 2356, test 2317
  - `real_or_synthetic`: unknown 16773
  - `source`: jmjmjm3/kor-smishing-message 16773

### `kisa_ctas_smishing`

- 파일: `data/processed/kisa_smishing_external.csv` (3,202,930 bytes)
- SHA-256: `581c7a54127d84dbf32b4d0291e1d1a7e0bb96b87073dd567bd85be0b145b55a`
- 의도된 용도: external recall by year and type
- 금지: merge into training; measure false positives (no normals)
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `label`: smishing 5430
  - `real_or_synthetic`: real 5430
  - `source`: KISA C-TAS smishing export 5430
  - `attack_type`: 택배 3019, 공공기관 2226, 기타 150, 지인 14, 금융(결제) 9, 유해사이트 5, 구글폼 4, 결제 1

### `kr_mob_smishing_v2`

- 파일: `data/processed/kr_mob_smishing_v2_messages.csv` (69,322 bytes)
- SHA-256: `bad538eb8b7661cb6cf214d6741ff3d1bfe906ba4cae527267bad067a3ffd163`
- 의도된 용도: train-only synthetic augmentation
- 금지: real FPR; held-out evaluation
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `label`: smishing 76, normal 33
  - `split`: train 109
  - `real_or_synthetic`: synthetic 109
  - `source`: DimensionV/KR-MOB-SMISHING-v2 109

### `url_free_malicious_audit`

- 파일: `data/processed/url_free_malicious_categories.csv` (358,157 bytes)
- SHA-256: `fe4744e3c989c27a14fc8d5a2f7068ab0df45c9cbb802db47982209c5723e1f3`
- 의도된 용도: attack-type coverage audit
- 금지: treat the average miss rate as one attack type
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `split`: train 278, test 54, validation 48
  - `attack_type`: loan_ad 205, messenger_phishing 81, other 39, payment_impersonation 38, job_scam 13, agency_impersonation 3, adult_bait 1

### `hard_negative_review_packet`

- 파일: `data/interim/hard_negative_review_packet_reviewer_a.csv` (238,197 bytes)
- SHA-256: `51ff1cff4ae17bf63e156e21ac9630f1e44ac74c72496d7ef2e191316179604f`
- 의도된 용도: category-wise false-positive evaluation after dual review
- 금지: report FPR before verdicts; show model scores to reviewers
- 채워진 판정: 389/389
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `source_pool`: mined_normal 250, disaster_alert 139
  - `message_category`: public_service 189, account_security 50, banking_auth 50, card_payment 50, delivery 50
  - `verdict`: <empty> 389

### `realistic_normal_candidates`

- 파일: `data/interim/realistic_normal_review_candidates.csv` (454,505 bytes)
- SHA-256: `a429f382ec6f499c30c572457970eaf9e92b1ba8a6055b40c5ccdc7dd5992b99`
- 의도된 용도: development review practice; not independent FPR
- 금지: claim 250 real normal messages; external FPR
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `real_or_synthetic`: unknown 250
  - `review_status`: pending 250
  - `eligible_for_evaluation`: 0 250
  - `source`: jmjmjm3/kor-smishing-message 250
  - `message_category`: account_security 50, banking_auth 50, card_payment 50, delivery 50, public_service 50

### `disaster_alerts`

- 파일: `data/interim/disaster_message_candidates.csv` (30,084,262 bytes)
- SHA-256: `2e2ec35231ac9b2ad9c3cf2bd06b52b9475640c27ad5cbcf3c35336b18ec1228`
- 의도된 용도: public_service hard-negative candidates
- 금지: evaluate before dual review; missing-person alerts without a retention decision
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `label`: normal 47555
  - `real_or_synthetic`: real 47555
  - `review_status`: pending 47555
  - `source`: safetydata.go.kr 긴급재난문자 API 47555
  - `message_category`: public_service 47555

### `consented_sms` — 미확보

- 의도된 용도: external realistic-normal FPR
- 금지: commit raw donated text
- 기대 경로: `data/interim/consented_sms_candidates.csv`

### `phiusiil_lexical`

- 파일: `data/processed/phiusiil_lexical_features.csv` (22,840,126 bytes)
- SHA-256: `29265cb777490e7e5154cb4d70ee33e6368613678a50550af0698381a95552b0`
- 의도된 용도: URL lexical model training
- 금지: webpage-source features; live URL fetch
- 잔존 식별자 행(원문 미수록): n/a
- 관측 분포:
  - `label`: 0 134850, 1 100520

### `external_url_feeds`

- 파일: `data/processed/external_url_features.csv` (19,611,689 bytes)
- SHA-256: `82a44f6728fcb2d7eb044a2696faa6d5af6f59d0be8e28c5535a0687f4ca38a3`
- 의도된 용도: external URL-model evaluation; OpenPhish is not redistributable
- 금지: final URL ML verdict; redistribute OpenPhish raw URLs
- 잔존 식별자 행(원문 미수록): n/a
- 관측 분포:
  - `label`: 1 67069, 0 50000
  - `source`: phishtank_verified_online 66769, tranco_weak_benign 50000, openphish_community 244, openphish_community|phishtank_verified_online 56

### `iscx_url2016` — 미확보

- 의도된 용도: URL-model evaluation on benign URLs that have paths
- 금지: auto-submit the CIC identity form; unofficial mirrors
- 기대 경로: `data/processed/iscx_url2016_lexical.csv`

### `cic_trap4phish_url_strings` — 미확보

- 의도된 용도: URL-string-only auxiliary evaluation, if separable from documents
- 금지: download Word/Excel/PDF/HTML/QR; auto-submit identity form
- 기대 경로: `data/processed/cic_trap4phish_url_strings.csv`

### `aihub_normal_journeys`

- 파일: `data/interim/aihub_normal_journeys.jsonl` (48,931,408 bytes)
- SHA-256: `290d1029665b0db827d5002ab4f064d08ddb24dd88ffb35847aa9a53b5480464`
- 의도된 용도: normal journey contrast after dual review
- 금지: text-classifier training (call transcripts, not SMS); evaluate while pending
- 잔존 식별자 행(원문 미수록): n/a
- 관측 분포:
  - `real_or_synthetic`: real 4497
  - `review_status`: pending 4497
  - `journey_label`: normal 4497
  - `requested_action`: none 88187

### `synthetic_scam_journeys`

- 파일: `data/samples/scam_journeys.jsonl` (6,091 bytes)
- SHA-256: `46e2d95dfbd12f091b2ea6ac89f99316e9a3dc00b20b00a93c9fcd8bbe114b9c`
- 의도된 용도: schema validation and dashboard demo
- 금지: performance claims; human-agreement statistics
- 잔존 식별자 행(원문 미수록): n/a
- 관측 분포:
  - `real_or_synthetic`: synthetic 2
  - `review_status`: verified 2
  - `journey_label`: normal 1, scam 1
  - `requested_action`: none 4, official_verification 2, app_install 1, channel_switch 1, fund_transfer 1, link_open 1

### `official_procedures`

- 파일: `config/official_procedures.json` (14,852 bytes)
- SHA-256: `9111067a1c9960becf465e655cc199a2713a8dad868f5dd6eeeac3fe6986b802`
- 의도된 용도: contradiction evidence after two human reviewers promote to verified
- 금지: confirmed procedure evidence while source_checked
- 잔존 식별자 행(원문 미수록): n/a
- 관측 분포:
  - `review_status`: source_checked 10
  - `institution_id`: supreme_court 4, financial_services_commission 2, joint_government 2, national_police_agency 2

### `voice_phishing_transcripts` — 미확보

- 의도된 용도: voice-channel journey events
- 금지: commit raw audio or unmasked transcripts
- 기대 경로: `data/interim/voice_phishing_transcripts.jsonl`

### `synthetic_hard_negative_samples`

- 파일: `data/processed/hard_negative_messages.csv` (1,707 bytes)
- SHA-256: `2526f6e4b8ff9c1cc88b4e7fcf3c1d981c2062d709b55ce10adcf4932bc4cfaf`
- 의도된 용도: pipeline smoke tests
- 금지: FPR numerator
- 잔존 식별자 행(원문 미수록): active_url=0, phone=0, email=0, resident_number=0
- 관측 분포:
  - `label`: normal 5
  - `real_or_synthetic`: synthetic 5
  - `review_status`: verified 5
  - `eligible_for_evaluation`: 0 5
  - `source`: scamlens_synthetic_sample 5
  - `message_category`: account_security 1, banking_auth 1, card_payment 1, delivery 1, public_service 1

---

## 4. 사용 규칙

- 출처·라이선스가 없는 배치는 식별만 하고 학습에 넣지 않는다.
- `real_or_synthetic=unknown` 인 공개 코퍼스의 점수를 실제 문자 로그 성능으로 말하지 않는다.
- `review_status=pending` 인 행은 평가 집계에서 제외한다.
- 원본 민감정보와 동의 증빙은 저장소 밖에 둔다.
- 이 문서는 메시지 원문을 포함하지 않는다.

## 재현

```bash
PYTHONPATH=src python3 scripts/audit_data_lineage.py
PYTHONPATH=src python3 scripts/audit_data_lineage.py --check
```
