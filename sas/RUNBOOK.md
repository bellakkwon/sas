# SAS 실행 안내

실행할 파일은 [00_RUN_ALL.sas](00_RUN_ALL.sas) 하나입니다. SAS Studio에서 전체 파일을 실행하거나 아래 코드를 제출합니다. 서버의 저장소 경로가 다르면 `projroot`를 바꿉니다.

```sas
%let projroot=/home/student/github;
%include "&projroot./sas/00_RUN_ALL.sas";
```

기본 `AUTO`는 공개 집계 분석과 비공개 입력이 준비된 기존 분석을 실행합니다. 없는 비공개 입력, 선행 단계 부재, 꺼진 선택 기능은 상태표에 건너뛴 이유를 남깁니다. 건너뜀은 완료가 아닙니다.

| 설정 | 기본값 | 동작 |
|---|---|---|
| `sl_profile` | `AUTO` | 가능한 모든 분석. `PUBLIC`은 공개 집계만, `FULL`은 기존 분석 입력이 빠지면 중단 |
| `sl_run_cas` | `0` | `1`이면 분석 후 CAS 게시·읽기 대조. SAS Viya와 게시 권한 필요 |
| `sl_run_text` | `0` | `1`이면 04 SAS 문자 모델 보조 실험. 비공개 본문 입력 필요 |
| `sl_run_zip` | `1` | 후속 분석 결과를 SAS 자체 ZIP 기능으로 포장 |

공개 집계와 CAS를 함께 실행하려면:

```sas
%let projroot=/home/student/github;
%let sl_profile=PUBLIC;
%let sl_run_cas=1;
%include "&projroot./sas/00_RUN_ALL.sas";
```

실행마다 `outputs/run_<UUID>/`를 새로 만듭니다. `run_status.csv`, 로그, 단계별 HTML, `followup/`의 후속 진단과 ZIP, `final/`의 최종 시각화와 선택 CAS 반환 파일을 확인합니다. 이전 출력은 덮어쓰지 않습니다. 상태가 `RUNNING`에서 끝났으면 중간 중단으로 보고 로그를 확인합니다. 로그·집계 값 검수 전에는 실행 완료를 연구 결과 검증으로 해석하지 않습니다.

기존 분석 입력은 `data/processed/sas/`에 별도 비공개로 준비합니다. 본문·행별 예측·가중치를 Git에 올리지 않습니다. KcBERT 재학습은 이 실행기의 범위에 포함되지 않으며, 자원 한도로 중단했던 옛 Compute 인계 코드는 보관본입니다.

로컬 검사:

```sh
python3 scripts/verify_sas_layout.py
python3 scripts/build_project_readme.py --check
```

이 검사는 파일·입력 해시·경로·실행 계약을 확인합니다. 실제 SAS Studio/CAS 실행 검증은 새 실행 로그와 반환 파일로 수행합니다.
