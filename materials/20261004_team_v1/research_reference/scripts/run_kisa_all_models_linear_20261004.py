#!/usr/bin/env python3
"""Frozen-feature one-example logistic adaptation; private offline experiment."""
from __future__ import annotations
import os
for _var in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    os.environ[_var] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
import argparse, csv, hashlib, json, math, sys, fcntl
from pathlib import Path
from collections import defaultdict
import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.special import expit
from sklearn.metrics.pairwise import cosine_similarity
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from scamlens.preprocessing import extract_urls, neutralize_url_placeholder
from scamlens.url_features import lexical_features
from scamlens.sms_action_features import SmsActionCueTransformer
from scamlens.fage import EXPERT_ORDER, expert_availability, context_from_experts, equal_weight_scores, fixed_weight_scores
PLAN = ROOT/'docs/experiments/KISA_ALL_MODELS_LINEAR_PLAN_20261004.json'
PRIVATE = Path.home()/'scamlens_private'
OUT = PRIVATE/'kisa_all_models_linear_20261004_v1'
NEURAL = PRIVATE/'kisa_all_models_neural_20261004_v1'
PUBLIC = ROOT/'reports/generated/kisa_all_models_linear_20261004.json'
DOC = ROOT/'docs/KISA_ALL_MODELS_LINEAR_RESULT_20261004.md'
STEPS = (1,5,10)

def load(path):
    return json.loads(Path(path).read_text())

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def path(value):
    p=(PRIVATE/value[8:]) if value.startswith('private:') else ROOT/value
    p=p.resolve()
    if not (p.is_relative_to(ROOT) or p.is_relative_to(PRIVATE)):raise ValueError('source path escape')
    return p

def write(pathname, value, private=True):
    p=Path(pathname)
    if private:
        if not p.resolve().is_relative_to(OUT.resolve()):raise ValueError('private output escape')
        p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(p.parent,0o700)
    else:p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp')
    with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600 if private else 0o644),'w') as f:
        f.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

def sources(plan):
    names={PLAN,Path(__file__).resolve(),ROOT/'src/scamlens/preprocessing.py',ROOT/'src/scamlens/url_features.py',ROOT/'src/scamlens/sms_action_features.py',ROOT/'src/scamlens/fage.py',ROOT/'scripts/train_text_baselines.py',ROOT/'data/processed/messages_split.csv',ROOT/'data/processed/message_urls.csv',ROOT/'data/research/url_free_stability_20260909/fold_assignments.csv',ROOT/'models/url/lexical_hist_gradient_boosting.joblib',ROOT/'reports/generated/url_baseline.json',PRIVATE/'external_eval_20260921_v1/evaluation_packet.json'}
    for n in ('kisa_inputs.json','normal_candidates.json'):names.add(PRIVATE/plan['input_dir']/n)
    for m in plan['models']:
        names.add(path(m['source']))
        for k in ('model_path','vectorizer_path'):
            if m.get(k):names.add(path(m[k]))
    # FAGE similarity uses each original fit partition and its frozen vectorizer.
    for seed in (42,101,202,303,404):names.add(ROOT/f'data/research/url_free_stability_20260909/models/seed_{seed}/fold_0/vectorizer.joblib')
    for mid in [f'kcbert_A_s{s}' for s in (42,101,202,303,404)]+['u5_DUP_s42']:
        d=NEURAL/mid
        names.update(d/f for f in ['completion_receipt.json','baseline_predictions.json']+[f'fold_K{i:02d}.json' for i in range(1,10)])
    names.add(NEURAL/'prepare_manifest.json')
    return sorted(names)

def validate_probs(p):
    p=np.asarray(p,dtype=float)
    if p.shape!=(272,) or not np.isfinite(p).all() or (p<0).any() or (p>1).any():raise ValueError('invalid probabilities')
    return p

