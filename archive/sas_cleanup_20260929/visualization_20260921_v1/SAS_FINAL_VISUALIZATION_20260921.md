# ScamLens: SAS에서 실행할 순서

준비된 것은 **Studio 보고서 코드와 VA 구성 안내**입니다. 아래 실행은 사용자가 합니다.
기존에 반환한 SAS 집계 보고서는 검수했지만, 이번 Studio 보고서·CAS 게시·VA 저장본의
실행 성공은 아직 확인하지 않았습니다. 원문 없이 공개 집계 CSV만 사용합니다.

## 1. 저장소 갱신

SAS Studio 왼쪽 Git 영역에서 기존 `kimchikingdom/sas` 저장소의 `main`을 **Pull**합니다.
파일 영역에서 `/home/student/github/visualization_20260921_v1/`가 보이는지 확인하세요.
이 폴더에 `data`, `sas`, 이 안내서가 있어야 합니다. 저장소 위치가 다르면 아래
`projroot`를 실제 **저장소 루트**로 바꾸세요. 예전 `14`·`15` 파일 대신 아래 새 파일을 사용합니다.

## 2. Studio 발표용 보고서 만들기

새 SAS 프로그램에 아래 두 줄을 넣고 전체 실행합니다.

```sas
%let projroot=/home/student/github;
%include "&projroot./visualization_20260921_v1/sas/00_RUN_FINAL_VISUALIZATION_20260921.sas";
```

성공한 경우 로그 끝에 `SCAMLENS_FINAL_STUDIO_COMPLETE`와 `REPORT=...`가 표시됩니다.
파일 영역을 새로 고침하고 다음 폴더를 여세요.

```text
visualization_20260921_v1/outputs/run_<UUID>/
  final_visualization.html
  readback_sv_models.csv
  readback_sv_features.csv
  readback_sv_truncation.csv
  readback_sv_kisa.csv
  readback_sv_jev.csv
  readback_sv_fusion.csv
  run_status.txt
```

- `run_status.txt`에 `status=ok stage=studio_aggregate_report`가 있어야 합니다.
- `final_visualization.html`을 선택해 **다운로드**하세요. 그림을 내장하므로 이 파일
  하나로 보고서를 열 수 있습니다. 보고서의 표·그림이 모두 표시되는지 확인하세요.
- 그래프는 U5 오탐·미탐, URL 유무별 오탐률, 절단 여부별 미탐률,
  KISA 고유·대표 표본의 조건별 재현율, 정상 후보의 조건별 오탐을 보여줍니다.
  JEV 대체·결합은 별도 표로 제공합니다.
- 오류가 있으면 성공 문구만 확인하지 말고 **최초 ERROR 앞뒤 로그**를 보관하세요.
  이 단계는 CAS를 시작하지 않습니다.

## 3. VA에서 사용할 집계표 올리기

별도 SAS 프로그램에서 아래를 실행합니다. Studio 단계와 다른 세션이어도 입력을 다시 읽습니다.

```sas
%let projroot=/home/student/github;
%let sv_suffix=20260921;
%include "&projroot./visualization_20260921_v1/sas/90_PUBLISH_FINAL_TO_CASUSER_20260921.sas";
```

이미 같은 이름의 테이블이 있으면 덮어쓰지 않고 중단합니다. **기존 게시본을 다시
사용하거나**, 별도 게시가 필요할 때 `sv_suffix=20260921b`처럼 새 값을 지정하세요.
접미사는 영문·숫자·밑줄 1~12자입니다. 추가 승인 플래그나 환경변수 설정은 필요 없습니다.

이 코드는 입력 검사를 거쳐 집계표를 CASUSER에 올리고, 6개 모두 다시 읽어 원본과
비교한 뒤 VA에서 보이도록 승격합니다. 로그의 `SCAMLENS_FINAL_CAS_COMPLETE`,
`CAS_EVIDENCE=...`를 확인하세요. 해당 `outputs/cas_<UUID>/cas_status.txt`에
`status=ok stage=cas_readback_and_promote`가 있어야 합니다. 중간 실패 시 일부 테이블이
남을 수 있으므로 성공으로 간주하지 말고 로그와 접미사를 보관하세요.

