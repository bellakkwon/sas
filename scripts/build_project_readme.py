#!/usr/bin/env python3
"""Generate the project README from the checked-in final evidence JSON."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "materials/20260921_final_v1/evidence/submission_final_20260921.json"
README = ROOT / "README.md"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def one(value: float) -> str:
    return f"{value:.1f}"


def build(data: dict) -> str:
    arms = data["arms"]
    url = data["url"]
    trunc = data["trunc"]
    kisa = data["kisa_conditions"]
    jev = data["jev_transitions"]
    fusion = data["fusion_rows"]
    runtime = data["sas_runtime"]
    seeds = ", ".join(str(x) for x in data["seeds"])
    n_seeds = len(data["seeds"])
    n_kisa_conds = len(kisa)

    rows = "\n".join(
        f"| {arm} | {one(arms[arm]['mean_fp'])} | {one(arms[arm]['mean_fn'])} | "
        f"{pct(arms[arm]['mean_recall'])} | {pct(arms[arm]['mean_fpr'])} |"
        for arm in ("BASE", "DUP", "FLIP")
    )
    kisa_rows = "\n".join(
        f"| `{name}` | {kisa[name]['tp']}/{kisa[name]['fn']} | {pct(kisa[name]['recall'])} | "
        f"{kisa[name]['normal_fp']} | {kisa[name]['normal_new_fp']} |"
        for name in ("original128", "ocr_delete128", "cap300", "ocr_delete300", "ocr_unk128", "ocr_unk300", "head_tail128")
    )
    fusion_labels = {
        "rawK": "KcBERT 기준선 (`rawK`)",
        "K": "KcBERT 점수만 재결합 (`K`)",
        "KJ": "KcBERT＋JEV (`KJ`)",
        "KU": "KcBERT＋URL 특징 (`KU`)",
        "KJU": "KcBERT＋JEV＋URL 특징 (`KJU`)",
    }
    fusion_rows = "\n".join(
        f"| {fusion_labels[name]} | {fusion[name]['fp']}건 | {fusion[name]['fn']}건 |"
        for name in ("rawK", "K", "KJ", "KU", "KJU")
    )
    return f"""# ScamLens

**정상 문자의 오탐과 스미싱의 미탐을 함께 검증하는 한국어 문자 탐지 연구**

ScamLens는 문자 분류기가 정상 안내문을 스미싱으로 잘못 경보하는지(오탐, FP)와
스미싱을 정상으로 놓치는지(미탐, FN)를 같은 평가 틀에서 함께 살펴본 프로젝트입니다.<br>
정상 문자를 스미싱으로 잘못 판단하면 정상 안내를 놓치거나 불필요한 경고를 받게 되고,
스미싱을 놓치면 피해를 막지 못할 수 있습니다. 문자 내용은 Python KcBERT로 분류하고, URL은
외부에 접속하거나 본문을 가져오지 않고 오프라인 문자열 특징으로만 다루었습니다.

평가 자료의 역할과 해석 경계를 분리하여, 새로운 기법이나 입력 개입이 실제로 미탐을
복구하는지 또는 불필요한 정상 경보를 늘리는지 그 득실을 체계적으로 검증했습니다.
수치의 정본은 [최종 제출 집계 JSON](materials/20260921_final_v1/evidence/submission_final_20260921.json)이고,
해석의 기준은 [최종 연구 보고서](materials/20260921_final_v1/presentation/RESEARCH_REPORT.md)입니다.

핵심 결론은 세 가지입니다:

* **학습 조건 비교**: U5 동일 평가자료에서 선택 원문을 추가한 DUP 조건이 평균 FP {one(arms['DUP']['mean_fp'])}건, FN {one(arms['DUP']['mean_fn'])}건으로 오류 균형이 가장 좋았으나 통계적 우월을 확정할 수 없습니다.
* **취약 조건 규명**: DUP 기준 URL 포함 정상문자의 오탐률({pct(url['1']['mean_fpr'])})과 128토큰 초과 스미싱의 미탐률({pct(trunc['truncated']['fnr'])})이 높게 관찰됐지만 단일 원인이나 인과효과로 단정할 수 없습니다.
* **개입 득실 검증**: KISA {n_kisa_conds}개 입력 조건 분석과 JEV 판정 대체·특징 결합 두 별도 실험에서 미탐 복구 시 정상 경보가 함께 늘거나 추가 이득이 없어, 관측 후 승자 교체 없이 기준 조건과 고정 임계값을 유지하기로 결정했습니다.