def metrics(base, after, support, threshold, collisions=()):
    b=validate_probs(base)>=threshold;a=validate_probs(after)>=threshold
    if support not in range(9):raise ValueError('invalid support')
    held=np.array([i for i in range(22) if i!=support and i not in collisions])
    common=np.array([i for i in range(9) if i!=support and i not in collisions])
    miss=held[~b[held]];ret=held[b[held]]
    recovered=int(a[miss].sum());new_miss=int((~a[ret]).sum())
    return {'support_baseline_detected':bool(b[support]),'support_detected':bool(a[support]),'common_other_denominator':len(common),'common_other_detected':int(a[common].sum()),'common_other_baseline_detected':int(b[common].sum()),'common_other_recovered':int((a[common]&~b[common]).sum()),'remaining_baseline_misses':len(miss),'recovered':recovered,'recovery_rate':recovered/len(miss) if len(miss) else None,'prior_detection_denominator':len(ret),'retained':int(a[ret].sum()),'new_misses':new_miss,'normal_denominator':250,'baseline_normal_alerts':int(b[22:].sum()),'normal_alerts':int(a[22:].sum()),'new_normal_alerts':int((a[22:]&~b[22:]).sum()),'resolved_normal_alerts':int((~a[22:]&b[22:]).sum()),'support_equivalent_heldout_indices':list(collisions),'clean_recovery':bool(recovered>0 and new_miss==0 and not (a[22:]&~b[22:]).any())}

def rank_one_adapt(X, coef, intercept, support, learning_rate=.1, clip_norm=1.):
    """Exact full-vector SGD: delta_w = alpha*x_support, delta_b = alpha."""
    X=sparse.csr_matrix(X,dtype=np.float64);w=np.asarray(coef,dtype=float).ravel();b=float(intercept)
    if X.shape[0]!=272 or X.shape[1]!=len(w) or not np.isfinite(X.data).all() or not np.isfinite(w).all() or not math.isfinite(b):raise ValueError('invalid logistic inputs')
    base=np.asarray(X@w).ravel()+b;xs=X.getrow(support)
    norm2=float(xs.multiply(xs).sum());kernel=np.asarray((X@xs.T).toarray()).ravel()+1.
    alpha=0.;steps={};losses=[]
    for step in range(1,11):
        z=float(base[support]+alpha*kernel[support]);prob=float(expit(z));losses.append(float(np.logaddexp(0.,-z)))
        grad=(prob-1.);norm=abs(grad)*math.sqrt(norm2+1.)
        scale=min(1.,clip_norm/max(norm,1e-30))
        alpha-=learning_rate*grad*scale
        if step in STEPS:steps[str(step)]={'probabilities':expit(base+alpha*kernel).tolist(),'alpha':alpha}
    return expit(base),steps,{'alpha_final':alpha,'support_indices':xs.indices.tolist(),'support_values':xs.data.tolist(),'coefficient_delta_l2':alpha*math.sqrt(norm2),'intercept_delta':alpha,'losses':losses}

def feature_collisions(X,support):
    X=sparse.csr_matrix(X)
    return [i for i in range(22) if i!=support and (X.getrow(i)-X.getrow(support)).nnz==0]

def read_inputs(plan):
    k=sorted(load(PRIVATE/plan['input_dir']/'kisa_inputs.json'),key=lambda x:x['template_index'])
    n=load(PRIVATE/plan['input_dir']/'normal_candidates.json')
    if [x['template_index'] for x in k]!=list(range(22)) or len(n)!=250 or len({x['candidate_id'] for x in n})!=250:raise ValueError('input counts/IDs')
    for r in k:
        if hashlib.sha256(r['primary_model_input'].encode()).hexdigest()!=r['primary_model_input_sha256']:raise ValueError('kisa text hash')
    for r in n:
        if hashlib.sha256(r['text_normalized'].encode()).hexdigest()!=r['text_sha256']:raise ValueError('normal text hash')
    return k,n,[r['primary_model_input'] for r in k]+[r['text_normalized'] for r in n]