| 기본 테이블 이름 (CASUSER) | 입력 CSV | 행 수 | 고유 키 |
|---|---|---:|---|
| `slf_u5_20260921` | `data/u5_models.csv` | 15 | arm, seed |
| `slf_feat_20260921` | `data/u5_features.csv` | 17 | feature_category, feature_value |
| `slf_trunc_20260921` | `data/u5_truncation.csv` | 6 | arm, is_truncated |
| `slf_kisa_20260921` | `data/kisa_conditions.csv` | 105 | cohort, seed, condition |
| `slf_jev_20260921` | `data/jev_comparison.csv` | 15 | seed, cohort |
| `slf_fusion_20260921` | `data/jev_fusion.csv` | 15 | arm, role |

접미사를 바꾸었다면 VA에서도 변경된 이름을 선택하세요. CASUSER는 개인 공간이며
다른 계정의 접근 권한을 자동으로 부여하지 않습니다. 승격은 디스크 영구 저장과
다릅니다. CAS 서버 재시작 후 사라졌다면 다시 적재해야 합니다.

## 4. Visual Analytics 보고서 구성

Visual Analytics에서 **새 보고서 → 데이터 추가**로 CASUSER의 위 6개 표를 선택합니다.
표가 없으면 CAS 실행 로그와 계정·CASUSER 선택을 먼저 확인하세요. 표를 서로 조인하지 않습니다.

데이터 창에서 `seed`, `is_truncated`는 숫자라도 **범주(Category)**로 바꿉니다.
비율 변수 `recall`, `fpr`, `fnr`, `dup_fpr`, `dup_fnr`의 형식은 **백분율(Percent)**,
집계는 **평균(Average)**으로 지정합니다. 원본이 0~1이므로 100을 다시 곱하지 않습니다.
아래 표의 건수 변수도 평균으로 설정하면 같은 표본을 시드 수만큼 합산하는 실수를 줄입니다.

### 페이지 1 — 기존 시험의 성능과 오류 조건

| 개체 | 데이터 | 범주·역할 | 측정값 / 집계 | 개체 필터 |
|---|---|---|---|---|
| 막대 그래프: 평균 오탐·미탐 | slf_u5 | 범주 arm | fp, fn / 평균 | 없음 (다섯 시드 평균) |
| 목록표: 시드별 결과 | slf_u5 | arm, seed | tp, tn, fp, fn, recall, fpr / 평균 | 없음 |
| 막대 그래프: URL 유무 | slf_feat | 범주 feature_value | dup_fpr / 평균 | feature_category = has_url |
| 목록표: URL 분모 | slf_feat | feature_value | n_normal, dup_avg_fp / 평균 | feature_category = has_url |
| 막대 그래프: 절단 미탐률 | slf_trunc | 범주 is_truncated | fnr / 평균 | arm = DUP |
| 목록표: 절단 분모 | slf_trunc | is_truncated | n_smishing, mean_fn / 평균 | arm = DUP |

상단 텍스트: **“U5는 과거 평가 이력이 있는 동일 시험 문자들입니다. 시드 평균은
다섯 독립 표본의 평균이 아니며, URL·절단 차이는 연관성 진단입니다.”**
이 페이지에는 시드 42 필터를 걸지 않습니다. 목록표에서 arm·seed를 모두 보여줍니다.

### 페이지 2 — 외부 스미싱과 정상 후보의 입력 진단

이 페이지의 데이터는 `slf_kisa` 하나입니다. 페이지 컨트롤에 **드롭다운 목록**을
넣고 범주를 `seed`로 지정합니다. **Required(필수 선택)**을 켜고 초기값을 **42**로
설정하세요. 버전에 따라 초기값을 직접 입력하거나 42를 선택한 상태로 저장합니다.
각 그래프의 개체 필터는 아래처럼 서로 다르게 둡니다.

| 개체 | 범주 | 측정값 / 집계 | 개체 필터 |
|---|---|---|---|
| 가로 막대: KISA 고유 표본 | condition | recall / 평균 | cohort = kisa_unique |
| 가로 막대: KISA 대표 표본 | condition | recall / 평균 | cohort = kisa_representatives |
| 가로 막대: 정상 후보 경보 | condition | fp / 평균 | cohort = normal_candidates |
| 목록표: 분모·탐지·미탐 | cohort, condition | n, tp, fn, fp, recall, fpr / 평균 | 없음 |

