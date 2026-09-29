#!/usr/bin/env python3
"""Private, atomic storage and independent checks for matched KcBERT arms.

No model training occurs here.  Prediction CSVs are private; check output is
aggregate-only and never prints IDs or text.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,tempfile
from pathlib import Path
import numpy as np

SEEDS=(42,101,202,303,404); ARMS=("DUP","FLIP","BASE"); ROLES=("calibration","readout")
PRED_COLS=("message_id","development_group_id","role","label","has_url","probability")

def req(x,msg):
    if not x: raise ValueError(msg)
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def text_bytes(rows):
    import io
    s=io.StringIO(newline=''); w=csv.DictWriter(s,fieldnames=PRED_COLS,lineterminator='\n'); w.writeheader(); w.writerows(rows); return s.getvalue().encode()
def validate_rows(rows,role):
    req(role in ROLES,'invalid_role'); req(rows,'empty_prediction_rows'); seen=set()
    for r in rows:
        req(set(PRED_COLS)<=set(r),'prediction_schema'); req(r['role']==role,'role_mismatch'); req(r['message_id'] not in seen,'duplicate_prediction_id'); seen.add(r['message_id']); req(r['label'] in ('normal','smishing') and r['has_url'] in ('0','1'),'invalid_metadata'); p=float(r['probability']); req(np.isfinite(p) and 0<=p<=1,'invalid_probability')
    return seen
def threshold(y,p,cap=.01):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float);normal=int((y==0).sum());mal=int((y==1).sum());req(normal and mal,'calibration_requires_both_classes'); cand=np.append(np.unique(p),np.nextafter(p.max(),np.inf)); feasible=[]
    for t in cand:
        pred=p>=t; fp=int(((y==0)&pred).sum());tp=int(((y==1)&pred).sum())
        if fp/normal<=cap:feasible.append((tp,fp,float(t)))
    req(feasible,'no_feasible_threshold');tp,fp,t=max(feasible,key=lambda x:(x[0],-x[1],x[2]));return t,{'candidate_count':len(cand),'normal_rows':normal,'malicious_rows':mal,'normal_fp':fp,'normal_fpr':fp/normal,'malicious_tp':tp,'malicious_recall':tp/mal,'cap':cap}
def metric(y,p):
    y=np.asarray(y);p=np.asarray(p);tp=int(((y==1)&(p==1)).sum());fn=int(((y==1)&(p==0)).sum());fp=int(((y==0)&(p==1)).sum());tn=int(((y==0)&(p==0)).sum()); return {'n':len(y),'tp':tp,'fn':fn,'fp':fp,'tn':tn,'recall':tp/(tp+fn) if tp+fn else None,'fpr':fp/(fp+tn) if fp+tn else None,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
def read_arm(path):
    with (path/'predictions.csv').open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
    req({r.get('role') for r in rows} <= set(ROLES),'unknown_prediction_role')
    validate_rows([r for r in rows if r['role']=='calibration'],'calibration');validate_rows([r for r in rows if r['role']=='readout'],'readout');return rows
def verify_arm(output,seed,arm,fingerprint,expected_rows=None):
    d=Path(output)/f'seed_{seed}'/arm; req(d.is_dir(),'partial_or_missing_arm:'+str(seed)+'/'+arm)
    am=d/'arm_manifest.json';done=d/'completed.json';pred=d/'predictions.csv';req(am.is_file() and done.is_file() and pred.is_file(),'partial_arm:'+str(seed)+'/'+arm)
    for private_path in (Path(output),d.parent,d,am,done,pred):
        req(not private_path.is_symlink() and private_path.stat().st_mode & 0o077 == 0,
            'private_arm_permissions_or_symlink')
    meta=json.loads(am.read_text()); req(meta.get('seed')==seed and meta.get('arm')==arm and meta.get('fingerprint')==fingerprint,'arm_fingerprint_mismatch'); req(json.loads(done.read_text()).get('status')=='completed' and json.loads(done.read_text()).get('fingerprint')==fingerprint,'arm_not_completed'); req(sha(pred)==meta.get('files',{}).get('predictions.csv'),'prediction_hash_mismatch'); rows=read_arm(d)
    if expected_rows is not None:
        if isinstance(expected_rows,int): req(len(rows)==expected_rows,'arm_row_count_mismatch')
        elif isinstance(expected_rows,dict):
            for role, expected in expected_rows.items():
                actual=[tuple(r[k] for k in ('message_id','label','development_group_id','has_url')) for r in rows if r['role']==role]
                want=[tuple(r[k] for k in ('message_id','label','development_group_id','has_url')) for r in expected]
                req(actual==want,'arm_expected_sequence_mismatch')
        else:
            actual=[tuple(r[k] for k in ('message_id','label','development_group_id','has_url')) for r in rows]
            want=[tuple(r[k] for k in ('message_id','label','development_group_id','has_url')) for r in expected_rows]
            req(actual==want,'arm_expected_sequence_mismatch')
    return rows
def write_arm(output,seed,arm,calibration,readout,fingerprint):
    output=Path(output); req(seed in SEEDS and arm in ARMS,'invalid_arm_key'); output.mkdir(parents=True,exist_ok=True); os.chmod(output,0o700)
    validate_rows(calibration,'calibration');validate_rows(readout,'readout'); target=output/f'seed_{seed}'/arm; req(not target.exists(),'arm_already_exists'); rows=calibration+readout
    tmp=Path(tempfile.mkdtemp(prefix=f'.{arm}.',dir=str(output))); os.chmod(tmp,0o700); d=tmp/f'seed_{seed}'/arm; d.mkdir(parents=True,mode=0o700); os.chmod(d,0o700)
    try:
        (d/'predictions.csv').write_bytes(text_bytes(rows)); os.chmod(d/'predictions.csv',0o600)
        manifest={'schema_version':1,'seed':seed,'arm':arm,'fingerprint':fingerprint,'rows':len(rows),'files':{'predictions.csv':sha(d/'predictions.csv')}}
        (d/'arm_manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n');os.chmod(d/'arm_manifest.json',0o600)
        (d/'completed.json').write_text(json.dumps({'status':'completed','fingerprint':fingerprint})+'\n');os.chmod(d/'completed.json',0o600)
        seed_dir=output/f'seed_{seed}'; seed_dir.mkdir(parents=True,exist_ok=True); os.chmod(seed_dir,0o700); os.rename(d, target); os.chmod(target,0o700); return manifest
    finally:
        if tmp.exists():
            import shutil; shutil.rmtree(tmp,ignore_errors=True)
def check(output,expected_fingerprint=None):
    output=Path(output); root=output/'run_manifest.json';req(root.is_file(),'run_manifest_missing'); req(not root.is_symlink() and root.stat().st_mode & 0o077 == 0,'run_manifest_permissions_or_symlink'); meta=json.loads(root.read_text());fp=meta.get('fingerprint');req(fp and (expected_fingerprint is None or fp==expected_fingerprint),'run_fingerprint_mismatch'); completed=[]; arms={}
    for seed in SEEDS:
      for arm in ARMS:
        rows=verify_arm(output,seed,arm,fp); arms[(seed,arm)]=rows; completed.append((seed,arm))
    summaries=[]
    for (seed,arm),rows in arms.items():
      cal=[r for r in rows if r['role']=='calibration'];ro=[r for r in rows if r['role']=='readout']; y=np.array([r['label']=='smishing' for r in cal],dtype=int);p=np.array([float(r['probability']) for r in cal]);t,ts=threshold(y,p); yy=np.array([r['label']=='smishing' for r in ro],dtype=int);pp=np.array([float(r['probability'])>=t for r in ro]); summaries.append({'seed':seed,'arm':arm,'threshold':t,'threshold_selection':ts,'readout':metric(yy,pp),'readout_by_has_url':{u:metric(yy[[r['has_url']==u for r in ro]],pp[[r['has_url']==u for r in ro]]) for u in ('0','1')}})
    paired=[]
    for seed in SEEDS:
      d={r['message_id']:r for r in arms[(seed,'DUP')] if r['role']=='readout'};f={r['message_id']:r for r in arms[(seed,'FLIP')] if r['role']=='readout'};req(set(d)==set(f),'paired_readout_ids_mismatch');
      for key in ('label','development_group_id','has_url'):
        req(all(d[i][key]==f[i][key] for i in d),'paired_metadata_mismatch:'+key)
      dt=next(x for x in summaries if x['seed']==seed and x['arm']=='DUP')['threshold'];ft=next(x for x in summaries if x['seed']==seed and x['arm']=='FLIP')['threshold']; trans={'seed':seed,'rows':len(d),'flip_minus_dup':{'rescued_fn_to_tp':0,'lost_tp_to_fn':0,'new_fp':0,'resolved_fp':0}}
      for i in d:
        y=d[i]['label']=='smishing';a=float(d[i]['probability'])>=dt;b=float(f[i]['probability'])>=ft
        if y and not a and b:trans['flip_minus_dup']['rescued_fn_to_tp']+=1
        if y and a and not b:trans['flip_minus_dup']['lost_tp_to_fn']+=1
        if not y and not a and b:trans['flip_minus_dup']['new_fp']+=1
        if not y and a and not b:trans['flip_minus_dup']['resolved_fp']+=1
      paired.append(trans)
    return {'status':'completed_15_arms_checked','fingerprint':fp,'completed_arms':len(completed),'summaries':summaries,'paired_flip_minus_dup':paired}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);ap.add_argument('--check',action='store_true');ap.add_argument('--fingerprint');a=ap.parse_args()
    if a.check: print(json.dumps(check(a.output,a.fingerprint),ensure_ascii=False,indent=2));return
    raise SystemExit('write_arm_is_library_api; refusing ad-hoc CLI writes')
if __name__=='__main__':main()