def url_context(k,n):
    packet=load(PRIVATE/'external_eval_20260921_v1/evaluation_packet.json')
    candidates=defaultdict(list)
    for c in packet['candidates']:candidates[c['primary_model_input_sha256']].append(c)
    url_art=joblib.load(ROOT/'models/url/lexical_hist_gradient_boosting.joblib');cols=url_art['feature_columns']
    table=pd.read_csv(ROOT/'data/processed/message_urls.csv').groupby('message_id',sort=False)
    summaries=[];probs=[];audit=[]
    def summarize(items):
        return [len(items),max((int(x['url_length']) for x in items),default=0),max((float(x['digit_ratio']) for x in items),default=0.),int(any(float(x['has_ip_literal']) for x in items)),int(any(float(x['has_at_symbol']) for x in items))]
    def score(items):
        return float(url_art['model'].predict_proba(pd.DataFrame(items)[cols])[:,1].max()) if items else 0.
    for r in k:
        cs=sorted(candidates[r['primary_model_input_sha256']],key=lambda x:x['audit_index'])
        if not cs:raise ValueError('missing canonical URL source')
        variants=[[lexical_features(u) for u in extract_urls(c['sms_body'])] for c in cs]
        chosen=variants[0]
        summaries.append(summarize(chosen));probs.append(score(chosen))
        signatures={json.dumps([{z:v[z] for z in cols} for v in vv],sort_keys=True) for vv in variants}
        audit.append({'case_id':f"K{r['template_index']+1:02d}",'selected_audit_index':cs[0]['audit_index'],'candidate_count':len(cs),'distinct_url_feature_sets':len(signatures)})
    for r in n:
        items=table.get_group(r['message_id']).to_dict('records') if r['message_id'] in table.groups else []
        summaries.append(summarize(items));probs.append(score(items))
    return np.asarray(summaries,dtype=float),np.asarray(probs),audit

def neural_probs(mid,ids,support=None,step=None):
    d=NEURAL/mid
    receipt=load(d/'completion_receipt.json')
    name='baseline_predictions.json' if support is None else f'fold_K{support+1:02d}.json'
    expected=receipt['baseline_sha256'] if support is None else receipt['fold_hashes'][f'fold_K{support+1:02d}']
    if sha(d/name)!=expected:raise ValueError('neural dependency hash drift')
    data=load(d/name)
    if support is not None:data=data['steps'][str(step)]
    lookup={x.get('case_id',x.get('candidate_id')):x['prob'] for x in data['kisa_records']+data['normal_records']}
    if set(lookup)!=set(ids):raise ValueError('neural dependency IDs')
    return validate_probs([lookup[x] for x in ids])