상단 텍스트: **“대표 표본은 고유 표본의 부분집합입니다. 두 표본을 합산하지 않습니다.
정상 후보는 개발용이므로 독립 오탐률로 해석하지 않습니다. 조건 비교는 사후 진단입니다.”**
모든 개체에 seed 컨트롤의 필터가 적용되는지 확인합니다. 기본 시드에서 고유 표본
`original128`의 `tp/n`과 Studio 표가 일치해야 합니다. 긍정 표본의 빈 `fpr`를
0으로 바꾸지 마세요. 정상 후보의 빈 `recall`도 같은 원칙입니다.

### 페이지 3 — JEV 판정 대체와 특징 결합

| 개체 | 데이터 | 범주·역할 | 측정값 / 집계 | 개체 필터 |
|---|---|---|---|---|
| 목록표: 판정 대체 | slf_jev | seed, cohort | n, b_fp, b_fn, j_fp, j_fn, j_abstain_pos, j_abstain_neg, t_corrected_fp, t_new_fn, t_abstain_from_correct / 평균 | seed = 42 AND cohort = all |
| 목록표: 특징 결합 | slf_fusion | arm, role | n, normal_denominator, smishing_denominator, fp, fn, recall, fpr / 평균 | role = readout |
| 막대 그래프: 결합 오탐·미탐 | slf_fusion | 범주 arm | fp, fn / 평균 | role = readout |

`slf_jev`의 실제 열 이름은 `b_fp`, `t_corrected_fp`, `t_new_fn`입니다.
`baseline_fp` 같은 별칭은 만들지 않았습니다. 각 데이터의 필터를 개별 지정하고,
다른 데이터로 필터를 자동 연결하지 않습니다. `meta_fit`·`calibration`을 readout에
합산하지 마세요. 두 패널 위에는 각각 **“오류를 과대표집한 선택 표본”**,
**“기존 validation 재사용 탐색”**을 표시합니다. 결합 결과의 무오류를 새 독립
시험 정확도나 추가 성능 개선으로 표현하지 않습니다.

### 페이지 4 — 결론·근거·한계

텍스트 개체로 다음을 정리합니다.

- 성과: 오류가 집중되는 조건을 찾고, 수정 후보의 득실을 비교해 채택 여부를 결정했다.
- 결정: 기본 입력과 기존 고정 임계값을 유지한다. JEV 자동 대체는 채택하지 않는다.
- 한계: 새 실제 정상 자료의 독립 오탐률, 단일 오류 원인, 실서비스 효과는 미확인이다.
- 근거: 이번 보고서 HTML, 입력 CSV, manifest, Studio/CAS 상태 파일의 저장 위치.
- 상태: 실제 실행 후 확인한 범위만 완료로 기록한다. 코드가 있다고 실행 완료로 쓰지 않는다.

## 5. 저장하고 확인하기

보고서를 `ScamLens_Final_20260921`로 저장합니다. 편집 화면을 닫았다가 다시 열어
페이지 2의 시드 기본값 42와 페이지 3의 `all`·`readout` 필터가 유지되는지 확인하세요.
Studio 표와 VA 표의 건수를 대조하고, 각 페이지의 제목·축·범례가 읽히는지 확인합니다.
필요하면 VA의 보고서 인쇄/PDF 기능으로 발표용 사본을 저장합니다(메뉴명은 버전에 따라 다름).

SAS 실행 후 보관할 것은 **HTML 한 파일, Studio 상태 파일, CAS 상태 파일,
오류가 있을 때의 로그, VA 저장 보고서·화면**입니다. 검산이 필요하면 각 실행 폴더의
readback CSV도 함께 보관하세요. 이를 확인한 뒤에야 실제 시각화 완료로 표시합니다.

패키지 자체의 무결성은 다운로드한 폴더에서 다음 명령으로 검사할 수 있습니다.
SAS 실행을 대신하는 검사는 아닙니다.

```sh
python3 verify_package.py
```

공식 문서: [CAS 적재·승격](https://go.documentation.sas.com/api/collections/pgmsascdc/v_020/docsets/casref/content/casref.pdf?locale=en),
[VA 컨트롤과 역할](https://documentation.sas.com/api/collections/vacdc/v_026/docsets/vaobj/content/vaobj.pdf?locale=cn),
[SAS 막대 그래프](https://documentation.sas.com/api/collections/pgmsascdc/v_063/docsets/grstatproc/content/grstatproc.pdf?locale=en).
