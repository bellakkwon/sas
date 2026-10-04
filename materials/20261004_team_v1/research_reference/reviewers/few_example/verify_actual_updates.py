"""Reconstruct every real linear update using full coefficients, not low-rank algebra."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):os.environ[name]='1'
import sys,hashlib,json,time
from pathlib import Path
import numpy as np
from scipy.special import expit
R=Path('${PROJECT_ROOT}');sys.path.insert(0,str(R/'scripts'))
import kisa_few_example_common_20261004 as c
start=time.time();c.verify_sources();plan=c.get_plan();reader=c.old_module('linear');F=reader.Features(c.load(R/plan['linear_plan']))
count=rows=0;maximum=0.;hashes={}
for spec in c.model_specs('linear'):
    if spec['kind'] in ('derived_ensemble','original_fixed','raw_neural_derived'):continue
    X,w,b=F.linear(spec);raw=c.existing_result('linear',spec['id'])
    assert raw is not None
    assert hashlib.sha256(w.tobytes()+np.asarray([b]).tobytes()).hexdigest()==raw['initial_coefficient_sha256']
    for group in raw['groups']:
        S=group['support_indices'];A=X[S].toarray();ww=w.copy();bb=b
        collisions=[i for i in range(22) if i not in S and any((X.getrow(i)-X.getrow(j)).nnz==0 for j in S)]
        assert collisions==group['collisions']
        unique=len({row.tobytes() for row in A});assert unique==group['unique_support_features']
        for step in range(1,11):
            logits=A@ww+bb;loss=float(np.logaddexp(0.,-logits).mean())
            assert abs(loss-group['delta']['training_losses'][step-1])<1e-10
            factors=(expit(logits)-1.)/len(S)
            grad=np.r_[A.T@factors,float(factors.sum())]
            grad/=max(1.,float(np.linalg.norm(grad)))
            ww-=.1*grad[:-1];bb-=.1*grad[-1]
            if step in [1,5,10]:
                actual=expit(np.asarray(X@ww).ravel()+bb);saved=np.asarray(group['steps'][str(step)]['probabilities'])
                difference=float(np.max(np.abs(actual-saved)));assert difference<1e-10
                maximum=max(maximum,difference);rows+=272
        assert np.max(np.abs(ww-(w+A.T@np.asarray(group['delta']['alpha']))))<1e-10
        assert abs(bb-b-group['delta']['intercept_delta'])<1e-10
    hashes[spec['id']]=c.sha(c.OUT/'linear'/(spec['id']+'.json'));count+=1
derived_count=derived_rows=0;derived_gap=0.;derived_hashes={}
for spec in c.model_specs('linear'):
    if spec['kind'] not in ('derived_ensemble','original_fixed','raw_neural_derived'):continue
    raw=c.existing_result('linear',spec['id']);kind=spec['kind']
    if kind=='raw_neural_derived':dependencies=[c.existing_result('neural','u5_DUP_s42')]
    elif kind=='original_fixed':dependencies=[c.existing_result('linear','char_tfidf_lr')]
    else:
        seed=spec['seed']
        dependencies=[c.existing_result('linear',m) for m in [f'LR_A_s{seed}_f0',f'LR_C_s{seed}_f0',f'word_expert_s{seed}']]+[c.existing_result('neural',f'kcbert_A_s{seed}')]
    for group in raw['groups']:
        deps=[next(g for g in d['groups'] if g['group_id']==group['group_id']) for d in dependencies]
        expected_collisions=sorted({i for d in deps for i in d['collisions']} - set(group['support_indices']))
        assert expected_collisions==group['collisions']
        for step in ['1','5','10']:
            ps=[np.asarray(d['steps'][step]['probabilities']) for d in deps]
            has=F.url[:,0]>0
            if kind=='raw_neural_derived':actual=ps[0]
            elif kind=='original_fixed':actual=np.where(has,.7*ps[0]+.3*F.urlp,ps[0])
            elif spec['family']=='equal_weight':actual=(sum(ps)+np.where(has,F.urlp,0.))/(4+has.astype(int))
            elif spec['family']=='fixed_weight':actual=np.where(has,.7*(sum(ps)/4)+.3*F.urlp,sum(ps)/4)
            else:raise ValueError('unexpected derived family')
            gap=float(np.max(np.abs(actual-np.asarray(group['steps'][step]['probabilities']))))
            assert gap<1e-10;derived_gap=max(derived_gap,gap);derived_rows+=272
    derived_count+=1;derived_hashes[spec['id']]=c.sha(c.OUT/'linear'/(spec['id']+'.json'))
out={'status':'passed','conditions':count,'probability_rows':rows,'maximum_difference':maximum,'derived_conditions':derived_count,'derived_probability_rows':derived_rows,'derived_maximum_difference':derived_gap,'derived_result_hashes':derived_hashes,'method':'Explicit full coefficient/intercept mean-minibatch SGD, global joint clipping, original reset per group; derived blends independently recomputed by direct arithmetic and dependency collision union','result_hashes':hashes,'checker_sha256':c.sha(__file__),'elapsed_seconds':round(time.time()-start,3)}
(R/'tmp/kisa_few_example_20261004/update_validation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='result_hashes'},indent=2))