class Features:
    def __init__(self,plan):
        self.plan=plan;self.k,self.n,self.texts=read_inputs(plan)
        self.ids=[f'K{i+1:02d}' for i in range(22)]+[x['candidate_id'] for x in self.n]
        self.url,self.urlp,self.url_audit=url_context(self.k,self.n)
        self.cache={};self.baselines={};self.gate_cache={}
        self.specs={m['id']:m for m in plan['models']}
    def linear(self,m):
        kind=m['kind'];mp=m.get('model_path')
        if kind=='pipeline':
            native=joblib.load(path(mp));X=native[:-1].transform(self.texts);model=native[-1];reference=native.predict_proba(self.texts)[:,1]
        elif kind in ('linear_arm','word_expert'):
            key=m['vectorizer_path']
            if key not in self.cache:self.cache[key]=joblib.load(path(key)).transform(self.texts)
            X=self.cache[key]
            if m.get('arm')=='B':X=sparse.hstack([X,SmsActionCueTransformer().transform(self.texts)],format='csr')
            model=joblib.load(path(mp));reference=model.predict_proba(X)[:,1]
        elif kind=='bundled_linear':
            bundle=joblib.load(path(mp));model=bundle['model'];X=bundle['vectorizer'].transform(self.texts);reference=model.predict_proba(X)[:,1]
        elif kind=='gate':
            frame=self.gate(m['seed'],m['family']);X=frame[m['features']].to_numpy(float)
            w=np.asarray(m['coef'],float);b=float(m['intercept'])
            if mp:
                native=joblib.load(path(mp));assert np.allclose(native.coef_.ravel(),w,rtol=0,atol=1e-12) and np.isclose(native.intercept_[0],b,rtol=0,atol=1e-12)
                reference=native.predict_proba(X)[:,1]
            else:reference=expit(X@w+b)
            return self.checked(X,w,b,reference)
        elif kind=='original_meta':
            bundle=joblib.load(path(mp));model=bundle['model']
            X=np.column_stack([self.baseline('char_tfidf_lr'),self.urlp,(self.url[:,0]>0).astype(int)])
            if bundle['feature_columns']!=['text_probability','url_probability_filled','has_url']:raise ValueError('meta feature order')
            reference=model.predict_proba(X)[:,1]
        elif kind=='jev_gate':
            mm=load(path(mp))['models'][m['arm']];p=np.clip(neural_probs('u5_DUP_s42',self.ids),1e-6,1-1e-6)
            X=np.log(p/(1-p))[:,None]
            if m['arm']=='KU':X=np.column_stack([X,self.url])
            X=(X-np.asarray(mm['scaler_mean']))/np.asarray(mm['scaler_scale'])
            w=np.asarray(mm['coef'][0]);b=float(mm['intercept'][0]);return self.checked(X,w,b,expit(X@w+b))
        else:raise ValueError('not a fitted logistic model')
        if list(model.classes_) not in ([0,1],[False,True]):raise ValueError('class ordering')
        return self.checked(X,model.coef_.ravel(),model.intercept_[0],reference)
    def checked(self,X,w,b,reference):
        X=sparse.csr_matrix(X,dtype=float);actual=expit(np.asarray(X@w).ravel()+b)
        if not np.allclose(actual,reference,rtol=0,atol=1e-7):raise ValueError('native logistic replay mismatch')
        validate_probs(actual);return X,np.array(w,copy=True),float(b)
    def baseline(self,mid):
        if mid not in self.baselines:
            X,w,b=self.linear(self.specs[mid]);self.baselines[mid]=expit(np.asarray(X@w).ravel()+b)
        return self.baselines[mid]
    def gate(self,seed,family='fage',adapted=None):
        cachekey=(seed,family)
        if adapted is None and cachekey in self.gate_cache:return self.gate_cache[cachekey].copy()
        has=(self.url[:,0]>0).astype(int)
        p=lambda name: adapted[name] if adapted is not None else self.baseline(name)
        k=adapted['kcbert'] if adapted is not None else neural_probs(f'kcbert_A_s{seed}',self.ids)
        frame=pd.DataFrame({'p_lr_a':p(f'LR_A_s{seed}_f0'),'p_lr_c':p(f'LR_C_s{seed}_f0'),'p_word':p(f'word_expert_s{seed}'),'p_kcbert_filled':k,'p_kcbert_missing':0,'p_url_filled':self.urlp,'p_url_missing':1-has,'has_url':has})
        simkey=('similarity',seed)
        if simkey not in self.cache:
            assign=pd.read_csv(ROOT/'data/research/url_free_stability_20260909/fold_assignments.csv')
            fit=set(assign.loc[(assign.seed==seed)&(assign.fold==0)&(assign.role=='fit'),'message_id'])
            data=pd.read_csv(ROOT/'data/processed/messages_split.csv',usecols=['message_id','split','text_normalized'])
            rows=data[data.message_id.isin(fit)]
            if len(rows)!=len(fit) or not rows.split.eq('train').all():raise ValueError('fit similarity source boundary')
            vector=joblib.load(ROOT/f'data/research/url_free_stability_20260909/models/seed_{seed}/fold_0/vectorizer.joblib')
            self.cache[simkey]=cosine_similarity(vector.transform(self.texts),vector.transform(rows.text_normalized.astype(str))).max(axis=1)
        frame['similarity_to_train']=self.cache[simkey]
        drop={'fage_no_lr_c':'lr_c','fage_no_kcbert':'kcbert','fage_no_url':'url'}.get(family)
        experts=tuple(e for e in EXPERT_ORDER if e!=drop)
        cols=[f'p_{e}_filled' if e in ('kcbert','url') else f'p_{e}' for e in experts]
        probs=frame[cols].to_numpy();available=expert_availability(has,np.zeros(272,int),1-has,experts=experts)
        context=context_from_experts(probs,available)
        frame['model_disagreement']=context['model_disagreement'];frame['uncertainty']=context['uncertainty'];frame['p_equal_weight']=context['equal_weight']
        textcols=[f'p_{e}_filled' if e=='kcbert' else f'p_{e}' for e in EXPERT_ORDER if e!='url']
        frame['p_fixed_weight']=fixed_weight_scores(frame[textcols].to_numpy().mean(axis=1),self.urlp,has.astype(bool))
        if adapted is None:self.gate_cache[cachekey]=frame.copy()
        return frame

