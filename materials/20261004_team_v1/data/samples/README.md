# 합성 예시와 빈 반입 양식

`messages.csv`와 `hard_negative_messages.csv`는 프로젝트에서 만든 합성 문자다. `.invalid` 주소는 테스트 전용이며 실제 사기 사이트가 아니다. 모델 정확도 측정이나 실제 유형 검증에 사용하지 않는다.

`consented_sms_import_template.csv`, `url_free_malicious_import_template.csv`, `voice_phishing_transcript_import_template.csv`는 컬럼 설명용 양식이다. 실제 문자를 채운 파일은 이 저장소에 커밋하지 않는다. 출처·동의·라벨·중복·개인정보 검수 후 별도 비공개로 처리한다.

`voice_phishing_pattern_catalog.csv`와 `scam_journeys.jsonl`은 후속 설계의 합성 예시다. 실제 녹취 학습이나 모바일 개입 효과가 검증됐다는 근거가 아니다.