## 왜 필요한가

오탐은 정상 배송·결제 안내를 위험 문자라고 알리는 일이고, 미탐은 위험 문자를
정상으로 통과시키는 일입니다. 한쪽만 줄이면 다른 쪽 비용이 커질 수 있으므로
단순 정확도 하나가 아니라 정상 분모의 FPR과 스미싱 분모의 FNR을 함께 봐야 합니다.

연구 질문은 “정상 문자 경보를 늘리지 않으면서 스미싱 미탐을 줄이려면 무엇을
검증해야 하는가?”입니다. 이 질문에 답하기 위해 임계값을 검증자료에서 정한 뒤
사전에 고정하고, 평가자료를 본 뒤 규칙이나 임계값을 바꾸지 않는 비교를 구성했습니다.

## 무엇을 했는가

KcBERT는 한국어 댓글·구어체 텍스트로 사전학습된 언어모델 기반 문자 분류기입니다.
본 연구에서는 문자 본문 분류를 위해 KcBERT를 파인튜닝하며 세 가지 학습 조건을
동일 조건에서 비교했습니다. (URL 및 JEV 특징을 추가한 분석은 모델 학습 조건을
바꾼 것이 아니라 별도로 수행한 취약점 진단 및 결합 실험입니다.)

* **BASE**: 원문으로 학습.
* **DUP**: 선택한 원문을 추가하되 라벨은 유지.
* **FLIP**: 선택한 문자의 URL을 편집한 문장을 추가하되 원래 라벨을 보존 (정답 라벨 반전 없음).

중복을 정리하고 유사도 그룹 단위로 분할하여 누출 위험을 줄인 뒤, 검증셋에서
임계값을 사전에 고정하고 평가자료에서 비교했습니다. 이후 오류 조건과 입력 개입을
진단하고, 같은 결과를 SAS에서 집계·재계산했습니다.

```mermaid
flowchart LR
  A[원문·출처 정리 및 유사그룹 분할] --> B[검증 임계값 사전 고정]
  B --> C[BASE/DUP/FLIP 고정 평가]
  C --> D[오류 조건·입력 개입 진단]
  D --> E[SAS 독립 집계 검산]
```

## 평가자료와 역할

| 자료 | 구성과 규모 | 역할 및 해석 경계 |
|---|---|---|
| U5 | {data['n_test']:,}건: 정상 {data['normal']:,}건, 스미싱 {data['smishing']:,}건; 동일 자료 {n_seeds}개 seed ({seeds}) | 기존 시험·사후 진단 (과거 평가 이력이 있으며, 독립 1회 시험이 아님) |
| KISA | 고유 {data['kisa_unique_total']}건, 대표 {data['kisa_rep_total']}건 부분집합; 배송유형 양성 편의표본 | 양성 편의표본 (정상 문자가 없어 독립 정상 FPR 계산 불가) |
| 정상 후보 | 개발용 {data['normal_candidates_total']}건 | 경보 증가 점검용 (독립적인 정상 오탐률 표본이 아님) |
| JEV 대체 | seed 42에서 선택 {data['jev_total']}건; 오류 과대표집 | 사후 진단 (바꿨을 때 득실 확인용, 독립 시험이 아님) |
| JEV 결합 | 검증자료 재사용 {data['fusion_n']}건 (정상 {data['fusion_normal']}건, 스미싱 {data['fusion_smishing']}건) | 특징 결합 탐색 (추가 독립 이득을 입증하지 못함) |

## 주요 결과

### U5: 세 학습 조건 비교

근거: [U5 오류 진단 정본](materials/20260921/evidence/u5_error_diagnostics_20260920.json), [U5 고정 평가 정본](materials/20260921/evidence/matched_kcbert_u5_unused_test_20260918_v1.json).