def prepare():
    plan=load(PLAN)
    if OUT.exists():raise FileExistsError('fresh prepare output required')
    files={str(p):sha(p) for p in sources(plan)}
    read_inputs(plan)
    write(OUT/'prepare.json',{'files':files,'models':[m['id'] for m in plan['models']]})
    print('Prepared',len(plan['models']),'linear/derived conditions and',len(files),'sources')

def verify_sources():
    receipt=load(OUT/'prepare.json')
    for p,h in receipt['files'].items():
        if sha(p)!=h:raise ValueError('source changed: '+Path(p).name)
    return receipt

def baseline_summary(probs,t):
    p=validate_probs(probs)>=t
    return {'kisa_detected':int(p[:22].sum()),'kisa_missed':int((~p[:22]).sum()),'normal_alerts':int(p[22:].sum())}

def validate_result(payload,m,ids):
    if payload['model_id']!=m['id'] or payload['row_ids']!=ids or payload['threshold']!=m['threshold']:raise ValueError('result identity')
    base=validate_probs(payload['baseline_probabilities']);computed=baseline_summary(base,m['threshold'])
    if payload['baseline']!=computed:raise ValueError('baseline drift')
    if len(payload['folds'])!=9 or [f['support'] for f in payload['folds']]!=list(range(9)):raise ValueError('fold coverage')
    for f in payload['folds']:
        if set(f['steps'])!={'1','5','10'}:raise ValueError('checkpoint coverage')
        for step,s in f['steps'].items():
            if s['metrics']!=metrics(base,s['probabilities'],f['support'],m['threshold'],f.get('collisions',())):raise ValueError('metric drift')
    return True

