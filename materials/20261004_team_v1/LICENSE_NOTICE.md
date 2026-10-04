ScamLens 공개본 소스 귀속과 라이선스 안내
=======================================

1. 코드 라이선스: 기존 저장소에 코드 라이선스 부여 기록이 없으므로 이 공개본의
   코드 라이선스는 미지정(unspecified)이다. MIT를 포함한 어떤 오픈소스 라이선스도
   부여하지 않는다. 이용 조건은 권리자의 별도 허가가 필요하다.

2. 포함 코드의 출처
   - src/scamlens/preprocessing.py, url_features.py, robustness.py:
     ScamLens 저장소의 오프라인 문자열 분석 코드 복사본. 네트워크 접속 없음.
   - src/scamlens/public_results.py, scripts/verify_public_results.py,
     demo/result_explorer.py: 이 공개본을 위해 새로 작성된 집계 재검산·탐색 코드.
   - sas_examples/*.sas: ScamLens 저장소 sas/ 디렉터리의 SAS 실무자용 소스 예시.
     개인 경로 플레이스홀더로 살균됨. 실행 상태는 SAS_EXAMPLES_STATUS.md를 본다.

3. 데이터 귀속 (원시 데이터는 포함하지 않음)
   - 공개 집계 JSON은 reports/generated/matched_kcbert_u5_unused_test_20260918_v1.json
     복사본이다. 학습 코퍼스 jmjmjm3/kor-smishing-message(CC BY-NC-SA 4.0),
     DimensionV/KR-MOB-SMISHING-v2(CC BY-NC 4.0), KISA C-TAS(재배포 불가),
     UCI PhiUSIIL(CC BY 4.0), PhishTank/OpenPhish/Tranco(혼합 피드 조건)의
     원시 행은 포함하지 않는다. 전체 계보는 원 저장소 docs/DATA_LINEAGE.md를 본다.

4. 상표·모델: KcBERT는 별도 라이선스의 외부 모델이며 가중치를 포함하지 않는다.