아래 FP/FN은 동일 평가자료({data['n_test']:,}건)에서 {n_seeds}개 seed({seeds})의 결과를 평균낸 값입니다.
평균 건수의 소수점은 시드 평균의 표기이며 고유 문자 수가 아닙니다. Recall은 스미싱
분모({data['smishing']:,}건), FPR은 정상 분모({data['normal']:,}건)를 기준으로 계산했습니다.

| 조건 | 평균 FP(건) | 평균 FN(건) | 평균 Recall | 평균 FPR |
|---|---:|---:|---:|---:|
{rows}

![U5 세 조건의 seed별 오류 분포](materials/20260921/diagnostics/u5/charts/error_distribution_arm.png)

*그림 A. U5 동일 평가자료에서 BASE·DUP·FLIP의 오류 분포. 색 막대는 평균 오류 건수, 점은 시드별 결과, 검은 오차막대는 {n_seeds}시드 모표준편차이며, 독립표본 신뢰구간이 아니다.*

### URL 포함과 입력 절단

근거: [최종 제출 집계의 URL·절단 항목](materials/20260921_final_v1/evidence/submission_final_20260921.json).

아래 본문 수치는 DUP 조건의 {n_seeds}개 시드 평균입니다.

URL이 있는 정상 집단은 정상 {url['1']['normal']:,}건에서 평균 FPR {pct(url['1']['mean_fpr'])},
URL이 없는 집단은 정상 {url['0']['normal']:,}건에서 {pct(url['0']['mean_fpr'])}였습니다.
이는 URL 포함 여부와 오탐의 연관 관찰이며, URL 자체가 오탐의 단일 원인이라는 증거가 아닙니다.
128토큰을 초과한 스미싱 {trunc['truncated']['messages']}건의 FNR은 {pct(trunc['truncated']['fnr'])}(평균 FN {one(trunc['truncated']['mean_fn'])}건),
한도 이내 {trunc['nontruncated']['messages']}건은 {pct(trunc['nontruncated']['fnr'])}(평균 FN {one(trunc['nontruncated']['mean_fn'])}건)이었습니다.
절단과 미탐의 관계도 다른 문장 특성과 분리한 인과 추정은 아닙니다.

![토큰 절단 여부에 따른 미탐률과 오탐률](materials/20260921/diagnostics/u5/charts/token_truncation_impact.png)

*그림 B. 왼쪽은 스미싱 FNR, 오른쪽은 정상 FPR이며 둘 다 128토큰 절단 여부별 오류율을 BASE·DUP·FLIP 3개 조건으로 보여준다. 각 집단의 정상·스미싱 분모로 읽어야 하며 인과효과가 아니다.*

### KISA 입력 개입: 기준 seed 42

근거: [KISA OCR·입력 진단 정본](materials/20260921/evidence/kisa_ocr_diagnostics_20260921.json).

OCR(광학문자인식)은 이미지 속 문자를 텍스트로 읽는 과정입니다. 표의 처리명에서
`delete`는 OCR 잡음 삭제, `unk`는 잡음 토큰 가림(`[UNK]`), `cap300`은 입력 상한 확대를 뜻합니다.
고유 KISA {data['kisa_unique_total']}건(대표 부분집합 {data['kisa_rep_total']}건)은 배송 유형 중심의 양성 편의표본이며,
정상 후보 {data['normal_candidates_total']}건은 경보 증가를 점검하기 위한 별도의 개발용 자료입니다.
양성 표본에는 정상 문자가 없으므로 정상 오탐률을 계산할 수 없습니다.

