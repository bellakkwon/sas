"""Count support/normal input collisions without exporting text or input fingerprints."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
import hashlib,importlib.util,json
from pathlib import Path
from transformers import AutoTokenizer
R=Path('${PROJECT_ROOT}');P=Path.home()/'scamlens_private'
def load(p):return json.loads(Path(p).read_text())
spec=importlib.util.spec_from_file_location('collision_features',R/'scripts/run_kisa_all_models_linear_20261004.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
plan=reader.load(reader.PLAN);F=reader.Features(plan)
linear=[]
for model in plan['models']:
    if model['kind'] in ('derived_ensemble','original_fixed','raw_neural_derived'):continue
    X,_,_=F.linear(model)
    X=X.tocsr(copy=True);X.sum_duplicates();X.eliminate_zeros();X.sort_indices()
    keys=[]
    for i in range(X.shape[0]):
        start,end=X.indptr[i:i+2]
        keys.append(hashlib.sha256(X.indices[start:end].tobytes()+X.data[start:end].tobytes()).digest())
    counts=[sum(keys[s]==key for key in keys[22:]) for s in range(9)]
    linear.append({'id':model['id'],'normal_input_collisions_per_support':counts})
np=load(R/'docs/experiments/KISA_ALL_MODELS_NEURAL_PLAN_20261004.json')
prep=load(P/np['output_dir']/'prepare_manifest.json')
k=load(P/np['input_dir']/'kisa_inputs.json');n=load(P/np['input_dir']/'normal_candidates.json')
texts=[x['primary_model_input'] for x in k]+[x['text_normalized'] for x in n]
groups={}
for mid,m in prep['models'].items():
    files={name:h for name,h in m['model_files'].items() if 'token' in name or 'vocab' in name or 'special' in name}
    key=json.dumps(files,sort_keys=True)
    groups.setdefault(key,[]).append(mid)
neural=[]
for mids in groups.values():
    tok=AutoTokenizer.from_pretrained(prep['models'][mids[0]]['model_dir'],local_files_only=True)
    rows=tok(texts,truncation=True,padding='max_length',max_length=128)['input_ids']
    counts=[sum(rows[s]==row for row in rows[22:]) for s in range(9)]
    neural.append({'model_ids':mids,'normal_input_collisions_per_support':counts})
result={'status':'checked','method':'Exact canonical sparse feature equality for linear/gate models and exact first128-token equality for each frozen tokenizer group; text and fingerprints omitted','linear_conditions':len(linear),'neural_tokenizer_groups':len(neural),'linear':linear,'neural':neural,'support_normal_collision_pairs':sum(sum(r['normal_input_collisions_per_support']) for r in linear+neural)}
(R/'tmp/kisa_all_models_20261004/input_collision_validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('linear','neural')},indent=2))
