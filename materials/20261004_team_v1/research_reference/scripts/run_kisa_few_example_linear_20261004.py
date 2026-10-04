"""Fixed-feature mean-minibatch SGD and derived readouts for two/three examples."""
import argparse,hashlib,math
import kisa_few_example_common_20261004 as c
import numpy as np
from scipy import sparse
from scipy.special import expit
DERIVED=('derived_ensemble','original_fixed','raw_neural_derived')

def derived_collisions(dependencies,group):
    return sorted(set().union(*(next(g for g in raw['groups'] if g['group_id']==group['id'])['collisions'] for raw in dependencies))-set(group['support_indices']))

def adapt(X,w,b,support,lr=.1,clip=1.):
    X=sparse.csr_matrix(X,dtype=float);w=np.asarray(w,dtype=float).ravel();support=list(support)
    if X.shape[0]!=272 or X.shape[1]!=len(w) or not np.isfinite(X.data).all() or not np.isfinite(w).all() or not math.isfinite(b):raise ValueError('nonfinite or malformed input')
    if len(support) not in (1,2,3) or len(set(support))!=len(support) or any(i not in range(9) for i in support):raise ValueError('invalid support')
    A=X[support];base=np.asarray(X@w).ravel()+b
    K=(X@A.T).toarray()+1.;G=(A@A.T).toarray()+1.
    alpha=np.zeros(len(support));steps={};losses=[]
    for step in range(1,11):
        z=base[support]+G@alpha;losses.append(float(np.logaddexp(0.,-z).mean()))
        g=(expit(z)-1.)/len(support);norm2=float(g@G@g)
        if not math.isfinite(norm2) or norm2 < -1e-10:raise ValueError('invalid gradient norm')
        norm=math.sqrt(max(0.,norm2));scale=min(1.,clip/norm) if norm else 1.
        alpha-=lr*g*scale
        if str(step) in c.STEPS:steps[str(step)]={'probabilities':c.probabilities(expit(base+K@alpha)).tolist()}
    return expit(base),steps,{'alpha':alpha.tolist(),'intercept_delta':float(alpha.sum()),'training_losses':losses}

def run():
    c.verify_sources();p=c.get_plan();old=c.old_module('linear');F=old.Features(c.load(c.ROOT/p['linear_plan']))
    done={};neural={}
    for mid in [f'kcbert_A_s{s}' for s in (42,101,202,303,404)]+['u5_DUP_s42']:
        v=c.existing_result('neural',mid)
        if v is None:raise ValueError('missing adapted neural dependency: '+mid)
        neural[mid]=v
    specs=sorted(c.model_specs('linear'),key=lambda m:m['kind'] in DERIVED)
    for m in specs:
        mid=m['id'];existing=c.existing_result('linear',mid)
        if existing is not None:done[mid]=existing;continue
        prior,singles=c.prior_predictions('linear',mid);groups=[];kind=m['kind']
        if kind not in DERIVED:
            X,w,b=F.linear(m);base=expit(np.asarray(X@w).ravel()+b)
            state_sha=hashlib.sha256(w.tobytes()+np.asarray([b]).tobytes()).hexdigest()
            # An exact singleton regression anchors this new updater to all prior supports.
            singleton_gap=0.
            for support in range(9):
                _,one,_=adapt(X,w,b,[support])
                for s in c.STEPS:
                    gap=float(np.max(np.abs(np.asarray(one[s]['probabilities'])-singles[support][s])))
                    singleton_gap=max(singleton_gap,gap)
                    if gap>1e-10:raise ValueError('one-example update regression: '+mid)
            for group in p['groups']:
                S=group['support_indices'];replay,steps,delta=adapt(X,w,b,S)
                if not np.array_equal(replay,base):raise ValueError('group reset')
                collisions=sorted(set().union(*(old.feature_collisions(X,i) for i in S))-set(S))
                unique=len({hashlib.sha256(X.getrow(i).toarray().tobytes()).hexdigest() for i in S})
                groups.append({'group_id':group['id'],'support_indices':S,'collisions':collisions,'unique_support_features':unique,'steps':steps,'delta':delta})
        else:
            state_sha=None;singleton_gap=None
            seed=m.get('seed')
            def pred(mid,group_id=None,step=None,is_neural=False):
                raw=neural[mid] if is_neural else done[mid]
                if group_id is None:return np.asarray(raw['baseline_probabilities'])
                g=next(x for x in raw['groups'] if x['group_id']==group_id)
                return np.asarray(g['steps'][step]['probabilities'])
            def derived(group_id=None,step=None):
                if kind=='raw_neural_derived':return pred('u5_DUP_s42',group_id,step,True)
                if kind=='original_fixed':
                    text=pred('char_tfidf_lr',group_id,step)
                    return np.where(F.url[:,0]>0,.7*text+.3*F.urlp,text)
                seed=m['seed'];ad={name:pred(name,group_id,step) for name in [f'LR_A_s{seed}_f0',f'LR_C_s{seed}_f0',f'word_expert_s{seed}']}
                ad['kcbert']=pred(f'kcbert_A_s{seed}',group_id,step,True)
                return F.gate(seed,adapted=ad)['p_'+m['family']].to_numpy()
            base=derived()
            if kind=='raw_neural_derived':dependencies=[neural['u5_DUP_s42']]
            elif kind=='original_fixed':dependencies=[done['char_tfidf_lr']]
            else:dependencies=[done[name] for name in [f'LR_A_s{seed}_f0',f'LR_C_s{seed}_f0',f'word_expert_s{seed}']]+[neural[f'kcbert_A_s{seed}']]
            for g in p['groups']:
                groups.append({'group_id':g['id'],'support_indices':g['support_indices'],'collisions':derived_collisions(dependencies,g),'steps':{s:{'probabilities':c.probabilities(derived(g['id'],s)).tolist()} for s in c.STEPS}})
        gap=float(np.max(np.abs(base-prior)))
        if gap>1e-5 or not np.array_equal(base>=m['threshold'],prior>=m['threshold']):raise ValueError('baseline replay: '+mid)
        payload={'model_id':mid,'family':m['family'],'kind':kind,'threshold':m['threshold'],'row_ids':F.ids,'baseline_probabilities':base.tolist(),'baseline_replay_max_diff':gap,'singleton_max_diff':singleton_gap,'initial_coefficient_sha256':state_sha,'groups':groups}
        c.save_result('linear',mid,payload);done[mid]=payload
        print('Completed',mid,len(done),'/',len(specs),flush=True)
    c.verify_sources()
    c.private_write(c.OUT/'linear_completion.json',{'models':{mid:c.sha(c.OUT/'linear'/(mid+'.json')) for mid in done},'prepare_sha256':c.sha(c.OUT/'prepare.json')})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['run']);ap.parse_args()
    with c.old_module('neural').FileLock(c.OUT/'linear.lock'):run()
