# SAS 교육 최종 발표 — 실패 조건 분석

> 최신 발표용 Studio·VA 작업은 [2026-09-21 실행 안내](../visualization_20260921_v1/SAS_FINAL_VISUALIZATION_20260921.md)를 따릅니다. 아래 내용은 이전 판의 기록이며, 공개본에 없는 행별 입력을 요구할 수 있습니다.

목적은 스미싱 탐지의 실패 조건을 설명하고 검수 우선순위로 연결하는 교육 최종 발표와
포트폴리오다. Python은 전처리·분할·기존 탐지 모델을, SAS는 감사·통계 분석·시각화를 맡는다.

**최신 후속 실행은 [집계 전용 실행 안내](../docs/SAS_FOLLOWUP_RUN_GUIDE_20260921.md)를 따른다.**
U5·Jev·KISA 후속 패키지는 ../followup_20260921_v1/에 있다.
최신 후속 실행의 반환 결과는 [SAS 열람본](../materials/20260921/sas-results/index.html)에서 확인한다.
과거 원문·행별 입력은 공개 Git에서 제외했으며 기존 분석 재실행에는 별도 비공개 입력이 필요하다.

기존 A/B 검수 분석은 `00_RUN_AB.sas` → 11 → 12다.
합의 전 A/B 검수 일치도와 최종 합의 범주별 저장 모델 판정을 분석한다.
과거 A 단독 09·10은 `archive/`로 이동했으며 현행 실행 코드에 포함하지 않는다.
기존 결과와 단계별 상태는 [SAS 현황](../docs/SAS_STATUS_20260914.md)에 있다.

## 시작하기

[런북](RUNBOOK.md)과 [현장 체크리스트](../docs/SAS_EXECUTION_CHECKLIST.md)를 따른다.
SAS 서버 기본 위치는 `/home/student/github/`이며 기존 출력은 덮어쓰지 않는다.

| 프로그램 | 질문 / 산출물 | 선행 조건 |
|---|---|---|
| 01_load_and_audit | 분할·결측·한글·URL 분포, 이항 신뢰구간 | score/text CSV |
| 02_meta_classifier | OOF 입력의 SAS 메타 회귀 계수·OR·CI | 01, 검증된 train OOF |
| 03_model_comparison | 같은 평가 행에서 ROC-AUC 차이 | 01; 02 성공 시 메타 비교 추가 |
| 06_transformer_contrast | 기존 KcBERT 계열 ROC-AUC 비교 | 01, 해당 모델 평가 확률 |
| 05_visuals | URL별 오탐·미탐, 분포, ROC, 난독화 | 01; 메타 곡선은 02 성공 시 |
| 07_composition_and_novelty | 유형·유사도·연도와 실패의 연관, 제외 표본 영향 | 외부 feature CSV, 독립 실행 |
| 04_korean_text_model | SAS 자체 텍스트 모델의 보조 실험 | 01, 선택 실행 |
| 08_fage_gate | 원래 train fold 0에서 A/B/C와 스태킹·FAGE를 시드별 재적합 | `sas_fage_abc_rows.csv`, 독립 실행 |
| 11_reviewer_ab_agreement | 합의 전 A/B 범주·행동 일치도 | `sas_reviewer_ab_20260914.csv`, AB 실행기 |
| 12_consensus_model_comparison | 최종 합의 범주별 원 라벨 기준 오류·시드 평균 | `sas_consensus_predictions_20260914.csv`, AB 실행기 |
| 13_publish_ab_to_cas | 검증된 11·12 집계의 선택적 CAS 공유·저장 | 같은 세션의 11·12 완료 문맥 |

`00_RUN_PENDING.sas`는 과거 진입점임을 안내하고 종료한다.
`00_RUN_AB.sas`는 11·12의 로그·HTML·CSV를 새 출력 폴더에 남긴다.
현재 보관 중인 공통 분석 단계를 재현할 때는 `00_RUN_ALL.sas`를 사용한다. 이 실행기도 단계별 로그·HTML과 실행 상태를 남긴다. 07을 먼저 실행하고
내부 분석으로 이어진다. 04는 기본 비활성이다. 08은 `sas_fage_abc_rows.csv`가 있을 때만,
실행한다. 시드를 한 모형에 합치지 않으며, 원래 validation/test를 쓰지 않는다.
Python FAGE 수치가 08 로그를 대신하지 않는다.

## OOF와 메타 회귀

train 입력은 같은 유사도 그룹을 학습하지 않은 모델의 OOF 확률이어야 한다.
일반 추론용 `text_probability`와 train 적합용 OOF를 구별한다.
OOF가 없거나 행·그룹·입력 해시가 맞지 않으면 02를 실행 준비 완료로 표시하지 않는다.

고정 프로토콜 OOF 복원은 train 내부 교차적합이다. 현재 입력으로 복원한 파일을 과거
학습 때 저장한 원본 OOF라고 부르지 않는다. 기존 탐지 모델과 평가 임계값은 보존한다.
SAS 02는 무규제 회귀이고 Python 채택 모형은 규제·클래스 가중치를 사용하므로
계수 수치나 부호가 같아야 한다고 강제하지 않는다. 추정된 OOF 점수와 문구 군집의
의존성 때문에 통상적인 Wald CI는 탐색적으로 해석한다.

## 통계 해석

- DeLong `ROCCONTRAST`는 **ROC-AUC** 비교다. PR-AUC/F1/Recall 검정이 아니며
  Python으로 구현할 수 없는 검정도 아니다.
- 효과 크기와 CI를 같이 보고한다. 비유의성을 무기여·동등성·효과 부재로 해석하지 않는다.
- 07과 Python의 표본·범주·수식·최대우도 추정이 같으면 관측 수와 추정값을 대조한다.
  차이가 나면 데이터형·제외 행·기준범주·수렴을 조사한다.
- 외부 연도는 전체 기간 중복 제거 후 최초 관측 시점이다. 실제 연도별 트래픽이나
  미래 검증이 아니다. 유형·유사도와 실패의 연관을 탐색한다.
- 기관사칭 검수 대기 자료는 확정 성과표에서 제외한다. Hard Negative 선별 도전셋과
  내부 그룹 홀드아웃은 다른 평가 범위다.

입력 행 수·열·해시는 export summary와 번들 manifest를 따른다. 숫자를 다시 옮겨
쓰지 않는다. UTF-8과 `event='1'`을 확인한다. 개인 SAS 이전 번들은 공개 배포본이 아니며
데이터 재배포 권한을 부여하지 않는다.
