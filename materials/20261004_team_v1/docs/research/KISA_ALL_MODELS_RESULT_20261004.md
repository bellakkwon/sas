# 기존 전체 모델의 한 건 추가학습 검증

## 결과와 판단

저장된 263개 조건에서 한 건씩 추가학습하거나 그 결과를 결합해 검증했다. 사전에 고정한 10회 업데이트 기준, 회복이 있으면서 새 오류가 없는 결과는 1/2367개 관측이다. 그중 학습에 쓴 사례를 해당 모델도 원래 놓쳤던 경우는 0/1218개 관측이다.

9가지 학습 사례 선택과 여러 시드·모델을 같은 자료에서 비교한 탐색 실험이다. 일부 개선 관측을 배포 모델 선정의 근거로 삼지 않고 기존 모델을 보존한다. 알려진 오류 한 건만 반복 학습했을 때의 회복과 정상 후보 오탐 변화를 확인한 결과로 해석한다.

## 실행 범위

저장된 KcBERT 27개 체크포인트와 선형·결합 236개 조건을 검증했다. 같은 9건을 각각 한 건씩 골라 원본에서 새로 시작했다. 시드·fold·과거 삭제/가중 변형을 포함한 조건 수이며 서로 다른 구조의 모델 수가 아니다.

- 학습 사례는 기존 DUP seed42가 놓친 K01~K09다. 다른 모델은 이 사례를 원래 탐지할 수 있으므로 각 모델의 학습 전 판정을 별도로 기록했다.
- 학습에 쓴 한 건을 제외한 공통 여덟 건과, 해당 모델이 다른 KISA 사례에서 놓쳤던 사례들의 회복을 각각 계산했다. 같은 특징으로 인코딩된 학습 사례의 복제는 해당 평가에서 제외했다.
- 원래 임계값과 전처리를 고정했다. KcBERT는 AdamW 0.00002, 선형 모델은 SGD 0.1로 10회 업데이트했다. 1·5회는 변화 경로를 보여 주는 보조 결과이며, 결과를 보고 최종 업데이트 수를 고르지 않았다.
- 결합 학습 모델은 기존 전문가를 고정한 채 결합 계수만 학습했다. 고정·동일 가중 결합은 별도로 적응시킨 문자 전문가를 조합했고 URL 전문가는 고정했다.
- 정상 후보 250건은 원 데이터의 정상 라벨을 사용한 개발 자료(train 199, validation 51)다. 독립적으로 확인한 정상 모집단이나 실제 서비스 오탐률이 아니다.
- TF-IDF는 정규화 문자 전체, KcBERT는 기존 128토큰 범위를 사용한다. 입력 범위와 추가학습 방식이 달라 구조 자체의 우열로 해석할 수 없다.

## 최종 업데이트 10회 결과

