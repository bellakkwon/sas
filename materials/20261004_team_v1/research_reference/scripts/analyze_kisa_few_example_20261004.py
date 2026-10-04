"""Read-only, independent transition audit and source-generated few-example report."""
import argparse,json,math,statistics
from collections import defaultdict,Counter
from pathlib import Path
import kisa_few_example_common_20261004 as c
PUBLIC=c.ROOT/'reports/generated/kisa_few_example_20261004.json'
DOC=c.ROOT/'docs/KISA_FEW_EXAMPLE_RESULT_20261004.md'
TMP=c.ROOT/'tmp/kisa_few_example_20261004'

def independently_count(base,after,S,t,collisions=()):
    b=[float(p)>=t for p in base];a=[float(p)>=t for p in after]
    held=[i for i in range(22) if i not in S and i not in collisions]
    common=[i for i in range(9) if i not in S and i not in collisions]
    misses=[i for i in held if not b[i]];prior=[i for i in held if b[i]]
    rec=sum(a[i] for i in misses);new_miss=sum(not a[i] for i in prior)
    nf=sum(a[i] and not b[i] for i in range(22,272));clean=bool(rec and not new_miss and not nf)
    return {'support_count':len(S),'support_baseline_misses':sum(not b[i] for i in S),'support_detected':sum(a[i] for i in S),'heldout_count':len(held),'common_denominator':len(common),'common_detected':sum(a[i] for i in common),'common_baseline_detected':sum(b[i] for i in common),'common_recovered':sum(a[i] and not b[i] for i in common),'miss_denominator':len(misses),'recovered':rec,'recovery_rate':rec/len(misses) if misses else None,'retention_denominator':len(prior),'retained':sum(a[i] for i in prior),'new_misses':new_miss,'baseline_normal_alerts':sum(b[22:]),'normal_alerts':sum(a[22:]),'new_normal_alerts':nf,'resolved_normal_alerts':sum(b[i] and not a[i] for i in range(22,272)),'clean_recovery':clean,'all_supports_were_missed':all(not b[i] for i in S),'all_supports_learned':all(a[i] for i in S),'full_common_clean_success':bool(clean and all(not b[i] for i in S) and all(a[i] for i in S) and len(common)==9-len(S) and all(a[i] for i in common))}

def comparison(base,after,controls,S,t,collisions=()):
    result=independently_count(base,after,S,t,collisions)
    assert result==c.metrics(base,after,S,t,collisions)
    cs=[]
    for train,p in controls:
        v=independently_count(base,p,S,t,collisions)
        assert v['miss_denominator']==result['miss_denominator'] and v['common_denominator']==result['common_denominator']
        cs.append({'trained_indices':list(train),'evaluation_excludes':list(S),**{k:v[k] for k in ['recovered','normal_alerts','new_normal_alerts','new_misses','common_detected']}})
    return result,cs