기준 조건(`original128`)에서는 고유 {data['kisa_unique_total']}건 중 탐지 {data['kisa_base']['tp']}건, 미탐 {data['kisa_base']['fn']}건(탐지율 {pct(kisa['original128']['recall'])}), 정상 후보 경보 {kisa['original128']['normal_fp']}건이었습니다.
길이만 300토큰으로 늘린 `cap300` 단독 조건은 탐지 {kisa['cap300']['tp']}건으로 미탐 복구가 전혀 없으면서 정상 후보 경보만 {kisa['original128']['normal_fp']}건에서 {kisa['cap300']['normal_fp']}건으로 {kisa['cap300']['normal_new_fp']}건 증가했습니다.
반면 OCR 특수문자를 가리고 길이를 300토큰으로 확대한 `ocr_unk300` 조건에서는 탐지가 {kisa['ocr_unk300']['tp']}건({pct(kisa['ocr_unk300']['recall'])})으로 증가했으나(잡음 삭제인 `ocr_delete300`도 {kisa['ocr_delete300']['tp']}건으로 증가),
이 조건 역시 정상 후보 경보가 {kisa['ocr_unk300']['normal_fp']}건으로 늘어나는 득실이 관찰되었습니다.

사전 등록 후보였던 `head_tail128`(앞뒤를 합쳐 128토큰 유지)은 {data['candidate_seeds']}개 시드 전체에서 미탐 복구 없이
새 경보가 발생해 불통과되었습니다. 기준 시드 42에서는 정상 후보 경보가 {kisa['head_tail128']['normal_fp']}건(신규 {kisa['head_tail128']['normal_new_fp']}건)으로
증가했습니다. 이에 따라 관측 후 승자 교체를 하지 않고 기존 조건(`original128`)과 고정 임계값을 유지하기로 결정했습니다.

| 입력 처리 | 탐지/미탐 | 탐지율 | 정상 후보 경보 | 새 경보 |
|---|---:|---:|---:|---:|
{kisa_rows}

![KISA 입력 개입 집계](materials/20260921_final_v1/presentation/PRESENTATION_SLIDES/slide_11.png)

*그림 C. 발표 표에 정리된 기준 seed 42의 KISA 입력 개입 집계다. 실제 SAS 직접 출력이 아니며, 양성 편의표본과 정상 후보를 구분해 읽는다.*

### JEV 오류대체와 특징 결합

근거: [JEV 오류대체 정본](materials/20260921/evidence/jev_kcbert_redacted_20260920.json), [JEV 특징 결합 정본](materials/20260921/evidence/jev_kcbert_fusion_20260920.json).

JEV(외부 판정/특징)를 활용한 실험은 판정 대체와 특징 결합의 두 가지 별도 실험으로 진행했습니다.
첫째, 오류를 과대표집한 seed 42 선택 {data['jev_total']}건에서 JEV 판정으로 자동 대체한 결과, 기존 오탐 {jev['corrected_fp']}건을
해소했지만 새로운 미탐 {jev['new_fn']}건을 발생시키고 원래 정답이었던 {jev['abstain_from_correct']}건이 판정 보류로 전환되어 채택하지 않았습니다.
둘째, 검증자료 {data['fusion_n']}건을 재사용한 특징 결합 실험에서는 기준선(`rawK`)부터 오탐 {fusion['rawK']['fp']}건, 미탐 {fusion['rawK']['fn']}건이어서 결합의 추가 독립 이득을 입증할 수 없었습니다.

| 결합 조건 (기호) | 오탐 (FP) | 미탐 (FN) |
|---|---:|---:|
{fusion_rows}

## SAS의 역할

근거: [SAS 최종 시각화·가이드](archive/sas_cleanup_20260929/visualization_20260921_v1/SAS_FINAL_VISUALIZATION_20260921.md).

이번 후속 SAS 집계 검증은 모델을 새로 학습하지 않고, Python 결과의 집계 재계산과
반환물 검수에 집중했습니다. 집계 반환 {runtime['stages_ok']}단계(U5 진단, JEV 비교, JEV 결합, KISA 진단)를
전수 완료했습니다. 반환 ZIP의 {runtime['zip_members']}개 파일 중 CSV 집계를 검산하고, ODS 그래프 {runtime['pngs_inspected']}개가 생성된 것을 확인했습니다.
새 Studio/CAS/VA 코드는 준비되어 있지만 서버에서 사용자가 실행하기를 기다리는 별도 항목이며,
실제 서비스 가동이나 사전 실행 완료로 표시하지 않습니다.

