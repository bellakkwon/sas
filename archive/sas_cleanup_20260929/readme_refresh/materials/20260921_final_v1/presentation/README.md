> 아래 빌드·검사 명령은 원본 연구 작업공간에서 실행합니다. 이 공개 전달본의 수치는 [발표 정본 JSON](../evidence/submission_final_20260921.json), SAS 실행은 [안내서](../../../visualization_20260921_v1/SAS_FINAL_VISUALIZATION_20260921.md)를 보세요.

# 최종 발표 패키지 (2026-09-21)

## 산출물
- PRESENTATION_20260921.pptx / .pdf (18쪽) / PRESENTATION_SLIDES/slide_01~18.png
- RESEARCH_REPORT.md, SPEAKER_SCRIPT.md(10/15/20분 경로), QA.md, ONE_PAGE_SUMMARY.md
- reports/generated/submission_final_20260921.json: 모든 수치의 정본 근거.

## 빌드와 검사
```sh
python3 scripts/build_submission_final_20260921.py
python3 scripts/build_submission_final_20260921.py --check
node scripts/build_submission_deck_final_20260921.mjs
node scripts/build_submission_deck_final_20260921.mjs --check
```
새 추론·API·학습·임계값 조정이 없다. SAS 신규 시각화 최종본은 사용자 실행 대기이며,
main이 상태를 추후 갱신할 수 있다.

## 근거
수치는 정본 JSON 7종에서 계산한다. 경로: 10m: 슬라이드 1,2,5,7,10,11,12,13,15; 15m: 슬라이드 1,2,3,5,7,8,10,11,12,13,14,15; 20m: 슬라이드 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18.
