"""Independent stdlib transition audit; no experiment metric functions imported."""
import hashlib,json,math,statistics
from pathlib import Path
from collections import defaultdict
R=Path('${PROJECT_ROOT}');P=Path.home()/'scamlens_private';T=R/'tmp/kisa_all_models_20261004'
def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def independent(base,after,support,threshold,exclude=()):
 assert len(base)==len(after)==272
 assert all(math.isfinite(p) and 0<=p<=1 for p in base+after)
 b=[p>=threshold for p in base];a=[p>=threshold for p in after]
 held=[i for i in range(22) if i!=support and i not in exclude];common=[i for i in range(9) if i!=support and i not in exclude]
 miss=[i for i in held if not b[i]];prior=[i for i in held if b[i]]
 rec=sum(a[i] for i in miss);new_miss=sum(not a[i] for i in prior);new_fp=sum(a[i] and not b[i] for i in range(22,272))
 return {'recovered':rec,'miss_denominator':len(miss),'common_detected':sum(a[i] for i in common),'common_recovered':sum(a[i] and not b[i] for i in common),'common_denominator':len(common),'new_misses':new_miss,'retained':sum(a[i] for i in prior),'retention_denominator':len(prior),'normal_alerts':sum(a[22:]),'new_normal_alerts':new_fp,'resolved_normal_alerts':sum(b[i] and not a[i] for i in range(22,272)),'clean_recovery':bool(rec and not new_miss and not new_fp),'all_misses_recovered':bool(miss and rec==len(miss)),'support_detected':a[support]}
def one_model_summary(mid,family,kind,base,threshold,folds):
 return {'id':mid,'family':family,'kind':kind,'baseline_kisa_detected':sum(x>=threshold for x in base[:22]),'baseline_normal_alerts':sum(x>=threshold for x in base[22:]),'folds':folds}