![SAS U5 실제 출력](materials/20260921/sas-results/stage_u5/outputs/SGPlot.png)

*그림 D. 반환된 SAS U5 결과 폴더의 실제 출력 PNG다. SAS 집계·렌더링 검수의 근거이지 성능 개선의 증거는 아니다.*

## 성과와 남은 한계

이번 작업의 성과는 오탐과 미탐이 집중되는 조건, 시도한 입력 개입의 득실, 채택하지 않을
방법을 같은 분모와 역할 경계로 정리한 것입니다. 다음 주장은 아직 할 수 없습니다.

* 오류 원인을 하나로 확증하거나, 새 정상 독립자료의 오탐률로 일반화할 수 없습니다.
* KISA 양성·JEV 사후 진단을 실서비스 성능이나 실제 사기 확인으로 바꿔 말할 수 없습니다.
* 과거 평가자료 재사용 결과를 새 독립시험의 성능으로 부를 수 없습니다.

따라서 최종 판단은 “DUP를 포함한 비교 설계가 균형 탐색에는 가장 유망했지만,
실서비스 안전성을 입증한 것은 아니다”입니다. 다음 단계는 새 독립자료와 사전 고정한
비교, 정상·스미싱 양쪽의 분모가 있는 운영 검증입니다.

## 자료·실행 안내

| 자료 | 링크 |
|---|---|
| 최신 발표 PPT/PDF·대본 | [최신 발표 폴더](materials/20260921_final_v1/presentation/) |
| 결과·그림·해석 HTML | [결과 설명 문서](materials/20260921/explain/scamlens_results_explained_20260921.html) |
| SAS 한 번에 실행 | [00_RUN_ALL.sas](sas/00_RUN_ALL.sas), [설정·실행 안내](sas/RUNBOOK.md) |
| 폴더 정리 이력 | [SAS 프로그램·보관본 안내](docs/SAS_ORGANIZATION_20260929.md) |
| 폴더·자료 안내 | [자료 모음 안내](materials/20260921/README.md), [저장소 구성과 공개 범위](docs/REPOSITORY_ORGANIZATION_20260921.md) |
| 이전 실행·반환 안내 | [이전 반환 실행 가이드](docs/SAS_FOLLOWUP_RUN_GUIDE_20260921.md) |

저장소 루트에서 재현성·링크·이미지와 README 정본 일치를 확인합니다.

```sh
python3 scripts/build_project_readme.py --check
git diff --check
```

공개 저장소에는 집계·코드·발표 자료를 정리했습니다. 원문과 모델 가중치 등 비공개 입력이
필요하므로 새 clone만으로 전체 학습을 재현할 수 있는 패키지는 아닙니다.
이번 정리는 현재 파일 트리 기준이며 과거 Git 이력은 재작성하지 않았습니다.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="README가 생성 결과와 같은지 검사")
    args = parser.parse_args()
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    rendered = build(data)
    if args.check:
        if README.read_text(encoding="utf-8") != rendered:
            print("README.md is not generated from the canonical evidence")
            return 1
        required = [
            "materials/20260921/diagnostics/u5/charts/error_distribution_arm.png",
            "materials/20260921/diagnostics/u5/charts/token_truncation_impact.png",
            "materials/20260921_final_v1/presentation/PRESENTATION_SLIDES/slide_11.png",
            "materials/20260921/sas-results/stage_u5/outputs/SGPlot.png",
        ]
        bad = [p for p in required if not (ROOT / p).is_file() or p not in rendered]
        if bad:
            print("missing required relative image links:", ", ".join(bad))
            return 1
        links = re.findall(r"\]\(([^)]+)\)", rendered)
        broken = []
        for link in links:
            if link.startswith(("http://", "https://", "#")):
                continue
            target = link.split("#", 1)[0]
            if target and not (ROOT / target).exists():
                broken.append(target)
        if broken:
            print("broken relative links:", ", ".join(sorted(set(broken))))
            return 1
        print("README.md: canonical content and required image links OK")
        return 0
    README.write_text(rendered, encoding="utf-8")
    print(f"wrote {README} ({len(rendered.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
