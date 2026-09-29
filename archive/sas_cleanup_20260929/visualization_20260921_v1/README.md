# ScamLens: SAS 실행 자료

[실행·VA 구성 안내](SAS_FINAL_VISUALIZATION_20260921.md)를 순서대로 따라 하세요.

1. SAS Studio에서 00_RUN_FINAL_VISUALIZATION_20260921.sas 실행 → HTML 한 파일 다운로드
2. 90_PUBLISH_FINAL_TO_CASUSER_20260921.sas 실행 → CAS 집계 대조·게시
3. 안내서의 데이터·열·필터 설정대로 VA 4페이지 구성·저장

공개 집계 CSV만 포함합니다. 코드·파일 무결성 검사와 실제 SAS 실행 확인은 다릅니다.
현재 실제 Studio/CAS/VA 실행은 사용자 진행 항목입니다.

파일 검사: 이 폴더에서 `python3 verify_package.py` 실행.
기존 실행 결과가 있는 outputs/는 패키지 검사의 입력이 아니며 재생성 시 보존합니다.