| 계열 | 조건 수 | KISA 탐지 전 /22 | 정상 경보 전 /250 | 나머지8 탐지 후 | 정상 경보 후 /250 | 회복 있고 새 오류 없는 반복 |
|---|---:|---:|---:|---:|---:|---:|
| kcbert | 1 | 13 | 8 | 8 | 236–243 | 0/9 |
| kcbert_cf | 1 | 13 | 5 | 8 | 150–212 | 0/9 |
| kcbert_A | 5 | 13–14 | 14–22 | 8 | 241–247 | 0/45 |
| kcbert_C | 5 | 13–18 | 16–27 | 8 | 242–248 | 0/45 |
| u5_BASE | 5 | 13 | 7–22 | 8 | 242–247 | 0/45 |
| u5_DUP | 5 | 13 | 7–19 | 8 | 235–246 | 0/45 |
| u5_FLIP | 5 | 13–15 | 8–21 | 8 | 241–247 | 0/45 |
| word_tfidf_lr | 1 | 22 | 11 | 8 | 15–25 | 0/9 |
| char_tfidf_lr | 1 | 18 | 11 | 8 | 17–23 | 0/9 |
| char_tfidf_url_neutral_lr | 1 | 17 | 26 | 8 | 54–72 | 0/9 |
| word_tfidf_lr_cf | 1 | 22 | 24 | 8 | 27–45 | 0/9 |
| char_tfidf_lr_cf | 1 | 20 | 22 | 8 | 39–46 | 0/9 |
| char_tfidf_url_neutral_lr_cf | 1 | 13 | 16 | 8 | 28–35 | 0/9 |
| LR_A | 15 | 13–22 | 7–32 | 4–8 | 10–89 | 0/135 |
| LR_B | 15 | 12–22 | 10–34 | 4–8 | 16–87 | 0/135 |
| LR_C | 15 | 13–22 | 9–29 | 4–8 | 12–96 | 0/135 |
| deletion_A_keep | 15 | 13–22 | 7–32 | 4–8 | 10–89 | 0/135 |
| deletion_A_half | 15 | 13–22 | 7–32 | 4–8 | 10–93 | 0/135 |
| deletion_A_target_delete | 15 | 13–22 | 5–34 | 4–8 | 9–96 | 0/135 |
| deletion_A_matched_delete | 15 | 13–22 | 7–32 | 4–8 | 10–90 | 0/135 |
| deletion_C_keep | 15 | 13–22 | 9–29 | 4–8 | 12–96 | 0/135 |
| deletion_C_half | 15 | 13–22 | 9–28 | 4–8 | 12–94 | 0/135 |
| deletion_C_target_delete | 15 | 13–22 | 5–31 | 4–8 | 11–95 | 0/135 |
| deletion_C_matched_delete | 15 | 13–22 | 5–32 | 4–8 | 11–98 | 0/135 |
| word_expert | 5 | 12–22 | 6–17 | 4–8 | 8–44 | 0/45 |
| stacking | 5 | 13–18 | 14–15 | 0–8 | 23–48 | 0/45 |
| fage | 5 | 13–21 | 12–21 | 4–8 | 23–65 | 0/45 |
| fage_no_has_url | 5 | 13–22 | 12–21 | 1–8 | 22–58 | 0/45 |
| fage_no_similarity | 5 | 13–20 | 13–24 | 0–8 | 24–100 | 0/45 |
| fage_no_lr_c | 5 | 13–20 | 12–20 | 0–8 | 19–87 | 0/45 |
| fage_no_kcbert | 5 | 13–22 | 10–21 | 4–8 | 11–49 | 1/45 |
| fage_no_url | 5 | 13–21 | 12–21 | 0–8 | 16–44 | 0/45 |
| fage_no_disagreement | 5 | 13–21 | 12–21 | 1–8 | 22–57 | 0/45 |
| fage_no_url_free_weight | 5 | 13–18 | 12–16 | 5–8 | 21–76 | 0/45 |
| equal_weight | 5 | 14–22 | 14–26 | 8 | 93–215 | 0/45 |
| fixed_weight | 5 | 14–22 | 14–27 | 8 | 87–184 | 0/45 |
| text_url_meta | 1 | 18 | 11 | 4–7 | 13–16 | 0/9 |
| text_url_fixed | 1 | 22 | 17 | 8 | 35–43 | 0/9 |
| jev_fusion_K | 1 | 13 | 8 | 0 | 8 | 0/9 |
| jev_fusion_KU | 1 | 13 | 10 | 0 | 38–40 | 0/9 |
| jev_rawK | 1 | 13 | 8 | 8 | 240–245 | 0/9 |

범위는 해당 계열의 모든 시드·fold와 9가지 학습 사례에 걸친 최솟값~최댓값이다. 나머지8 탐지에는 원래 탐지하던 문자도 포함된다. 회복은 학습 전 놓친 사례가 탐지로 바뀐 경우만 별도로 계산했다. 마지막 열은 미학습 사례 회복이 한 건 이상이면서 기존 탐지를 잃지 않고 새 정상 후보 경보도 없는 반복 수다. 전체 미탐 회복과는 구분한다.

## 새 오류 없이 회복한 개별 관측

- **fage_no_kcbert_s303, K07 학습**: 학습에 쓰지 않은 기존 미탐 7건 중 3건 회복, 기존 탐지 14건 중 14건 유지. 정상 후보 경보 11→11/250건, 새 경보 0건. 학습 사례를 이 모델은 원래 탐지했다. 따라서 이 모델 자신의 오답 한 건을 학습한 결과로 표현할 수 없다.

## 업데이트 횟수별 경과

