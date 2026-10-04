# KcBERT Matched Control 실험 최종 총평 및 분석 보고서

- **작성일자**: 2026-09-17
- **실험 범위**: KcBERT Matched Control의 DUP·FLIP·BASE 조건과 전체 시드 결과
- **실행 환경**: 로컬 Mac (Apple MPS), URL 접속·리디렉션·본문 수집 없는 오프라인 실행
- **정본 집계**: `matched_kcbert_local_final_15arms_20260917_v1.json` (원 작업공간 경로: `../../reports/generated/matched_kcbert_local_final_15arms_20260917_v1.json`)
- **개인정보 안전 파생 산출물**: `matched_privacy_safe_20260917_v1.json` (원 작업공간 경로: `../../reports/generated/matched_privacy_safe_20260917_v1.json`)
- **분석 상태**: `completed_15_arms_checked`인 사후 탐색적 분석이며, 사전 승인된 확증 분석이 아님

---

## 1. 실험 배경 및 목표

본 방어 연구는 URL 표시가 포함된 정상 안내와 악성 문자에서 탐지 판단이 어떻게 달라지는지, URL 의존 가설을 통제된 편집 쌍으로 탐색하기 위해 수행했다. URL의 실제 접속이나 리디렉션 추적 없이 문자열 편집만 사용했으며, 결과는 이번 단일 코퍼스와 개발 평가 범위에 한정한다.

- **BASE**: 원본 `fit` 입력
- **DUP**: 원본 `fit`에 선택된 메시지의 원문을 추가
- **FLIP**: 같은 선택 메시지의 URL 편집문을 추가

FLIP은 라벨을 반전한 조건이 아니다. 실행 코드에서 DUP와 FLIP의 추가 행에 같은 원본 라벨을 배정한다([`run_matched_kcbert_portable_20260917.py` 345–362행](../../../research_reference/scripts/run_matched_kcbert_portable_20260917.py#L345-L362)). 따라서 명칭의 `FLIP`은 URL 문자열 편집을 가리키며, 정답 라벨 변경을 뜻하지 않는다.

## 2. 결과를 읽는 기준

중복 수치 표는 이 문서에 재작성하지 않는다. 시드 평균·표준편차, URL 유무별 개발 리드아웃, 시드별 상세값과 전이 집계는 `SCAMLENS_PROJECT_STATUS_20260917.md` (원 작업공간 경로: `../SCAMLENS_PROJECT_STATUS_20260917.md`)의 자동 생성 표와 원 JSON (원 작업공간 경로: `../../reports/generated/matched_kcbert_local_final_15arms_20260917_v1.json`)을 참조한다. 원 JSON의 `status`, `E_status`, `evaluation_role`, `arm_statistics`, `detailed_summaries`, `paired_totals_flip_minus_dup`가 집계의 기준이다.

입력 역할은 `fit`, `threshold_calibration`, `development_readout`으로 구분한다. 역할별 표본 수와 임계값 보정 기준은 현황 문서의 자동 생성 표와 원 JSON을 참조한다. 보정 역할에서 적용한 FPR 제한은 `development_readout`의 모든 조건·하위집단 FPR을 보장하는 조건이 아니다. `development_readout`은 독립 테스트가 아니므로, 이 결과만으로 외부 일반화 성능이나 배포 성능을 추정할 수 없다.

## 3. 쌍별 전이의 해석 범위

DUP와 FLIP의 판정 전이는 원 JSON의 `paired_totals_flip_minus_dup`와 현황 문서의 자동 생성 표로 확인한다. 시드 누적 전이는 같은 평가 메시지를 시드별로 반복해 센 **메시지-시드 판정 수**다. 따라서 이를 고유 메시지 수, 독립 표본 수, 독립 반복 실험 수로 해석하지 않는다.

이번 자료에서 FLIP의 평균 FPR과 재현율 변화가 함께 관찰되었지만, 각 arm의 임계값과 개발 리드아웃이라는 평가 범위를 고려해야 한다. 관찰된 차이에 대해 통계적 유의성을 검정하지 않았고, URL 지름길의 인과적 교정 기전이나 차이가 발생한 원인을 확증하지 않았다.

## 4. 개인정보·누출·권리 제한

사람 판정에서 식별정보로 표시된 행이 속한 유사도 그룹을 역할 전체에서 제외하여 파생 입력을 만들었다. 개인정보 안전 파생 산출물에는 집계 결과만 두고 개인 식별자와 원문을 manifest에 포함하지 않는 검사를 적용했으며, 교차 역할 exact-text 중복과 그룹 중복 검사 결과는 privacy-safe JSON (원 작업공간 경로: `../../reports/generated/matched_privacy_safe_20260917_v1.json`)의 `checks`에서 확인한다.

이 조치는 원본의 영구 삭제나 개인정보 탐지 완료를 뜻하지 않는다. 비후보 개인정보의 미탐지 가능성, 원문·개별 예측·checkpoint의 비공개 범위, 원 제공자의 사용·공개 권리는 별도 제한으로 남는다. 로컬 파일 권한과 공개 제외 정책은 보호 조치일 뿐 개인정보 유출을 원천 차단한다는 보장이 아니다.

## 5. 결론 및 남은 제약

이번 실험은 URL 편집을 포함한 세 arm을 같은 시드 집합과 공통 학습 예산으로 실행하고, 보정 절차 뒤 개발 리드아웃에서 기술통계를 산출한 사후 탐색 자료다. 결과는 URL 의존 가설을 추가로 검토할 근거를 제공하지만, FLIP이 최우수 안전성·통계적 우월성·인과적 효과·실제 운영 효과를 입증했다고 결론 내릴 수 없다.

확증을 위해서는 평가 전에 선택 규칙과 임계값을 고정하고 고유 그룹이 분리된 미사용 독립 테스트를 수행해야 한다. 외부 일반화 성능을 주장하려면 외부 코퍼스 평가도 별도로 필요하다. 그 전까지 본 결과는 탐색적 자료로만 사용하며, 본문·URL 별도 경로 결합과 운영 적용은 후속 연구 제안 단계로 둔다.

검산과 자동 표 생성의 현재 상태는 `SCAMLENS_PROJECT_STATUS_20260917.md` (원 작업공간 경로: `../SCAMLENS_PROJECT_STATUS_20260917.md`)와 원 JSON (원 작업공간 경로: `../../reports/generated/matched_kcbert_local_final_15arms_20260917_v1.json`)을 기준으로 확인한다.