def run():
    prep=c.verify_sources();models=[];raw_hashes={};rows=0;comparisons=0
    for kind in ['neural','linear']:
        for spec in c.model_specs(kind):
            mid=spec['id'];raw=c.existing_result(kind,mid)
            if raw is None:raise ValueError('Incomplete experiment: '+mid)
            raw_hashes[kind+'/'+mid]=c.sha(c.OUT/kind/(mid+'.json'))
            base=c.probabilities(raw['baseline_probabilities']);prior,singles=c.prior_predictions(kind,mid)
            gap=max(abs(float(a)-float(b)) for a,b in zip(base,prior))
            assert gap<=1e-5 and all((a>=spec['threshold'])==(b>=spec['threshold']) for a,b in zip(base,prior))
            group_by_support={tuple(g['support_indices']):g for g in raw['groups']};groups=[]
            for g in raw['groups']:
                S=g['support_indices'];coll=g.get('collisions',[]);steps={}
                for step in c.STEPS:
                    after=g['steps'][step]['probabilities']
                    m,one=comparison(base,after,[([j],singles[j][step]) for j in S],S,spec['threshold'],coll)
                    two=[]
                    if len(S)==3:
                        import itertools
                        _,two=comparison(base,after,[(pair,group_by_support[pair]['steps'][step]['probabilities']) for pair in itertools.combinations(S,2)],S,spec['threshold'],coll)
                    steps[step]={'metrics':m,'one_example_controls':one,'additional_recovery_vs_one_mean':m['recovered']-statistics.mean(x['recovered'] for x in one),'normal_alert_change_vs_one_mean':m['normal_alerts']-statistics.mean(x['normal_alerts'] for x in one),'two_example_controls':two,'additional_recovery_vs_two_mean':m['recovered']-statistics.mean(x['recovered'] for x in two) if two else None}
                    rows+=272;comparisons+=1+len(one)+len(two)
                groups.append({'group_id':g['group_id'],'support_indices':S,'support_cases':[f'K{i+1:02d}' for i in S],'size':len(S),'collisions':coll,'unique_support_features':g.get('unique_support_features',len(S)),'steps':steps})
            models.append({'id':mid,'family':spec['family'],'kind':kind,'original_kind':raw['kind'],'baseline_kisa_detected':sum(float(p)>=spec['threshold'] for p in base[:22]),'baseline_normal_alerts':sum(float(p)>=spec['threshold'] for p in base[22:]),'groups':groups})
    if len(models)!=263:raise ValueError('model coverage')
    proof=c.load(TMP/'update_validation.json')
    assert proof['status']=='passed' and proof['conditions']==224 and proof['probability_rows']==224*12*3*272 and proof['maximum_difference']<1e-10
    for mid,h in proof['result_hashes'].items():assert h==raw_hashes['linear/'+mid]
    assert proof['derived_conditions']==12 and proof['derived_probability_rows']==12*12*3*272 and proof['derived_maximum_difference']<1e-10
    assert len(proof['result_hashes'])==224 and len(proof['derived_result_hashes'])==12
    for mid,h in proof['derived_result_hashes'].items():assert h==raw_hashes['linear/'+mid]
    assert proof['checker_sha256']==c.sha(TMP/'verify_actual_updates.py')
    def aggregate(ms,size,step):
        vals=[g['steps'][step] for m in ms for g in m['groups'] if g['size']==size];metrics=[v['metrics'] for v in vals]
        rng=lambda key:[min(v[key] for v in metrics),max(v[key] for v in metrics)]
        return {'conditions':len(ms),'observations':len(vals),'recovery_range':rng('recovered'),'miss_denominator_range':rng('miss_denominator'),'normal_alert_range':rng('normal_alerts'),'new_normal_alert_range':rng('new_normal_alerts'),'clean_recovery':sum(v['clean_recovery'] for v in metrics),'own_missed_supports_learned_clean_recovery':sum(v['clean_recovery'] and v['all_supports_were_missed'] and v['all_supports_learned'] for v in metrics),'full_common_clean_success':sum(v['full_common_clean_success'] for v in metrics),'clean_gain_over_every_single_control':sum(v['metrics']['clean_recovery'] and v['metrics']['all_supports_were_missed'] and v['metrics']['all_supports_learned'] and v['metrics']['recovered']>max(x['recovered'] for x in v['one_example_controls']) for v in vals),'mean_additional_recovery_vs_one':statistics.mean(v['additional_recovery_vs_one_mean'] for v in vals)}
    totals={str(k):{s:aggregate(models,k,s) for s in c.STEPS} for k in [2,3]}
    fam=defaultdict(list)
    for m in models:fam[m['family']].append(m)
    families={f:{str(k):{s:aggregate(ms,k,s) for s in c.STEPS} for k in [2,3]} for f,ms in fam.items()}
    examples=[];partial_gains=[]
    for m in models:
        for g in m['groups']:
            for st in c.STEPS:
                v=g['steps'][st];a=v['metrics']
                if a['clean_recovery'] and a['all_supports_were_missed'] and a['all_supports_learned']:
                    examples.append({'model':m['id'],'group_id':g['group_id'],'size':g['size'],'step':int(st),'baseline_normal_alerts':m['baseline_normal_alerts'],**v})
                if a['clean_recovery'] and a['recovered']>max(x['recovered'] for x in v['one_example_controls']):
                    partial_gains.append({'model':m['id'],'group_id':g['group_id'],'size':g['size'],'step':int(st),'baseline_normal_alerts':m['baseline_normal_alerts'],**v})
    result={'status':'completed','conditions':len(models),'neural_checkpoints':27,'linear_and_derived_conditions':236,'primary_step':10,'support_design':c.get_plan()['group_design'],'groups':c.get_plan()['groups'],'totals':totals,'families':families,'models':models,'own_missed_learned_clean_examples':examples,'limitations':c.get_plan()['limitations']}
    result['clean_gains_without_requiring_support_learning']=partial_gains
    kisa,normal,_=c.input_data()
    result['input_metadata']={'kisa_rows':len(kisa),'kisa_similarity_groups':len({x['group_id'] for x in kisa}),'normal_candidates':len(normal),'normal_source_splits':dict(Counter(x['split_origin'] for x in normal))}
    validation={'status':'passed','actual_adapted_prediction_rows':rows,'matched_transition_evaluations':comparisons,'bound_source_files':len(prep['files']),'independent_linear_update_proof_sha256':c.sha(TMP/'update_validation.json'),'raw_result_hashes':raw_hashes,'analysis_source_sha256':c.sha(__file__),'method':'Independent stdlib threshold/transition counts checked against runner metric implementation; fixed matched holdouts; original source hashes; full-vector linear update reconstruction and direct derived-blend reconstruction'}
    return result,validation