def run_locked():
    prep=verify_sources();plan=load(PLAN);F=Features(plan)
    ut=load(ROOT/'reports/generated/url_baseline.json')['validation_selected']['threshold']
    normal_available=F.url[22:,0]>0
    url_baseline={'threshold':ut,'kisa_denominator':int((F.url[:22,0]>0).sum()),'kisa_detected':int(((F.urlp[:22]>=ut)&(F.url[:22,0]>0)).sum()),'normal_with_URL_denominator':int(normal_available.sum()),'normal_with_URL_alerts':int(((F.urlp[22:]>=ut)&normal_available).sum()),'normal_without_URL_abstained':int((~normal_available).sum()),'adaptation_status':'not_run_no_native_one_example_online_update'}
    write(OUT/'url_mapping_audit.json',{'cases':F.url_audit,'URL_expert':'frozen','normal250_source_label_only':True,'URL_baseline':url_baseline})
    completed={};ordered=sorted(plan['models'],key=lambda m:m['kind'] in ('derived_ensemble','original_fixed','raw_neural_derived'))
    for m in ordered:
        mid=m['id'];target=OUT/(mid+'.json');receipt=OUT/(mid+'.receipt.json')
        if target.exists() or receipt.exists():
            if not (target.exists() and receipt.exists()):raise ValueError('partial model output: '+mid)
            rc=load(receipt)
            if rc!={'result_sha256':sha(target),'prepare_sha256':sha(OUT/'prepare.json')}:raise ValueError('resume hash drift')
            payload=load(target);validate_result(payload,m,F.ids);completed[mid]=payload;continue
        folds=[];kind=m['kind']
        if kind not in ('derived_ensemble','original_fixed','raw_neural_derived'):
            X,w,b=F.linear(m);base=expit(np.asarray(X@w).ravel()+b)
            state_sha=hashlib.sha256(w.tobytes()+np.asarray([b]).tobytes()).hexdigest()
            for support in range(9):
                replay,steps,delta=rank_one_adapt(X,w,b,support)
                if not np.array_equal(replay,base):raise ValueError('fold reset replay')
                collisions=feature_collisions(X,support)
                for st,v in steps.items():v['metrics']=metrics(base,v['probabilities'],support,m['threshold'],collisions)
                folds.append({'support':support,'collisions':collisions,'steps':steps,'delta':delta})
        else:
            state_sha=None
            def derived(support=None,step=None):
                def p(mid):
                    row=completed[mid]
                    return np.asarray(row['baseline_probabilities'] if support is None else row['folds'][support]['steps'][str(step)]['probabilities'])
                if kind=='raw_neural_derived':return neural_probs('u5_DUP_s42',F.ids,support,step)
                if kind=='original_fixed':return np.where(F.url[:,0]>0,.7*p('char_tfidf_lr')+.3*F.urlp,p('char_tfidf_lr'))
                seed=m['seed'];adapted={name:p(name) for name in [f'LR_A_s{seed}_f0',f'LR_C_s{seed}_f0',f'word_expert_s{seed}']}
                adapted['kcbert']=neural_probs(f'kcbert_A_s{seed}',F.ids,support,step)
                return F.gate(seed,adapted=adapted)['p_'+m['family']].to_numpy()
            base=derived()
            for support in range(9):
                steps={}
                for st in STEPS:
                    probs=derived(support,st);steps[str(st)]={'probabilities':probs.tolist(),'metrics':metrics(base,probs,support,m['threshold'])}
                folds.append({'support':support,'collisions':[],'steps':steps})
        payload={'model_id':mid,'family':m['family'],'kind':kind,'threshold':m['threshold'],'row_ids':F.ids,'baseline_probabilities':base.tolist(),'baseline':baseline_summary(base,m['threshold']),'initial_coefficient_sha256':state_sha,'folds':folds}
        validate_result(payload,m,F.ids);write(target,payload);write(receipt,{'result_sha256':sha(target),'prepare_sha256':sha(OUT/'prepare.json')});completed[mid]=payload
        print('Completed',mid,'baseline',payload['baseline'],flush=True)
    verify_sources();render(plan,completed,F.url_audit)
    write(OUT/'completion.json',{'prepare_sha256':sha(OUT/'prepare.json'),'models':{k:sha(OUT/(k+'.json')) for k in completed},'url_audit_sha256':sha(OUT/'url_mapping_audit.json'),'public_sha256':sha(PUBLIC),'doc_sha256':sha(DOC)})

