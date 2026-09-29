# 공개 SAS 집계 입력

`followup/`은 U5·JEV·KISA 후속 진단용 집계이고 `final/`은 최종 보고서·CAS 게시용 집계입니다. 이전 전달본에서 바이트를 그대로 복사했으며 출처·SHA-256은 [정리 manifest](../../manifests/sas_organization_20260929.json)와 로컬 검사기로 확인합니다.

실행은 [sas/00_RUN_ALL.sas](../../sas/00_RUN_ALL.sas) 하나입니다. 새 출력은 저장소의 `outputs/`에 생성하며 Git에서 제외합니다. 기존 본문·행별 점수·모델은 별도 비공개 입력이고 이 폴더에 추가하지 않습니다.