def markdown(r,v):
    fmt=lambda a:str(a[0]) if a[0]==a[1] else f'{a[0]}–{a[1]}'
    lines=['# 두 건·세 건 추가학습 실험','','## 검증 범위','',f"KcBERT {r['neural_checkpoints']}개 체크포인트와 선형·결합 {r['linear_and_derived_conditions']}개 조건을 동일한 고정 조합으로 검증했다. 시드·fold·삭제 변형을 포함한 조건 수이며 서로 다른 모델 구조 수가 아니다.",'','기존 K01~K09를 시드42로 섞어 세 묶음으로 나누고, 각 묶음의 모든 두 건 조합과 세 건 조합을 사용했다. 두 건 조합9개·세 건 조합3개다. 가능한 전체 조합(두 건36개·세 건84개)을 모두 검사한 결과는 아니다.','',*['- '+', '.join(f'K{i+1:02d}' for i in block) for block in r['support_design']['blocks']],'','원래 모델·전처리·임계값과 업데이트 수를 고정했다. 두 건·세 건을 한 배치에 넣어 평균 손실로 업데이트하므로, 업데이트 수는 같지만 한 번에 사용하는 문자 수와 계산량은 늘어난다. KcBERT는 AdamW 0.00002, 선형은 SGD 0.1이며 정상 자료를 섞지 않았다. 조건마다 원본에서 다시 시작했다.','','학습한 문자와 그 특징이 같은 문자를 모든 비교군의 평가에서 동일하게 제외했다. 전체 KISA 평가 대상은 두 건 학습에서20건, 세 건 학습에서19건이며, 특징 중복이 있으면 더 줄어든다. 표의 미탐 회복 분모는 이 평가 대상 중 해당 모델이 원래 놓친 건수다. 별도로 K01~K09 안의 남은7건·6건을 공통 사례로 집계했다. 한 건 대조군과 세 건에 대한 두 건 대조군도 각각 대상 학습 묶음 전체를 제외한 동일한 평가 대상에서 재집계했다. 원래 맞힌 사례는 회복으로 세지 않는다.','','## 전체 결과','','| 학습 사례 수 | 업데이트 | 관측 수 | 회복 있고 새 오류 없음 | 학습한 사례도 원래 오답·학습 성공 | 원래 오답 학습 성공·남은 공통 사례 전부 탐지·새 오류 없음 | 원래 오답 학습 성공·한 건 대조군 모두보다 회복 증가·새 오류 없음 |','|---|---:|---:|---:|---:|---:|---:|']
    core=['## 핵심 판정','']
    full=sum(r['totals'][str(k)]['10']['full_common_clean_success'] for k in [2,3])
    if full==0:core+=['최종10회 기준으로, 학습한 사례가 모두 원래 오답이면서 남은 공통 사례를 전부 탐지하고 새 오류도 만들지 않은 조건은 없었다. 두 건·세 건 학습만으로 안전한 개선 모델을 채택할 근거는 확보하지 못했다.','']
    else:core+=[f'최종10회 기준으로 원래 오답인 학습 사례를 모두 학습하고, 남은 공통 사례를 전부 탐지하며 새 오류도 만들지 않은 관측은 {full}개였다. 알려진 사례를 이용한 사후 관측이며 독립 데이터에서 확인하기 전 채택 결과로 해석하지 않는다.','']
    core+=['| 학습 건수 | 최종10회: 원래 오답 학습 성공·일부 회복·새 오류 없음 | 그중 모든 한 건 대조군보다 추가 회복 |','|---|---:|---:|']
    for k in [2,3]:
        a=r['totals'][str(k)]['10'];core.append(f"| {k} | {a['own_missed_supports_learned_clean_recovery']} | {a['clean_gain_over_every_single_control']} |")
    dup=next(m for m in r['models'] if m['id']=='u5_DUP_s42')
    core+=['','기존 증강 모델 DUP42의 결과는 다음과 같다. 학습 사례는 아래 탐지 수에서 제외했다.','',f"학습 전에는 KISA {dup['baseline_kisa_detected']}/22건을 탐지했고 정상 후보 경보는 {dup['baseline_normal_alerts']}/250건이었다.",'','| 학습 건수 | 최종10회: 남은 공통 사례 탐지 | 정상 후보 경보 /250 |','|---|---:|---:|']
    for k in [2,3]:
        ms=[g['steps']['10']['metrics'] for g in dup['groups'] if g['size']==k]
        core.append(f"| {k} | {fmt([min(m['common_detected'] for m in ms),max(m['common_detected'] for m in ms)])}/{9-k} | {fmt([min(m['normal_alerts'] for m in ms),max(m['normal_alerts'] for m in ms)])} |")
    core+=['','정상 경보까지 함께 비교해야 하며, 미탐을 탐지했다는 사실만으로 성능 개선을 주장할 수 없다.','']
    core+=['### 학습 사례 탐지 여부를 별도로 본 제한적 개선','', '다음은 새 오류 없이 모든 한 건 대조군보다 미학습 미탐 회복이 늘어난 관측 전체다. 학습에 사용한 사례를 모두 고쳤다는 조건은 적용하지 않았으므로, 아래 학습 사례 탐지 열을 함께 보아야 한다. 결과를 본 뒤 선택한 종료 시점이나 채택 모델이 아니다.','','| 모델 | 학습 조합 | 업데이트 | 한 건 대조군 회복 | 두·세 건 회복 | 학습 사례 탐지 | 정상 경보 전→후 |','|---|---|---:|---:|---:|---:|---:|']
    for x in r['clean_gains_without_requiring_support_learning']:
        a=x['metrics'];cs=[z['recovered'] for z in x['one_example_controls']]
        core.append(f"| {x['model']} | {x['group_id']} | {x['step']} | {fmt([min(cs),max(cs)])}/{a['miss_denominator']} | {a['recovered']}/{a['miss_denominator']} | {a['support_detected']}/{a['support_count']} | {a['baseline_normal_alerts']}→{a['normal_alerts']} |")
    if not r['clean_gains_without_requiring_support_learning']:core.append('| 해당 관측 없음 | — | — | — | — | — | — |')
    core+=['','이 표는 부분적인 미탐 회복을 보여줄 수 있지만, 학습 사례 미탐이 남거나 후속 업데이트에서 정상 경보가 증가한다면 그대로 적용할 근거는 부족하다. 학습 건수와 업데이트 수를 늘릴수록 좋아진다는 결론도 내릴 수 없다.','']
    lines[2:2]=core
    for k,ss in r['totals'].items():
        for st,a in ss.items():lines.append(f"| {k} | {st} | {a['observations']} | {a['clean_recovery']} | {a['own_missed_supports_learned_clean_recovery']} | {a['full_common_clean_success']} | {a['clean_gain_over_every_single_control']} |")
    lines+=['','“새 오류 없음”은 평가한 기존 탐지를 잃지 않고, 정상 후보250건에 새 경보도 발생하지 않았다는 뜻이다. 정상 후보는 원 데이터의 정상 라벨(__NORMAL_SOURCE_SPLITS__)이며 실서비스 오탐률이 아니다. 이 점검은 기존 U5 전체 테스트셋의 회귀 평가를 대신하지 않는다. 원래 탐지하던 학습 사례를 다시 학습한 관측과, 해당 모델의 오답을 학습한 관측을 구분했다.','','## 계열별 최종 10회 결과','','| 계열 | 학습 건수 | 관측 | 전체 KISA 평가의 기존 미탐 회복 범위 | 정상 후보 경보 /250 | 회복·새 오류 없음 | 원래 오답 학습 성공·모든 한 건 대조군보다 회복 증가·새 오류 없음 |','|---|---:|---:|---:|---:|---:|---:|']
    for f,ss in r['families'].items():
        for k,st in ss.items():
            a=st['10']
            recovery='대상 없음 (기존 미탐0)' if a['miss_denominator_range'][1]==0 else f"{fmt(a['recovery_range'])} / {fmt(a['miss_denominator_range'])}"
            lines.append(f"| {f} | {k} | {a['observations']} | {recovery} | {fmt(a['normal_alert_range'])} | {a['clean_recovery']} | {a['clean_gain_over_every_single_control']} |")
    lines+=['','범위는 각 계열의 모든 시드·fold와 해당 크기의 고정 조합에 걸친 최솟값~최댓값이다. 분자·분모의 최솟값끼리가 같은 관측일 필요는 없으며, 개별 값은 집계 JSON에 보존했다.','','## 앞선 개선 후보의 경과','','| 모델 | 학습 조합 | 업데이트 | 미학습 미탐 회복 | 같은 평가 대상의 한 건 대조군 회복 | 정상 경보 | 새 정상 경보 | 기존 탐지 손실 |','|---|---|---:|---:|---:|---:|---:|---:|']
    for m in r['models']:
        if m['id'] not in ['LR_C_s404_f1','fage_no_kcbert_s303']:continue
        for g in m['groups']:
            for st in ['5','10']:
                x=g['steps'][st];a=x['metrics'];cr=[x['recovered'] for x in x['one_example_controls']]
                lines.append(f"| {m['id']} | {'+'.join(g['support_cases'])} | {st} | {a['recovered']}/{a['miss_denominator']} | {fmt([min(cr),max(cr)])}/{a['miss_denominator']} | {a['normal_alerts']} | {a['new_normal_alerts']} | {a['new_misses']} |")
    lines+=['','이 두 조건은 앞선 한 건 실험에서 보였던 개선 신호를 추적하기 위해 표시했다. 이번 결과에서 가장 좋은 조건을 골라낸 표가 아니다. 전체 모델·조합·1/5/10회 결과는 [생성 집계](../reports/generated/kisa_few_example_20261004.json)에 포함했다.','','## 검증과 한계','',f"추가학습 예측 {v['actual_adapted_prediction_rows']:,}개와 동일 평가 대상을 사용한 전이 계산 {v['matched_transition_evaluations']:,}개를 별도로 검산했다. 원본과 의존 파일 {v['bound_source_files']}건의 해시를 확인했고, 선형 업데이트는 전체 계수로 독립 재구성했다.",'','검증 코드는 저장된 신경망 확률을 검산했다. 적응한 신경망 전체 가중치를 보관하지 않았으므로 해당 가중치를 다시 불러온 독립 추론 검증을 주장하지 않는다. 원본 모델·이전 한 건 결과는 보존했으며 배포 모델을 변경하지 않았다.','','- 알려진 오류와 앞선 결과를 본 뒤 설계한 사후 진단이다. 새로운 독립 데이터의 일반화 성능이 아니다.','- 반복한 시드·학습 조합·과거 변형 중에는 같은 계수의 조건도 있다. 관측 수를 독립 표본 수로 볼 수 없다.','- 신경망은128토큰, TF-IDF는원래 전체 문자 입력을 쓰고 업데이트 방식도 다르다. 모델 구조 자체의 우열로 해석하지 않는다.','- 가중치가 없는 과거 조건, 외부 JEV와 URL HGB 온라인 추가학습은 앞선 실험과 같은 이유로 제외했다. URL 전문가는 고정했다.','- 1·5회는 사전에 정한 중간 점검이다. 결과를 보고 학습률·임계값·종료 시점을 바꾸지 않았으며, 개선 관측은 별도 신규 자료에서 검증해야 한다.','','## 실행 및 근거','','```bash','python3 scripts/kisa_few_example_common_20261004.py prepare','python3 tmp/kisa_few_example_20261004/run_sweep.py','python3 scripts/run_kisa_few_example_linear_20261004.py run','python3 tmp/kisa_few_example_20261004/verify_actual_updates.py','python3 scripts/analyze_kisa_few_example_20261004.py','python3 scripts/analyze_kisa_few_example_20261004.py --check','python3 scripts/harness/cli.py verify kisa-few-example-run-20261004','```','','[메인 검산](../tmp/kisa_few_example_20261004/main_validation.json) · [코드 검토](../tmp/kisa_few_example_20261004/code_review.md) · [Orca 정산](../tmp/kisa_few_example_20261004/orca_accounting.json)','']
    metadata=r['input_metadata'];splits=metadata['normal_source_splits']
    text='\n'.join(lines)
    text=text.replace('__NORMAL_SOURCE_SPLITS__',f"train{splits.get('train',0)}·validation{splits.get('validation',0)}")
    return text

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    result,validation=run();doc=markdown(result,validation)
    if args.check:
        assert c.load(PUBLIC)==result and DOC.read_text()==doc and c.load(TMP/'main_validation.json')==validation
        print('PASS all263 conditions, exact support groups, matched controls and public results')
    else:
        PUBLIC.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n');DOC.write_text(doc)
        (TMP/'main_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
        print('Wrote verified few-example result',result['totals'])