def main():
 k=load(P/'kisa_ocr_diagnostics_20260921_v1/kisa_inputs.json');normal=load(P/'kisa_ocr_diagnostics_20260921_v1/normal_candidates.json')
 ids=[f'K{i:02d}' for i in range(1,23)]+[r['candidate_id'] for r in normal]
 assert len(set(ids))==272
 models=[];checks=0;prediction_rows=0;input_hashes=0
 neural_plan=load(R/'docs/experiments/KISA_ALL_MODELS_NEURAL_PLAN_20261004.json')
 npth=P/neural_plan['output_dir'];prep=load(npth/'prepare_manifest.json')
 for field,actual in [('plan_sha256',R/'docs/experiments/KISA_ALL_MODELS_NEURAL_PLAN_20261004.json'),('runner_sha256',R/'scripts/run_kisa_all_models_neural_20261004.py'),('kisa_input_sha256',P/neural_plan['input_dir']/'kisa_inputs.json'),('normal_input_sha256',P/neural_plan['input_dir']/'normal_candidates.json'),('prior_baseline_reference_sha256',Path(prep['prior_baseline_reference_path']))]:assert sha(actual)==prep[field];input_hashes+=1
 for mid,mm in prep['models'].items():
  for fname,h in mm['model_files'].items():assert sha(Path(mm['model_dir'])/fname)==h;input_hashes+=1
  assert sha(mm['threshold_source'])==mm['threshold_source_sha256'];input_hashes+=1
 def array(data):
  rows=data['kisa_records']+data['normal_records'];d={r.get('case_id',r.get('candidate_id')):r for r in rows};assert len(d)==272 and set(d)==set(ids)
  return [d[i]['prob'] for i in ids],d
 for spec in neural_plan['models']:
  mid=spec['id'];md=npth/mid;br=load(md/'baseline_predictions.json');base,bmap=array(br);receipt=load(md/'completion_receipt.json');assert receipt['baseline_sha256']==sha(md/'baseline_predictions.json')
  assert br['kisa_detected']==sum(p>=spec['threshold'] for p in base[:22]);assert br['normal_alerts']==sum(p>=spec['threshold'] for p in base[22:])
  if mid=='u5_DUP_s42':
   prior=load(prep['prior_baseline_reference_path']);ref={f"K{r['template_index']+1:02d}":r['baseline_prob'] for r in prior['kisa_replay']};ref.update({r['candidate_id']:r['baseline_prob'] for r in prior['normal_replay']})
   assert all(abs(base[i]-ref[c])<=1e-5 and (base[i]>=spec['threshold'])==(ref[c]>=spec['threshold']) for i,c in enumerate(ids))
  folds=[]
  for support in range(9):
   fid=f'fold_K{support+1:02d}';file=md/(fid+'.json');fd=load(file);assert receipt['fold_hashes'][fid]==sha(file) and fd['support_template_index']==support
   assert set(fd['training_losses'])=={str(i) for i in range(1,11)} and all(math.isfinite(x) for x in fd['training_losses'].values())
   assert len(fd['final_state_sha256'])==64 and math.isfinite(fd['param_delta_l2_norm']) and fd['param_delta_l2_norm']>0
   steps={}
   for step in ['1','5','10']:
    dat=fd['steps'][step];after,amap=array(dat)
    for i,c in enumerate(ids):assert amap[c]['baseline_prob']==base[i] and amap[c]['baseline_pred']==int(base[i]>=spec['threshold'])
    own=independent(base,after,support,spec['threshold']);m=dat['metrics']
    mapping={'recovered':('held_out_baseline_misses','recovered_count'),'miss_denominator':('held_out_baseline_misses','denominator'),'common_detected':('common_other_eight','detected_count'),'common_recovered':('common_other_eight','recovered_count'),'new_misses':('retention','newly_missed_count'),'retained':('retention','retained_count'),'retention_denominator':('retention','denominator'),'normal_alerts':('normal_regression','total_alerts'),'new_normal_alerts':('normal_regression','new_alerts'),'resolved_normal_alerts':('normal_regression','resolved_alerts'),'clean_recovery':('verdicts','clean_recovery')}
    for key,(a,b) in mapping.items():assert own[key]==m[a][b],(mid,support,step,key)
    steps[step]=own;checks+=1;prediction_rows+=272
   folds.append({'support':f'K{support+1:02d}','support_baseline_detected':bool(base[support]>=spec['threshold']),'steps':steps})
  models.append(one_model_summary(mid,spec['family'],'neural',base,spec['threshold'],folds))
 linear_plan=load(R/'docs/experiments/KISA_ALL_MODELS_LINEAR_PLAN_20261004.json');lp=P/linear_plan['output_dir'];lprep=load(lp/'prepare.json');completion=load(lp/'completion.json')
 for p,h in lprep['files'].items():assert sha(p)==h;input_hashes+=1
 assert set(completion['models'])=={s['id'] for s in linear_plan['models']}
 for spec in linear_plan['models']:
  mid=spec['id'];file=lp/(mid+'.json');dat=load(file);assert sha(file)==completion['models'][mid] and dat['row_ids']==ids
  base=dat['baseline_probabilities'];folds=[]
  for support,fd in enumerate(dat['folds']):
   assert fd['support']==support;steps={}
   for step in ['1','5','10']:
    sd=fd['steps'][step];own=independent(base,sd['probabilities'],support,spec['threshold'],fd['collisions']);m=sd['metrics']
    mapping={'recovered':'recovered','miss_denominator':'remaining_baseline_misses','common_detected':'common_other_detected','common_recovered':'common_other_recovered','common_denominator':'common_other_denominator','new_misses':'new_misses','retained':'retained','retention_denominator':'prior_detection_denominator','normal_alerts':'normal_alerts','new_normal_alerts':'new_normal_alerts','resolved_normal_alerts':'resolved_normal_alerts','clean_recovery':'clean_recovery'}
    for key,k2 in mapping.items():assert own[key]==m[k2],(mid,support,step,key)
    steps[step]=own;checks+=1;prediction_rows+=272
   folds.append({'support':f'K{support+1:02d}','support_baseline_detected':bool(base[support]>=spec['threshold']),'steps':steps})
  models.append(one_model_summary(mid,spec['family'],spec['kind'],base,spec['threshold'],folds))
 assert len(models)==len(neural_plan['models'])+len(linear_plan['models'])
 fams=defaultdict(list)
 for m in models:fams[m['family']].append(m)
 families=[]
 span=lambda xs:[min(xs),max(xs)]
 for family,ms in fams.items():
  result={'family':family,'conditions':len(ms),'kind':ms[0]['kind'],'baseline_kisa_detected_range':span([m['baseline_kisa_detected'] for m in ms]),'baseline_normal_alert_range':span([m['baseline_normal_alerts'] for m in ms]),'steps':{}}
  for step in ['1','5','10']:
   vs=[f['steps'][step] for m in ms for f in m['folds']]
   result['steps'][step]={'fold_observations':len(vs),'other_eight_detection_range':span([v['common_detected'] for v in vs]),'new_normal_alert_range':span([v['new_normal_alerts'] for v in vs]),'normal_alert_range':span([v['normal_alerts'] for v in vs]),'recovery_range':span([v['recovered'] for v in vs]),'remaining_miss_denominator_range':span([v['miss_denominator'] for v in vs]),'any_recovery_folds':sum(v['recovered']>0 for v in vs),'clean_recovery_folds':sum(v['clean_recovery'] for v in vs),'complete_clean_recovery_folds':sum(v['clean_recovery'] and v['all_misses_recovered'] for v in vs),'new_miss_range':span([v['new_misses'] for v in vs])}
  families.append(result)
 stage_totals={}
 clean_examples=[]
 for step in ['1','5','10']:
  pairs=[(m,f) for m in models for f in m['folds']]
  clean=[(m,f) for m,f in pairs if f['steps'][step]['clean_recovery']]
  own_missed=[(m,f) for m,f in pairs if not f['support_baseline_detected']]
  stage_totals[step]={'observations':len(pairs),'clean_recovery_observations':len(clean),'clean_recovery_conditions':len({m['id'] for m,f in clean}),'support_was_missed_observations':len(own_missed),'support_was_missed_clean_recovery_observations':sum(f['steps'][step]['clean_recovery'] for m,f in own_missed),'neural_clean_recovery_observations':sum(m['kind']=='neural' for m,f in clean),'complete_clean_recovery_observations':sum(f['steps'][step]['all_misses_recovered'] for m,f in clean)}
  stage_totals[step]['missed_support_learned_and_common_eight_detected_with_clean_recovery']=sum(f['steps'][step]['clean_recovery'] and f['steps'][step]['support_detected'] and f['steps'][step]['common_denominator']==8 and f['steps'][step]['common_detected']==8 for m,f in own_missed)
  if step=='10':
   for m,f in clean:
    clean_examples.append({'id':m['id'],'support':f['support'],'support_baseline_detected':f['support_baseline_detected'],'baseline_kisa_detected':m['baseline_kisa_detected'],'baseline_normal_alerts':m['baseline_normal_alerts'],**f['steps'][step]})
 inventory=load(T/'inventory_review.json')
 unavailable=[{'family':'Original KcBERT seed14-17','status':'missing_weights','reason':'Historical scratchpad weights absent; metric JSON only.'},{'family':'Matched 20260917 BASE/DUP/FLIP (15 runs) + two-track','status':'missing_weights','reason':'Predictions remain, original fitted weights absent; U5 successors tested separately.'},{'family':'JEV API / fusion KJ,KJU','status':'not_tested','reason':'No local trainable JEV model or new-case JEV features; no external transmission performed.'},{'family':'URL HGB','status':'baseline_only','reason':'Saved tree ensemble has no one-example online update; fitting with replay is a different future protocol.'},{'family':'ONNX / temperature calibration','status':'derived_export_not_separate_training','reason':'Same source neural weights. Calibration is a postprocessing step without a separately recorded binary-adaptation threshold.'},{'family':'always normal / always malicious / URL-present rule','status':'no_trainable_parameters','reason':'Fixed rules cannot learn an additional example.'},{'family':'next action backoff','status':'different_task','reason':'Action prediction, not binary normal/smishing.'},{'family':'early URL-free pilot','status':'no_saved_weights','reason':'Original pilot predictions retained; persisted successor LR-A/B/C models were tested.'}]
 summary={'status':'completed','neural_checkpoints':len(neural_plan['models']),'linear_and_derived_conditions':len(linear_plan['models']),'family_count':len(families),'all_conditions':len(models),'families':families,'models':models,'unavailable_or_non_adaptable':unavailable,'url_baseline':load(lp/'url_mapping_audit.json')['URL_baseline'],'limitations':['Known-error post-hoc diagnostic on the same22 KISA and250 development normal candidates; not prospective or operational FPR.','Repeated seeds/folds/support choices are not independent examples.','Neural AdamW2e-5 and logistic SGD0.1 are different frozen family recipes, not an architecture ranking.','Support excluded from recovery and retention; common8 already-detected cases are not recoveries.','Learned gates freeze experts; fixed combiner readouts use separately adapted text experts.','KISA22 are18 similarity groups; duplicate first128-token inputs exist outside support.','Canonical source URL ambiguity in3 templates, selected by fixed lowest audit index.','Any zero-new-error recovery is a diagnostic candidate, not deployment approval.']}
 summary['stage_totals']=stage_totals
 summary['primary_step']='10'
 summary['primary_clean_examples']=clean_examples
 summary['illustrative_intermediate_condition']={'id':'LR_C_s404_f1','selection':'Retrospectively selected illustration from predefined intermediate checkpoints; not a selected best model or tuned stopping rule.'}
 summary['trainable_conditions']=sum(m['kind'] not in ['derived_ensemble','original_fixed','raw_neural_derived'] for m in models)
 summary['limitations'].append('TF-IDF uses full normalized text, while KcBERT uses its original first128-token window; no matched-input architecture claim.')
 summary['limitations'].append('A support missed by original DUP42 may already be detected by another model; each fold records this and the own-missed-support subset separately.')
 gradient=load(T/'linear_update_validation.json')
 assert gradient['status']=='passed' and gradient['logistic_conditions']==224 and gradient['probability_rows_checked']==224*9*3*272 and gradient['max_probability_difference']<1e-10
 assert summary['trainable_conditions']==summary['neural_checkpoints']+gradient['logistic_conditions']
 collisions=load(T/'input_collision_validation.json')
 assert collisions['status']=='checked' and collisions['linear_conditions']==gradient['logistic_conditions'] and collisions['support_normal_collision_pairs']==0
 assert sum(len(g['model_ids']) for g in collisions['neural'])==summary['neural_checkpoints']
 public=R/'reports/generated/kisa_all_models_summary_20261004.json';public.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 validation={'status':'passed','independent_method':'stdlib probability thresholding and transition counts; no runner metric functions','conditions':len(models),'fold_checkpoint_groups':checks,'adapted_prediction_rows':prediction_rows,'original_and_dependency_hashes_verified':input_hashes,'model_inventory_source_sha256':sha(T/'inventory_review.json'),'summary_sha256':sha(public)}
 validation['independent_full_vector_linear_update_validation']=gradient
 validation['independent_linear_update_validation_sha256']=sha(T/'linear_update_validation.json')
 validation['audit_source_sha256']=sha(__file__)
 validation['support_normal_input_collision_audit']={k:v for k,v in collisions.items() if k not in ('linear','neural')}
 validation['support_normal_input_collision_audit_sha256']=sha(T/'input_collision_validation.json')
 validation['neural_verifier_repair_source_sha256']=sha(R/'scripts/verify_kisa_all_models_neural_20261004.py')
 (T/'main_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
 def fmt(r):return str(r[0]) if r[0]==r[1] else f'{r[0]}–{r[1]}'
 primary=stage_totals['10']
 lines=['# 기존 전체 모델의 한 건 추가학습 검증','','## 결과와 판단',f"저장된 {summary['all_conditions']}개 조건에서 한 건씩 추가학습하거나 그 결과를 결합해 검증했다. 사전에 고정한 10회 업데이트 기준, 회복이 있으면서 새 오류가 없는 결과는 {primary['clean_recovery_observations']}/{primary['observations']}개 관측이다. 그중 학습에 쓴 사례를 해당 모델도 원래 놓쳤던 경우는 {primary['support_was_missed_clean_recovery_observations']}/{primary['support_was_missed_observations']}개 관측이다.", '','9가지 학습 사례 선택과 여러 시드·모델을 같은 자료에서 비교한 탐색 실험이다. 일부 개선 관측을 배포 모델 선정의 근거로 삼지 않고 기존 모델을 보존한다. 알려진 오류 한 건만 반복 학습했을 때의 회복과 정상 후보 오탐 변화를 확인한 결과로 해석한다.','','## 실행 범위',f"저장된 KcBERT {summary['neural_checkpoints']}개 체크포인트와 선형·결합 {summary['linear_and_derived_conditions']}개 조건을 검증했다. 같은 9건을 각각 한 건씩 골라 원본에서 새로 시작했다. 시드·fold·과거 삭제/가중 변형을 포함한 조건 수이며 서로 다른 구조의 모델 수가 아니다.",'','- 학습 사례는 기존 DUP seed42가 놓친 K01~K09다. 다른 모델은 이 사례를 원래 탐지할 수 있으므로 각 모델의 학습 전 판정을 별도로 기록했다.','- 학습에 쓴 한 건을 제외한 공통 여덟 건과, 해당 모델이 다른 KISA 사례에서 놓쳤던 사례들의 회복을 각각 계산했다. 같은 특징으로 인코딩된 학습 사례의 복제는 해당 평가에서 제외했다.','- 원래 임계값과 전처리를 고정했다. KcBERT는 AdamW 0.00002, 선형 모델은 SGD 0.1로 10회 업데이트했다. 1·5회는 변화 경로를 보여 주는 보조 결과이며, 결과를 보고 최종 업데이트 수를 고르지 않았다.','- 결합 학습 모델은 기존 전문가를 고정한 채 결합 계수만 학습했다. 고정·동일 가중 결합은 별도로 적응시킨 문자 전문가를 조합했고 URL 전문가는 고정했다.','- 정상 후보 250건은 원 데이터의 정상 라벨을 사용한 개발 자료(train 199, validation 51)다. 독립적으로 확인한 정상 모집단이나 실제 서비스 오탐률이 아니다.','- TF-IDF는 정규화 문자 전체, KcBERT는 기존 128토큰 범위를 사용한다. 입력 범위와 추가학습 방식이 달라 구조 자체의 우열로 해석할 수 없다.','','## 최종 업데이트 10회 결과','', '| 계열 | 조건 수 | KISA 탐지 전 /22 | 정상 경보 전 /250 | 나머지8 탐지 후 | 정상 경보 후 /250 | 회복 있고 새 오류 없는 반복 |','|---|---:|---:|---:|---:|---:|---:|']
 for f in families:
  s=f['steps']['10'];lines.append(f"| {f['family']} | {f['conditions']} | {fmt(f['baseline_kisa_detected_range'])} | {fmt(f['baseline_normal_alert_range'])} | {fmt(s['other_eight_detection_range'])} | {fmt(s['normal_alert_range'])} | {s['clean_recovery_folds']}/{s['fold_observations']} |")
 lines+=['','범위는 해당 계열의 모든 시드·fold와 9가지 학습 사례에 걸친 최솟값~최댓값이다. 나머지8 탐지에는 원래 탐지하던 문자도 포함된다. 회복은 학습 전 놓친 사례가 탐지로 바뀐 경우만 별도로 계산했다. 마지막 열은 미학습 사례 회복이 한 건 이상이면서 기존 탐지를 잃지 않고 새 정상 후보 경보도 없는 반복 수다. 전체 미탐 회복과는 구분한다.']
 lines+=['','## 새 오류 없이 회복한 개별 관측','']
 if not clean_examples:lines.append('사전에 고정한 최종 업데이트 시점에서 해당 관측은 없었다.')
 for c in clean_examples:
  support_note='학습 사례를 이 모델은 원래 탐지했다. 따라서 이 모델 자신의 오답 한 건을 학습한 결과로 표현할 수 없다.' if c['support_baseline_detected'] else '학습 사례도 이 모델이 원래 놓친 사례였다.'
  lines.append(f"- **{c['id']}, {c['support']} 학습**: 학습에 쓰지 않은 기존 미탐 {c['miss_denominator']}건 중 {c['recovered']}건 회복, 기존 탐지 {c['retention_denominator']}건 중 {c['retained']}건 유지. 정상 후보 경보 {c['baseline_normal_alerts']}→{c['normal_alerts']}/250건, 새 경보 {c['new_normal_alerts']}건. {support_note}")
 lines+=['','## 업데이트 횟수별 경과','','| 업데이트 | 전체 관측 | 회복 있고 새 오류 없는 관측 | 해당 모델의 오답을 학습한 관측 중 같은 결과 | 오답 학습 성공 + 다른8 모두 탐지 + 새 오류 없음 |','|---|---:|---:|---:|---:|']
 for step,t in stage_totals.items():lines.append(f"| {step} | {t['observations']} | {t['clean_recovery_observations']} | {t['support_was_missed_clean_recovery_observations']}/{t['support_was_missed_observations']} | {t['missed_support_learned_and_common_eight_detected_with_clean_recovery']} |")
 demo=next(m for m in models if m['id']==summary['illustrative_intermediate_condition']['id'])
 clean5=[f for f in demo['folds'] if not f['support_baseline_detected'] and f['steps']['5']['clean_recovery'] and f['steps']['5']['support_detected']]
 lines+=['','## 중간 점검에서 확인한 개선 사례','',f"**{demo['id']}**는 문자 TF-IDF 선형 모델의 C 조건(URL 없는 스미싱 상대 가중치 증가), seed404·fold1이다. 학습 전 KISA {demo['baseline_kisa_detected']}/22건 탐지, 정상 후보 경보 {demo['baseline_normal_alerts']}/250건이었다. 다음 표에 이 조건의 모든 학습 사례 선택 결과를 함께 제시한다.",'','| 학습 사례 | 1회 미학습 미탐 회복 | 1회 정상 경보 | 5회 미학습 미탐 회복 | 5회 정상 경보 | 10회 미학습 미탐 회복 | 10회 정상 경보 |','|---|---:|---:|---:|---:|---:|---:|']
 for f in demo['folds']:
  cells=[]
  for st in ['1','5','10']:
   v=f['steps'][st];cells.extend([f"{v['recovered']}/{v['miss_denominator']}",str(v['normal_alerts'])])
  lines.append('| '+f['support']+' | '+' | '.join(cells)+' |')
 if clean5:
  supports='·'.join(f['support'] for f in clean5)
  ds=[f['steps']['5'] for f in clean5]
  lines.append(f"\n{supports} 중 한 건을 학습한 {len(clean5)}개 반복의 5회 시점에서는 학습한 한 건도 정탐으로 바뀌었고, 학습하지 않은 미탐 {fmt(span([v['miss_denominator'] for v in ds]))}건 중 {fmt(span([v['recovered'] for v in ds]))}건을 회복했다. 기존 탐지 {fmt(span([v['retention_denominator'] for v in ds]))}건을 모두 유지했고 정상 후보 경보는 {demo['baseline_normal_alerts']}→{fmt(span([v['normal_alerts'] for v in ds]))}건이었다. 같은 반복의 10회 시점 경보는 {fmt(span([f['steps']['10']['normal_alerts'] for f in clean5]))}건으로 늘었다.")
 lines+=['','이 조건은 결과를 본 뒤 설명용으로 고른 탐색 사례다. 미리 정한 1·5·10회 점검 중 5회에서 개선을 관측했다는 뜻이며, 5회가 최적이라는 검증이나 이 조건의 우월성을 주장하지 않는다. 같은 모델·같은 사례에서 반복한 관측은 서로 독립적인 검증이 아니다. 별도 자료에서 검증하기 전에는 최종 모델로 채택하지 않는다.']
 lines+=['','## 조건별 결과와 한계','','[신경망 상세](KISA_ALL_MODELS_NEURAL_RESULT_20261004.md), [선형·결합 상세](KISA_ALL_MODELS_LINEAR_RESULT_20261004.md), [전체 집계 JSON](../reports/generated/kisa_all_models_summary_20261004.json)에 1·5·10회와 모든 사례 선택 결과를 보존했다. 신경망 상세 표의 기존 열명 “무오류 완전 복구”는 해당 코드상 한 건 이상 회복을 뜻하므로, 본 통합 보고서의 정의와 수치를 해석 기준으로 사용한다.','','## 실행하지 못한 모델 및 적용하지 않은 항목','']
 for u in unavailable:lines.append(f"- **{u['family']}**: {u['reason']}")
 url=summary['url_baseline']
 lines+=['',f"URL HGB의 원본 탐지는 KISA {url['kisa_detected']}/{url['kisa_denominator']}건이었다. URL이 있는 정상 후보 {url['normal_with_URL_denominator']}건 중 {url['normal_with_URL_alerts']}건에 경보가 있었고, URL 없는 {url['normal_without_URL_abstained']}건은 판정 대상에서 제외했다. 추가학습 결과가 아니며 전체 정상 후보를 분모로 한 오탐률로 표시하지 않는다.",'','## 검증',f"저장된 추가학습 예측 {prediction_rows:,}행, {checks:,}개 모델·학습사례·체크포인트 묶음을 별도 계산으로 검산했다. 원본과 의존 산출물 해시 {input_hashes}건을 확인했다.",f"선형 학습 {gradient['logistic_conditions']}개 조건은 원래 전체 계수·절편으로부터 실제 SGD 업데이트를 별도로 재구성했다. 예측 {gradient['probability_rows_checked']:,}개 비교의 최대 확률 차이는 {gradient['max_probability_difference']:.3g}였다. 신경망은 저장된 예측을 검산했으며, 추가학습 가중치를 영구 보관하지 않았으므로 그 가중치를 다시 불러온 독립 추론 검증을 주장하지 않는다.",'','[메인 검산 기록](../tmp/kisa_all_models_20261004/main_validation.json), [독립 코드 검토](../tmp/kisa_all_models_20261004/code_review.md), [Orca 자원 정산](../tmp/kisa_all_models_20261004/orca_accounting.json).','','자동 검사에서 발견한 문자열 키 정렬 오류는 [별도 검증기 수정 기록](../tmp/kisa_all_models_20261004/verifier_fix.md)에 남겼다. 두 키 비교만 고쳤으며, 실험 코드·가중치·예측·분모·판정 기준은 그대로 유지했다.','','## 실행 명령','', '```bash','python3 scripts/run_kisa_all_models_neural_20261004.py prepare','python3 tmp/kisa_all_models_20261004/run_neural_sweep.py','python3 scripts/run_kisa_all_models_linear_20261004.py prepare','python3 scripts/run_kisa_all_models_linear_20261004.py run','python3 scripts/verify_kisa_all_models_neural_20261004.py','python3 scripts/run_kisa_all_models_linear_20261004.py check','python3 tmp/kisa_all_models_20261004/verify_linear_updates.py','python3 tmp/kisa_all_models_20261004/verify_input_collisions.py','python3 tmp/kisa_all_models_20261004/verify_and_summarize.py','python3 scripts/harness/cli.py verify kisa-all-models-run-v2-20261004','python3 scripts/harness/cli.py status kisa-all-models-run-v2-20261004','```','','실행 순서는 공통 입력·코드 검사 → 신경망 우선 6개 조건 → 해당 예측을 고정해 선형·결합 실행 → 나머지 신경망 완료 → 통합 검산이다. 위 명령은 사용한 진입점 기록이다. 기존 출력 폴더에서 실행하면 완료 결과를 검증·재사용하며 부분 결과나 입력 변경은 실패 처리한다. 독립 재실행은 별도 출력 경로와 새로 고정한 계획으로 수행해야 한다.','','## 해석의 범위','','- 같은 KISA 22건과 개발 정상 후보 250건에서 확인한 사후 진단이다. 새로운 독립 데이터에서의 일반화 성능이 아니다.','- 같은 사례를 시드와 학습 사례 선택만 바꿔 반복한 관측은 독립 표본이 아니다. 다수 비교에서 발견한 한 조건을 최종 모델로 채택하지 않았다.','- KISA 22건은 유사 문자 18그룹이다. 학습 사례 밖에는 앞 128토큰이 같은 입력도 있어 건별 결과를 독립 사건 수로 해석하지 않는다.','- URL 특징이 서로 다른 원천 후보가 같은 정규화 본문으로 합쳐진 사례가 3건 있다. 사전에 고정한 최소 audit_index 선택을 따랐다. URL에 접속하지 않았다.','- 다음 검증이 필요하다면 원래 정상·스미싱 자료를 섞는 재학습 조건을 먼저 고정하고, 별도의 신규 사례와 정상 자료로 평가해야 한다. 이번 실험에서는 이 후속 실험을 수행하지 않았다.','']
 formatted=[]
 for i,line in enumerate(lines):
  formatted.append(line)
  if line.startswith('#') and i+1<len(lines) and lines[i+1]:formatted.append('')
 (R/'docs/KISA_ALL_MODELS_RESULT_20261004.md').write_text('\n'.join(formatted))
 print(json.dumps(validation,indent=2))
if __name__=='__main__':main()
