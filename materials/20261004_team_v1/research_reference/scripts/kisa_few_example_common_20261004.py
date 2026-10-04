"""Shared immutable input/output contract for the fixed 2/3-example diagnostic."""
from __future__ import annotations
import os
for _name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    os.environ[_name]='1'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
import hashlib,importlib.util,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path('${PRIVATE_ROOT}')
OUT=PRIVATE/'kisa_few_example_20261004_v1'
PLAN=ROOT/'docs/experiments/KISA_FEW_EXAMPLE_PLAN_20261004.json'
STEPS=('1','5','10')
_modules={}
def load(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def old_module(kind):
    if kind not in ('neural','linear'):raise ValueError('unknown model kind')
    if kind not in _modules:
        spec=importlib.util.spec_from_file_location('prior_kisa_'+kind,ROOT/f'scripts/run_kisa_all_models_{kind}_20261004.py')
        m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);_modules[kind]=m
    return _modules[kind]
def get_plan():
    p=load(PLAN);groups=p['groups']
    if p['private_root']!=str(PRIVATE) or p['output_dir']!=OUT.name:raise ValueError('output contract drift')
    if len(groups)!=12 or len({g['id'] for g in groups})!=12:raise ValueError('group coverage')
    for size,num,exposure in ((2,9,2),(3,3,1)):
        gs=[g for g in groups if g['size']==size]
        if len(gs)!=num:raise ValueError('group size coverage')
        for g in gs:
            s=g['support_indices']
            if len(s)!=size or s!=sorted(set(s)) or any(i not in range(9) for i in s):raise ValueError('support identity')
        if any(sum(i in g['support_indices'] for g in gs)!=exposure for i in range(9)):raise ValueError('unbalanced support schedule')
    pairs={tuple(g['support_indices']) for g in groups if g['size']==2}
    import itertools
    for g in groups:
        if g['size']==3 and not set(itertools.combinations(g['support_indices'],2))<=pairs:raise ValueError('non-nested groups')
    return p
def model_specs(kind):
    p=get_plan();return load(ROOT/p[kind+'_plan'])['models']
def input_data():
    p=get_plan();d=PRIVATE/p['input_dir'];k=sorted(load(d/'kisa_inputs.json'),key=lambda x:x['template_index']);n=load(d/'normal_candidates.json')
    if [x['template_index'] for x in k]!=list(range(22)) or len(n)!=250:raise ValueError('input coverage')
    ids=[f'K{i+1:02d}' for i in range(22)]+[x['candidate_id'] for x in n]
    if len(set(ids))!=272:raise ValueError('duplicate identifiers')
    return k,n,ids
def probabilities(p):
    a=np.asarray(p,dtype=float)
    if a.shape!=(272,) or not np.isfinite(a).all() or (a<0).any() or (a>1).any():raise ValueError('invalid probabilities')
    return a
def prior_predictions(kind,mid):
    p=get_plan();d=PRIVATE/p['prior_'+kind+'_output'];ids=input_data()[2]
    if kind=='linear':
        raw=load(d/(mid+'.json'))
        if raw['row_ids']!=ids:raise ValueError('prior row order')
        return probabilities(raw['baseline_probabilities']),{f['support']:{s:probabilities(f['steps'][s]['probabilities']) for s in STEPS} for f in raw['folds']}
    def arr(raw):
        rows=raw['kisa_records']+raw['normal_records'];by={x.get('case_id',x.get('candidate_id')):x['prob'] for x in rows}
        if set(by)!=set(ids):raise ValueError('prior row identity')
        return probabilities([by[i] for i in ids])
    return arr(load(d/mid/'baseline_predictions.json')),{i:{s:arr(load(d/mid/f'fold_K{i+1:02d}.json')['steps'][s]) for s in STEPS} for i in range(9)}