| 업데이트 | 전체 관측 | 회복 있고 새 오류 없는 관측 | 해당 모델의 오답을 학습한 관측 중 같은 결과 | 오답 학습 성공 + 다른8 모두 탐지 + 새 오류 없음 |
|---|---:|---:|---:|---:|
| 1 | 2367 | 134 | 57/1218 | 0 |
| 5 | 2367 | 14 | 12/1218 | 0 |
| 10 | 2367 | 1 | 0/1218 | 0 |

## 중간 점검에서 확인한 개선 사례

**LR_C_s404_f1**는 문자 TF-IDF 선형 모델의 C 조건(URL 없는 스미싱 상대 가중치 증가), seed404·fold1이다. 학습 전 KISA 13/22건 탐지, 정상 후보 경보 9/250건이었다. 다음 표에 이 조건의 모든 학습 사례 선택 결과를 함께 제시한다.

| 학습 사례 | 1회 미학습 미탐 회복 | 1회 정상 경보 | 5회 미학습 미탐 회복 | 5회 정상 경보 | 10회 미학습 미탐 회복 | 10회 정상 경보 |
|---|---:|---:|---:|---:|---:|---:|
| K01 | 0/8 | 9 | 3/8 | 10 | 6/8 | 12 |
| K02 | 0/8 | 9 | 3/8 | 10 | 6/8 | 12 |
| K03 | 0/8 | 9 | 5/8 | 11 | 7/8 | 14 |
| K04 | 0/8 | 9 | 4/8 | 10 | 7/8 | 13 |
| K05 | 0/8 | 9 | 2/8 | 9 | 6/8 | 12 |
| K06 | 0/8 | 9 | 5/8 | 11 | 8/8 | 14 |
| K07 | 0/8 | 9 | 2/8 | 9 | 4/8 | 12 |
| K08 | 0/8 | 9 | 2/8 | 9 | 6/8 | 12 |
| K09 | 0/8 | 9 | 4/8 | 10 | 7/8 | 14 |

K05·K07·K08 중 한 건을 학습한 3개 반복의 5회 시점에서는 학습한 한 건도 정탐으로 바뀌었고, 학습하지 않은 미탐 8건 중 2건을 회복했다. 기존 탐지 13건을 모두 유지했고 정상 후보 경보는 9→9건이었다. 같은 반복의 10회 시점 경보는 12건으로 늘었다.

이 조건은 결과를 본 뒤 설명용으로 고른 탐색 사례다. 미리 정한 1·5·10회 점검 중 5회에서 개선을 관측했다는 뜻이며, 5회가 최적이라는 검증이나 이 조건의 우월성을 주장하지 않는다. 같은 모델·같은 사례에서 반복한 관측은 서로 독립적인 검증이 아니다. 별도 자료에서 검증하기 전에는 최종 모델로 채택하지 않는다.

## 조건별 결과와 한계

[신경망 상세](KISA_ALL_MODELS_NEURAL_RESULT_20261004.md), [선형·결합 상세](KISA_ALL_MODELS_LINEAR_RESULT_20261004.md), [전체 집계 JSON](../../data/aggregates/kisa_all_models_summary_20261004.json)에 1·5·10회와 모든 사례 선택 결과를 보존했다. 신경망 상세 표의 기존 열명 “무오류 완전 복구”는 해당 코드상 한 건 이상 회복을 뜻하므로, 본 통합 보고서의 정의와 수치를 해석 기준으로 사용한다.

## 실행하지 못한 모델 및 적용하지 않은 항목

- **Original KcBERT seed14-17**: Historical scratchpad weights absent; metric JSON only.
- **Matched 20260917 BASE/DUP/FLIP (15 runs) + two-track**: Predictions remain, original fitted weights absent; U5 successors tested separately.
- **JEV API / fusion KJ,KJU**: No local trainable JEV model or new-case JEV features; no external transmission performed.
- **URL HGB**: Saved tree ensemble has no one-example online update; fitting with replay is a different future protocol.
- **ONNX / temperature calibration**: Same source neural weights. Calibration is a postprocessing step without a separately recorded binary-adaptation threshold.
- **always normal / always malicious / URL-present rule**: Fixed rules cannot learn an additional example.
- **next action backoff**: Action prediction, not binary normal/smishing.
- **early URL-free pilot**: Original pilot predictions retained; persisted successor LR-A/B/C models were tested.

