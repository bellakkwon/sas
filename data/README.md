# 공개 집계 입력

최신 10-04 추가학습 집계 JSON·비교 CSV·합성 예시는 [팀 공유 데이터](../materials/20261004_team_v1/data/README.md)에 있습니다. 데이터 출처·비공개 입력·실행 순서도 같은 자료에 정리했습니다. 아래 루트 data는 기존 SAS 실행 입력입니다.

현재 Git에는 `processed/ab_expected_20260914/`의 집계 대조표와
`processed/sas/`의 KcBERT 조건·하위집단·전이·강건성 집계만 보관한다.
원문, URL 행 자료, 행별 점수·OOF·검수표는 로컬 전용이며 `.gitignore`로 제외한다.

기존 SAS 분석은 별도 승인된 비공개 입력을 원래 위치에 배치해야 실행할 수 있다.
현재 후속·최종 분석 입력은 [공개 집계 폴더](aggregates/README.md)에 있다. 실행은 [단일 실행기](../sas/00_RUN_ALL.sas)와 [RUNBOOK](../sas/RUNBOOK.md)을 따른다.
이전 집계 전용 패키지는 [보관본](../archive/sas_cleanup_20260929/followup_20260921_v1/README.md)으로 구분한다.
이곳의 이전 집계와 후속 U5·KISA 결과는 평가 시점과 범위가 다르므로 섞지 않는다.