def private_write(p,obj):
    p=Path(p)
    if not p.resolve().is_relative_to(OUT.resolve()) or OUT.is_symlink() or p.exists():raise ValueError('private output exists or escapes')
    p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(p.parent,0o700)
    tmp=p.with_name(p.name+'.tmp')
    with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
        f.write(json.dumps(obj,ensure_ascii=False,allow_nan=False,indent=2)+'\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def prepare():
    if OUT.exists():raise FileExistsError('fresh output required')
    p=get_plan();old_l=old_module('linear');old_n=old_module('neural')
    files=dict(old_l.verify_sources()['files'])
    def add(path,expected=None):
        path=Path(path).resolve();h=sha(path)
        if expected is not None and h!=expected:raise ValueError('source changed: '+path.name)
        files[str(path)]=h
    npth=PRIVATE/p['prior_neural_output'];prep=load(npth/'prepare_manifest.json')
    neural_weights={}
    for spec in model_specs('neural'):
        mid=spec['id'];mm=prep['models'][mid];neural_weights[mid]=str(Path(mm['model_dir'])/'model.safetensors')
        for fn,h in mm['model_files'].items():add(Path(mm['model_dir'])/fn,h)
        add(mm['threshold_source'],mm['threshold_source_sha256'])
        ok,reason,_=old_n.verify_model_completion(mid,npth,prep)
        if not ok:raise ValueError('invalid prior neural result: '+mid+' '+reason)
        for name in ['baseline_predictions.json','completion_receipt.json']+[f'fold_K{i:02d}.json' for i in range(1,10)]:add(npth/mid/name)
    lp=PRIVATE/p['prior_linear_output'];lc=load(lp/'completion.json')
    for mid,h in lc['models'].items():add(lp/(mid+'.json'),h)
    for name in ['completion.json','prepare.json','url_mapping_audit.json']:add(lp/name)
    for path in [PLAN,ROOT/p['neural_plan'],ROOT/p['linear_plan'],npth/'prepare_manifest.json',ROOT/'scripts/run_kisa_all_models_neural_20261004.py']+[ROOT/'scripts'/n for n in ['kisa_few_example_common_20261004.py','run_kisa_few_example_neural_20261004.py','run_kisa_few_example_linear_20261004.py']]:add(path)
    _,_,ids=input_data();OUT.mkdir(mode=0o700)
    private_write(OUT/'prepare.json',{'files':files,'neural_weights':neural_weights,'row_ids':ids,'groups':p['groups'],'expected':{'neural':27,'linear':236}})
    print('Prepared fixed two/three-example experiment;',len(files),'source bindings')
def verify_sources(neural_model_id=None):
    rec=load(OUT/'prepare.json');weights=set(rec['neural_weights'].values())
    chosen=rec['neural_weights'].get(neural_model_id)
    if neural_model_id is not None and chosen is None:raise ValueError('unknown neural model')
    for p,h in rec['files'].items():
        if neural_model_id is not None and p in weights and p!=chosen:continue
        if sha(p)!=h:raise ValueError('source drift: '+Path(p).name)
    return rec
def validate_payload(kind,mid,p):
    m=next(x for x in model_specs(kind) if x['id']==mid)
    if p['model_id']!=mid or p['threshold']!=m['threshold'] or p['row_ids']!=input_data()[2]:raise ValueError('payload identity')
    probabilities(p['baseline_probabilities']);gs=get_plan()['groups']
    if len(p['groups'])!=len(gs):raise ValueError('incomplete group output')
    for g,actual in zip(gs,p['groups']):
        if actual['group_id']!=g['id'] or actual['support_indices']!=g['support_indices']:raise ValueError('group mismatch')
        if set(actual['steps'])!=set(STEPS):raise ValueError('checkpoint coverage')
        coll=actual.get('collisions',[])
        if coll!=sorted(set(coll)) or any(i not in range(22) or i in g['support_indices'] for i in coll):raise ValueError('invalid collisions')
        for s in STEPS:probabilities(actual['steps'][s]['probabilities'])
        if kind=='neural':
            loss=actual['training_losses']
            if len(loss)!=10 or any(not math.isfinite(v) or v<0 for v in loss):raise ValueError('invalid losses')
            h=actual['final_state_sha256'];delta=actual['param_delta_l2_norm']
            if len(h)!=64 or any(c not in '0123456789abcdef' for c in h) or not math.isfinite(delta) or delta<=0:raise ValueError('invalid updated state')
        elif p['kind'] not in ('derived_ensemble','original_fixed','raw_neural_derived'):
            delta=actual['delta'];loss=delta['training_losses'];alpha=delta['alpha']
            if len(loss)!=10 or any(not math.isfinite(v) or v<0 for v in loss):raise ValueError('invalid linear losses')
            if len(alpha)!=g['size'] or any(not math.isfinite(v) for v in alpha):raise ValueError('invalid low-rank update')
            if not math.isfinite(delta['intercept_delta']) or abs(delta['intercept_delta']-sum(alpha))>1e-12:raise ValueError('intercept update mismatch')
def existing_result(kind,mid):
    path=OUT/kind/(mid+'.json');rp=OUT/kind/(mid+'.receipt.json')
    if not path.exists() and not rp.exists():return None
    if not path.exists() or not rp.exists():raise ValueError('partial model output: '+mid)
    if load(rp)!={'prepare_sha256':sha(OUT/'prepare.json'),'result_sha256':sha(path)}:raise ValueError('result/receipt drift')
    p=load(path);validate_payload(kind,mid,p);return p
def save_result(kind,mid,payload):
    validate_payload(kind,mid,payload)
    path=OUT/kind/(mid+'.json');private_write(path,payload)
    private_write(OUT/kind/(mid+'.receipt.json'),{'prepare_sha256':sha(OUT/'prepare.json'),'result_sha256':sha(path)})
def metrics(base,after,support,threshold,collisions=()):
    b=probabilities(base)>=threshold;a=probabilities(after)>=threshold;s=sorted(set(support))
    if not s or len(s)!=len(support) or any(i not in range(9) for i in s):raise ValueError('support set')
    held=[i for i in range(22) if i not in s and i not in collisions];common=[i for i in range(9) if i not in s and i not in collisions]
    misses=[i for i in held if not b[i]];prior=[i for i in held if b[i]]
    rec=sum(bool(a[i]) for i in misses);lost=sum(not a[i] for i in prior);new=int((a[22:]&~b[22:]).sum())
    clean=bool(rec>0 and not lost and not new)
    return {'support_count':len(s),'support_baseline_misses':int((~b[s]).sum()),'support_detected':int(a[s].sum()),'heldout_count':len(held),'common_denominator':len(common),'common_detected':int(a[common].sum()),'common_baseline_detected':int(b[common].sum()),'common_recovered':int((a[common]&~b[common]).sum()),'miss_denominator':len(misses),'recovered':rec,'recovery_rate':rec/len(misses) if misses else None,'retention_denominator':len(prior),'retained':int(a[prior].sum()),'new_misses':int(lost),'baseline_normal_alerts':int(b[22:].sum()),'normal_alerts':int(a[22:].sum()),'new_normal_alerts':new,'resolved_normal_alerts':int((b[22:]&~a[22:]).sum()),'clean_recovery':clean,'all_supports_were_missed':bool((~b[s]).all()),'all_supports_learned':bool(a[s].all()),'full_common_clean_success':bool(clean and (~b[s]).all() and a[s].all() and len(common)==9-len(s) and a[common].all())}
if __name__=='__main__':
    if sys.argv[1:]!=['prepare']:raise SystemExit('usage: common.py prepare')
    prepare()
