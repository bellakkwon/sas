# 데이터 보관·사용 역할 안내

정리 기준일: 2026-09-20, 후속 사용 이력 반영: 2026-09-21. 신규 반입 자료는 기존 학습·검증·시험 데이터에 합치지 않았다.
행별 원문·식별자·점수와 전체 파일 목록은 비공개 보관소에 유지한다.

## 데이터별 위치와 역할

| 자료 | 현재 위치 | 역할·사용 경계 |
|---|---|---|
| 기본 한국어 문자 코퍼스 | `data/raw/kor_smishing_message.csv` | 원 라벨·출처 보존. `explanation`은 모델 입력 금지. 이용 조건·생성 방식은 출처 메타데이터를 함께 확인 |
| 고정 분할 | `data/processed/messages_split.csv` | 기존 train/validation/test. 중복 그룹·이전 사용 이력을 보존 |
| 기존 합성 증강판 | `data/processed/messages_split_augmented.csv` | 기존 증강 실행 결과. 새 반입 자료가 자동 포함되지 않음 |
| 반사실·변형 자료 | `data/processed/messages_split_counterfactual.csv`, `data/research/` | 원문과 파생본의 연결·실험 역할을 유지. 새 독립 시험 자료와 구분 |
| 기존 KR-MOB v2 | `data/raw/kr_mob_smishing_v2/`, `data/processed/kr_mob_smishing_v2_messages.csv` | 기존에 처리한 합성 계열. 신규 v1과 다른 버전이며 일부 정규화 문구 공유 |
| 기존 KISA 처리본 | `data/processed/kisa_smishing_external.csv` | 과거 외부 코퍼스. 새 월별 ZIP과의 중복 비교 기준 중 하나 |
| 새 KISA 월별 ZIP | 비공개 `external_intake_20260920_v1/kisa/` | 원본·추출 CSV·문자별 중복 판정 보관. 후속 고정 평가는 `external_eval_20260921_v1/`에 별도 보관; [결과](EXTERNAL_KISA_EVALUATION_20260921.md) |
| 새 AI Hub KR-MOB v1 | 비공개 `external_intake_20260920_v1/synthetic_aihub71983/` | 원본·추출 JSON/문서·문자별 비교 보관. 합성 자료이며 실제 스미싱 평가를 대체하지 않음 |
| URL 원자료 | `data/raw/`의 PhiUSIIL·OpenPhish·PhishTank·Tranco 자료 | 로컬 문자열 분석만 허용. 출처·시점·라이선스를 파일별로 확인; 실제 접속 금지 |
| SAS 입력 | `data/processed/sas/`, `data/processed/sas_oof/` | 코드·실행판에 맞는 버전 고정 입력을 사용 |
| 안전한 형식 예시 | `data/samples/` | 예시·형식 확인용. 실제 탐지 성능 근거가 아님 |
| 개별 예측·AI 검토·실험 응답 | 프로젝트 밖 `scamlens_private/` | 재현·검수용 비공개 기록. 공개 집계와 분리 |
| 기존 정상 후보 | `data/interim/realistic_normal_review_candidates.csv`; 비공개 `normal_review_20260921_v1/` | 원 라벨·사람 검수 상태 보존. [별도 AI 본문 검수](NORMAL_CANDIDATE_REVIEW_20260921.md)는 개발용이며 독립 정상 평가 자료가 아님 |

새 자료의 실제 크기·날짜 범위·중복 판정은 [반입 집계 정본](../../data/aggregates/external_intake_index_20260920.json)과
읽기 안내 (원 작업공간 경로: `EXTERNAL_DATA_INTAKE_20260920.md`)를 따른다. 기존 자료의 계보는
[데이터 계보](DATA_LINEAGE.md), [학습 데이터 현황](TRAINING_DATA_STATUS.md),
기존 데이터 설명 (원 작업공간 경로: `../data/README.md`)을 함께 확인한다.

## 비공개 보관소에서 먼저 볼 폴더

| 폴더 | 보존 대상 |
|---|---|
| `external_intake_20260920_v1/` | 신규 자료 원본, 완전·근사 중복 감사, 메인 검산, 최종 수령 검사 기록 |
| `external_eval_20260921_v1/` | 고정 평가 입력·예측·미탐 검토·메인 검산·실행 기록. 수령 감사와 구분 |
| `kisa_ocr_diagnostics_20260921_v1/` | 고정 OCR 구간·변형 입력·토큰 계보·모델별 예측·실행 receipt·메인 재현 검사. 기존 KISA와 정상 후보를 재사용한 진단 |
| `normal_review_20260921_v1/` | 점수 제외 검수 입력·문자별 AI 근거·메인 보완·수락 기록. 제안 초안은 정본과 구분 |
| `u5_label_review_20260920_v2/` | 확장된 직접 AI 라벨 검토. 이전 v1은 별도 보존 |
| `u5_cause_audit_20260920_v1/` | 기존 U5 자료 재사용 대조 실험 및 개별 결과 |
| `jev_kcbert_comparison_20260920_v2/` | Jev 판정 비교의 비공개 실행 기록 |
| `jev_kcbert_fusion_20260920_v1/` | 결합 탐색의 고정 입력·응답·점수·실행 기록 |
| `local_kcbert_20260917_v1/`, `local_kcbert_u5_20260918_v1/` | 로컬 학습·추론 재현에 필요한 비공개 산출물 |
| `organization_20260920_v1/` | 이번 정리의 전체 파일 메타데이터 목록·작업 기록 |

다른 비공개 폴더도 삭제하지 않았다. `pre_*`, `unapproved_draft*`는 복구·초안 이력으로
보존하고, 정본 분석에 섞지 않는다. Downloads의 원본 다운로드 파일도 그대로 유지한다.

## 이후 데이터를 사용할 때

1. 목적을 학습·임계값 결정·독립 평가·기존 오류 진단 중 하나로 정한다.
2. 출처·이용 조건·실제/합성 여부와 원본 날짜의 의미를 확인한다.
3. 기존 자료 및 새 자료 내부의 중복 그룹과 라벨을 검토한다. 유사도 기준 통과만으로 독립성을 확정하지 않는다.
4. 독립 평가에 사용할 자료는 모델·규칙·임계값 변경에 사용하지 않는다.
5. 분류 모델을 고정한 뒤 해당 프로토콜로 평가한다. 스미싱만 있는 자료로 정상 문자 오탐률을 계산하지 않는다.

정리용 파일 목록은 경로·크기·수정 시각을 기록한 메타데이터 스냅샷이다. 원본 내용 무결성은
각 실험과 반입 폴더의 별도 해시 매니페스트·검사 스크립트로 확인한다.
