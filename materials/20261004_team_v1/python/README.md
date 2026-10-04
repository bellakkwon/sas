# 실행 가능한 오프라인 코드

전처리·URL 정적 특징·난독화 코드와 합성 테스트를 제공한다. 원문 분류기나 모델 가중치는 포함하지 않는다.

```sh
python3 scripts/offline_demo.py
python3 -m pip install pytest
PYTHONPATH=src python3 -m pytest tests -q
```

이 폴더에서 실행한다. 데모는 형제 `data/samples/messages.csv`를 사용하고 원문 접속 없이 URL 문자열 특징을 출력한다. 테스트에 등장하는 전화번호 형태의 문자열은 마스킹 검사를 위한 합성 fixture이며 실제 사용자 자료가 아니다. 데모·테스트 결과를 실제 스미싱 탐지 성능으로 해석하지 않는다.
