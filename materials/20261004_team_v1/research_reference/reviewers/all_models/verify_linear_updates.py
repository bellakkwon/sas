"""Rebuild real logistic updates with explicit full coefficient vectors, independent of rank-one updater."""
import hashlib,importlib.util,json,math,time
from pathlib import Path
import numpy as np
from scipy.special import expit
R=Path('${PROJECT_ROOT}')
spec=importlib.util.spec_from_file_location('readonly_features',R/'scripts/run_kisa_all_models_linear_20261004.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
plan=reader.load(reader.PLAN);F=reader.Features(plan)
checks=0;conditions=0;max_diff=0.;started=time.time()
for model in plan['models']:
 if model['kind'] in ('derived_ensemble','original_fixed','raw_neural_derived'):continue
 X,w,b=F.linear(model);data=reader.load(reader.OUT/(model['id']+'.json'))
 assert hashlib.sha256(w.tobytes()+np.asarray([b]).tobytes()).hexdigest()==data['initial_coefficient_sha256']
 for support,fold in enumerate(data['folds']):
  row=X.getrow(support).toarray().ravel();ww=w.copy();bb=b
  collisions=[i for i in range(22) if i!=support and np.array_equal(X.getrow(i).toarray().ravel(),row)]
  assert collisions==fold['collisions']
  for step in range(1,11):
   z=float(row@ww+bb);factor=float(expit(z)-1.)
   gradient=np.r_[factor*row,factor]
   gradient/=max(1.,float(np.linalg.norm(gradient)))
   ww-=.1*gradient[:-1];bb-=.1*gradient[-1]
   assert abs(float(np.logaddexp(0.,-z))-fold['delta']['losses'][step-1])<1e-10
   if step in (1,5,10):
    actual=expit(np.asarray(X@ww).ravel()+bb);saved=np.asarray(fold['steps'][str(step)]['probabilities']);diff=float(np.max(np.abs(actual-saved)))
    assert diff<1e-10,(model['id'],support,step,diff)
    max_diff=max(max_diff,diff);checks+=1
  assert abs(bb-b-fold['delta']['intercept_delta'])<1e-10
 conditions+=1
out={'status':'passed','method':'Full coefficient and intercept updates reconstructed with explicit gradients; no rank-one updater or metric function used','logistic_conditions':conditions,'support_checkpoint_checks':checks,'probability_rows_checked':checks*272,'max_probability_difference':max_diff,'elapsed_seconds':round(time.time()-started,3)}
(R/'tmp/kisa_all_models_20261004/linear_update_validation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