URL HGB의 원본 탐지는 KISA 22/22건이었다. URL이 있는 정상 후보 186건 중 161건에 경보가 있었고, URL 없는 64건은 판정 대상에서 제외했다. 추가학습 결과가 아니며 전체 정상 후보를 분모로 한 오탐률로 표시하지 않는다.

## 검증

저장된 추가학습 예측 1,931,472행, 7,101개 모델·학습사례·체크포인트 묶음을 별도 계산으로 검산했다. 원본과 의존 산출물 해시 437건을 확인했다.
선형 학습 224개 조건은 원래 전체 계수·절편으로부터 실제 SGD 업데이트를 별도로 재구성했다. 예측 1,645,056개 비교의 최대 확률 차이는 3.44e-15였다. 신경망은 저장된 예측을 검산했으며, 추가학습 가중치를 영구 보관하지 않았으므로 그 가중치를 다시 불러온 독립 추론 검증을 주장하지 않는다.

메인 검산 기록 (원 작업공간 경로: `../tmp/kisa_all_models_20261004/main_validation.json`), 독립 코드 검토 (원 작업공간 경로: `../tmp/kisa_all_models_20261004/code_review.md`), Orca 자원 정산 (원 작업공간 경로: `../tmp/kisa_all_models_20261004/orca_accounting.json`).

자동 검사에서 발견한 문자열 키 정렬 오류는 별도 검증기 수정 기록 (원 작업공간 경로: `../tmp/kisa_all_models_20261004/verifier_fix.md`)에 남겼다. 두 키 비교만 고쳤으며, 실험 코드·가중치·예측·분모·판정 기준은 그대로 유지했다.

## 실행 명령

```bash
python3 scripts/run_kisa_all_models_neural_20261004.py prepare
python3 tmp/kisa_all_models_20261004/run_neural_sweep.py
python3 scripts/run_kisa_all_models_linear_20261004.py prepare
python3 scripts/run_kisa_all_models_linear_20261004.py run
python3 scripts/verify_kisa_all_models_neural_20261004.py
python3 scripts/run_kisa_all_models_linear_20261004.py check
python3 tmp/kisa_all_models_20261004/verify_linear_updates.py
python3 tmp/kisa_all_models_20261004/verify_input_collisions.py
python3 tmp/kisa_all_models_20261004/verify_and_summarize.py
python3 scripts/harness/cli.py verify kisa-all-models-run-v2-20261004
python3 scripts/harness/cli.py status kisa-all-models-run-v2-20261004
```

실행 순서는 공통 입력·코드 검사 → 신경망 우선 6개 조건 → 해당 예측을 고정해 선형·결합 실행 → 나머지 신경망 완료 → 통합 검산이다. 위 명령은 사용한 진입점 기록이다. 기존 출력 폴더에서 실행하면 완료 결과를 검증·재사용하며 부분 결과나 입력 변경은 실패 처리한다. 독립 재실행은 별도 출력 경로와 새로 고정한 계획으로 수행해야 한다.

## 해석의 범위

- 같은 KISA 22건과 개발 정상 후보 250건에서 확인한 사후 진단이다. 새로운 독립 데이터에서의 일반화 성능이 아니다.
- 같은 사례를 시드와 학습 사례 선택만 바꿔 반복한 관측은 독립 표본이 아니다. 다수 비교에서 발견한 한 조건을 최종 모델로 채택하지 않았다.
- KISA 22건은 유사 문자 18그룹이다. 학습 사례 밖에는 앞 128토큰이 같은 입력도 있어 건별 결과를 독립 사건 수로 해석하지 않는다.
- URL 특징이 서로 다른 원천 후보가 같은 정규화 본문으로 합쳐진 사례가 3건 있다. 사전에 고정한 최소 audit_index 선택을 따랐다. URL에 접속하지 않았다.
- 다음 검증이 필요하다면 원래 정상·스미싱 자료를 섞는 재학습 조건을 먼저 고정하고, 별도의 신규 사례와 정상 자료로 평가해야 한다. 이번 실험에서는 이 후속 실험을 수행하지 않았다.
