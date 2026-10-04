# 공유 데이터

| 폴더 | 내용 | 사용 |
|---|---|---|
| [aggregates](aggregates/README.md) | 기존 실측 지표·추가학습 전체 JSON | 수치 정본 |
| [derived](derived/README.md) | 정본에서 재계산한 CSV와 요약 | 비교·SAS 반입 |
| [samples](samples/README.md) | 합성 문자와 빈 반입 양식 | 형식·코드 확인 |

행별 원문·원 URL·확률·정상 후보 ID·모델 가중치는 없다. K01~K22는 이미 공개 집계에서 사용하는 가명 사례 코드이며 원문에 대한 접근권을 뜻하지 않는다. 독립 신규 데이터 확보는 [비공개 입력 안내](../docs/PRIVATE_INPUTS.md)를 따른다.

출처 경로와 SHA-256은 [SOURCE_MANIFEST](../SOURCE_MANIFEST.json)에 있다. 실제/합성 여부와 자료 역할은 각 폴더 안내에서 확인한다. 원 데이터의 공개 이용 가능 여부와 파일 공개 여부는 다르다.