def run():
    if not (OUT/'prepare.json').exists():raise FileNotFoundError('prepare required')
    fd=os.open(OUT/'run.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run_locked()
    finally:
        os.close(fd)

def aggregate(plan,completed,url_audit):
    models={}
    for m in plan['models']:
        p=completed[m['id']]
        models[m['id']]={'family':m['family'],'kind':m['kind'],'threshold':m['threshold'],'baseline':p['baseline'],'folds':[{'support_case':f"K{f['support']+1:02d}",'steps':{s:v['metrics'] for s,v in f['steps'].items()}} for f in p['folds']]}
    return {'experiment_id':plan['experiment_id'],'status':'completed','conditions':len(models),'models':models,'URL_mapping_ambiguous_cases':sum(x['distinct_url_feature_sets']>1 for x in url_audit),'URL_baseline':load(OUT/'url_mapping_audit.json')['URL_baseline'],'URL_expert_adaptation':'not_run_no_native_one_example_online_update','clip_convention':'joint coefficient-and-intercept norm; one shared alpha','limitations':plan['limitations']}

def markdown(result):
    lines=['# 기존 선형·결합 모델의 한 건 추가학습 실측 결과','','원래 특징과 임계값을 고정하고 양성 한 건만 사용했다. 선형 모델은 SGD 0.1로 10회 업데이트했다. 각 행은 별도 기존 모델이며 9가지 학습 사례의 범위를 표시한다. 결합 게이트는 전문가를 고정하고 게이트만 학습했고, 고정 결합은 텍스트 전문가의 추가학습 결과를 조합했다.','','| 모델 | 학습 전 탐지 /22 | 정상 경보 전 /250 | 미학습 미탐 회복 범위 | 정상 경보 후 /250 | 새 정상 경보 | 회복 있고 새 오류 없는 실험 /9 |','|---|---:|---:|---:|---:|---:|---:|']
    for mid,m in result['models'].items():
        vals=[f['steps']['10'] for f in m['folds']]
        span=lambda k:f"{min(v[k] for v in vals)}–{max(v[k] for v in vals)}"
        lines.append(f"| {mid} | {m['baseline']['kisa_detected']} | {m['baseline']['normal_alerts']} | {span('recovered')} / {span('remaining_baseline_misses')} | {span('normal_alerts')} | {span('new_normal_alerts')} | {sum(v['clean_recovery'] for v in vals)} |")
    lines+=['','분모는 모델별 학습 전 미탐 중 지원 사례와 완전히 같은 특징의 사례를 제외한 수다. 이미 탐지한 문자는 회복에 포함하지 않는다. 전체 1·5·10회 결과는 대응 JSON에 보존했다.','',*['- '+x for x in result['limitations']],'',f"동일 정규화 문자에 URL 특징이 다른 원천 후보가 있는 사례: {result['URL_mapping_ambiguous_cases']}건. 고정 규칙으로 최소 audit_index 원천을 사용했으며 URL 접속은 수행하지 않았다.",'','URL HGB는 고정 전문가로만 평가했다. 한 건 온라인 추가학습 API가 없으므로 해당 모델의 추가학습 효과는 미검증이다.']
    return '\n'.join(lines)+'\n'

def render(plan,completed,url_audit):
    result=aggregate(plan,completed,url_audit);write(PUBLIC,result,False);write(DOC,markdown(result),False)

def check():
    verify_sources();plan=load(PLAN);k,n,_=read_inputs(plan);ids=[f'K{i+1:02d}' for i in range(22)]+[x['candidate_id'] for x in n]
    completion=load(OUT/'completion.json');expected={m['id'] for m in plan['models']}
    if completion['url_audit_sha256']!=sha(OUT/'url_mapping_audit.json'):raise ValueError('URL audit drift')
    if set(completion['models'])!=expected or completion['prepare_sha256']!=sha(OUT/'prepare.json'):raise ValueError('completion coverage')
    completed={}
    for m in plan['models']:
        mid=m['id'];p=OUT/(mid+'.json')
        if sha(p)!=completion['models'][mid]:raise ValueError('result hash drift')
        payload=load(p);validate_result(payload,m,ids);completed[mid]=payload
    result=aggregate(plan,completed,load(OUT/'url_mapping_audit.json')['cases'])
    if load(PUBLIC)!=result or DOC.read_text()!=markdown(result):raise ValueError('public report drift')
    if completion['public_sha256']!=sha(PUBLIC) or completion['doc_sha256']!=sha(DOC):raise ValueError('public artifact hash drift')
    print('PASS',len(completed),'conditions; baseline and all 9 x 3 prediction transitions verified')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run','check']);args=parser.parse_args()
    {'prepare':prepare,'run':run,'check':check}[args.mode]()

if __name__=='__main__':main()
