"""Autonomous evidence round. Fit on train, freeze using train OOF/validation, then score test."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,hashlib,json,platform,sys,time
from pathlib import Path
import numpy as np
from common import load_inputs,check_data
from run_fusion_experiments import labels,official
from vector_vote_fusion import select_from_scores
from evidence_models import make_inputs,subset,member_scores
from evidence_training import SPECS,BASE_CONFIGS,fit_base,fit
from math_evidence import SEM_NAMES,VERIFY_NAMES,REL_NAMES

def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def count(bank,y,s,alpha):
    p=select_from_scores(bank,s,'weighted',alpha)
    return y[np.arange(len(y)),p].astype(int)
def partitions(y,data,seed):
    rng=np.random.default_rng(seed);fold=np.zeros(len(y),int)
    strata={}
    for i in range(len(y)):
        key=(int(y[i].sum()),int(data['group_mask'][i].sum()),int((data['votes'][i]>0).sum()))
        strata.setdefault(key,[]).append(i)
    for ids in strata.values():
        ids=np.asarray(ids);rng.shuffle(ids);fold[ids]=np.arange(len(ids))%3
    return fold
def sources():
    files=['run_evidence_round.py','evidence_models.py','evidence_training.py','math_evidence.py','check_evidence_round.py',
      'broad_models.py','broad_training.py','direct_group_models.py','reasoning_features.py','vector_vote_fusion.py',
      'common.py','predict.py','score_predictions.py','run_fusion_experiments.py']
    return {f:digest(Path(f)) for f in files}
def plan(out):
    p={'specs':SPECS,'seeds':[211,509],'folds':3,
      'features':{'semantic':SEM_NAMES,'verify':VERIFY_NAMES,'relative':REL_NAMES},
      'selection':'train OOF only for component selection; validation veto/tie only; no test before freeze',
      'promotion_gate':{'mean_oof_gain':5,'each_seed_nonnegative':True,'positive_folds':4,'worst_fold_gain':-6,'validation_not_lower':True},
      'combinations':'two old controls; new pair weights .5/.75; evidence weights .1/.25; new triple .4/.4/.2; fixed vote .125 pairs/.15 new triple',
      'limits':{'cpu_threads':4,'assets_bytes':16*2**20,'fresh_test_prediction_and_scoring_seconds':30},
      'external_data_or_weights':False,'test_access_before_freeze':False,'source_sha256':sources(),
      'versions':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'processor':platform.processor()}}
    if (out/'plan.json').exists():assert json.loads((out/'plan.json').read_text(encoding='utf8'))['source_sha256']==p['source_sha256'],'Source changed: use fresh output'
    else:save(out/'plan.json',p)
def train(out):
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    if (out/'freeze.json').exists():raise RuntimeError('Already frozen; evaluate only')
    plan(out);check_data(splits=['train','validation'])
    started=time.perf_counter()
    tb,ta=load_inputs('train');vb,va=load_inputs('validation');ty=labels(tb,'train');vy=labels(vb,'validation')
    cache=out/'input-cache.npz'
    if cache.exists():
        with np.load(cache,allow_pickle=False) as z:
            td={k[2:]:z[k] for k in z.files if k.startswith('t_')}
            vd={k[2:]:z[k] for k in z.files if k.startswith('v_')}
    else:
        td,diag=make_inputs(tb,ta);vd,vdiag=make_inputs(vb,va)
        np.savez(cache,**{'t_'+k:v for k,v in td.items()},**{'v_'+k:v for k,v in vd.items()})
        save(out/'feature-diagnostics.json',{'train':diag,'validation':vdiag})
    del ta,va
    print(json.dumps({'prepared_seconds':time.perf_counter()-started,'features':[len(SEM_NAMES),len(VERIFY_NAMES),len(REL_NAMES)]}),flush=True)
    folds=[partitions(ty,td,s) for s in (211,509)]
    np.savez(out/'folds.npz',**{str(s):v for s,v in zip((211,509),folds)})
    oof={n:np.zeros((2,len(tb),4)) for n in SPECS};oof_scales={n:np.ones((2,len(tb))) for n in SPECS}
    full={};infos={};val_scores={}
    for repeat in range(3):
        for fold in (range(3) if repeat<2 else [0]):
            fullfit=repeat==2;tag='full' if fullfit else f'seed{(211,509)[repeat]}_fold{fold}'
            ti=np.arange(len(tb)) if fullfit else np.flatnonzero(folds[repeat]!=fold)
            hi=np.arange(len(vb)) if fullfit else np.flatnonzero(folds[repeat]==fold)
            train_data=subset(td,ti);held_data=vd if fullfit else subset(td,hi);train_y=ty[ti]
            bases={}
            for kind in BASE_CONFIGS:
                file=out/'fits'/tag/(kind+'-base.npz');meta=file.with_suffix('.json')
                if file.exists():
                    with np.load(file,allow_pickle=False) as z:bases[kind]={k:z[k] for k in z.files}
                else:
                    asset,info=fit_base(train_data,train_y,kind);file.parent.mkdir(parents=True,exist_ok=True)
                    np.savez(file,**asset);save(meta,info);bases[kind]=asset
            for name,c in SPECS.items():
                file=out/'fits'/tag/(name+'.npz');meta=file.with_suffix('.json')
                if file.exists():
                    with np.load(file,allow_pickle=False) as z:asset={k:z[k] for k in z.files}
                    info=json.loads(meta.read_text(encoding='utf8'))
                else:
                    asset,info=fit(train_data,train_y,c,bases.get(c['base']))
                    np.savez(file,**asset);save(meta,info)
                score=member_scores(held_data,c,asset)
                if fullfit:full[name]=asset;infos[name]=info;val_scores[name]=score
                else:oof[name][repeat,hi]=score;oof_scales[name][repeat,hi]=info['score_scale']
                correct=int(count(vb if fullfit else [tb[i] for i in hi],vy if fullfit else ty[hi],score,c['alpha']).sum())
                print(json.dumps({'fit':tag,'name':name,'held_correct':correct,'n':len(hi),'fit_seconds':info['seconds']}),flush=True)
            del train_data,held_data,bases
    # Exact historical prediction parity, checked before any test access.
    paths={'no_style':'runs/broad_round/official/no_style_vote/validation-predictions.json',
      'feature_selection':'runs/broad_round/official/stable_features_vote/validation-predictions.json',
      'joint':'runs/direct_group_round/joint_group_valid_only/validation-predictions.json'}
    parity={}
    for n,p in paths.items():
        old=json.loads(Path(p).read_text(encoding='utf8'))['selected']
        new=select_from_scores(vb,val_scores[n],'weighted',SPECS[n]['alpha'])
        parity[n]={'identical_choices':old==new,'differing_choices':sum(a!=b for a,b in zip(old,new)),'validation_correct':int(count(vb,vy,val_scores[n],SPECS[n]['alpha']).sum())}
        assert old==new,(n,parity[n])
    save(out/'reference-parity.json',parity)
    def choices_oof(n):
        return np.stack([count(tb,ty,oof[n][r],SPECS[n]['alpha']) for r in range(2)])
    def best(names):return max(names,key=lambda n:(choices_oof(n).mean(),n))
    enhanced_ns=best([n for n,c in SPECS.items() if c['base']=='no_style'])
    enhanced_j=best([n for n,c in SPECS.items() if c['base']=='joint'])
    evidence=best([n for n,c in SPECS.items() if c['base']=='none'])
    combos={
      'old_pair':([('joint',.5),('no_style',.5)],.125),
      'old_triple':([('joint',1/3),('no_style',1/3),('feature_selection',1/3)],1/6)}
    for label,a,b in [('joint_newNS','joint',enhanced_ns),('NS_newjoint','no_style',enhanced_j),
                       ('new_pair',enhanced_j,enhanced_ns)]:
        for w in (.5,.75):combos[f'{label}_{int(w*100)}']=([(a,w),(b,1-w)],.125)
    for a in ('joint','no_style'):
        for w in (.9,.75):combos[f'{a}_evidence_{int(w*100)}']=([(a,w),(evidence,1-w)],.125)
    combos['new_triple']=([(enhanced_j,.4),(enhanced_ns,.4),('feature_selection',.2)],.15)
    variants={n:{'parts':[(n,1.)],'alpha':c['alpha'],'normalized':False} for n,c in SPECS.items()}
    variants.update({n:{'parts':p,'alpha':a,'normalized':True} for n,(p,a) in combos.items()})
    records={};correct_oof={};correct_val={};all_val_choices={}
    for n,v in variants.items():
        vs=sum(w*(val_scores[k]-val_scores[k].mean(axis=1,keepdims=True))/(infos[k]['score_scale'] if v['normalized'] else 1) for k,w in v['parts'])
        rs=[]
        for r in range(2):
            ss=sum(w*(oof[k][r]-oof[k][r].mean(axis=1,keepdims=True))/(oof_scales[k][r,:,None] if v['normalized'] else 1) for k,w in v['parts'])
            rs.append(count(tb,ty,ss,v['alpha']))
        co=np.stack(rs);cv=count(vb,vy,vs,v['alpha']);correct_oof[n]=co;correct_val[n]=cv
        all_val_choices[n]=select_from_scores(vb,vs,'weighted',v['alpha'])
        records[n]={'oof_correct':co.sum(axis=1).tolist(),'mean_oof_correct':float(co.sum(axis=1).mean()),'validation_correct':int(cv.sum()),**v}
    incumbent=max(['no_style','joint','feature_selection','old_pair','old_triple'],key=lambda n:(records[n]['mean_oof_correct'],records[n]['validation_correct'],n))
    eligible=[]
    for n,r in records.items():
        dif=correct_oof[n]-correct_oof[incumbent]
        gains=dif.sum(axis=1);fg=[int(dif[j,folds[j]==k].sum()) for j in range(2) for k in range(3)]
        ok=float(gains.mean())>=5 and min(gains)>=0 and sum(g>0 for g in fg)>=4 and min(fg)>=-6 and r['validation_correct']>=records[incumbent]['validation_correct']
        r.update(seed_gains=gains.tolist(),fold_gains=fg,promotion_pass=bool(ok),
          validation_fixed=int(((correct_val[n]==1)&(correct_val[incumbent]==0)).sum()),
          validation_broken=int(((correct_val[n]==0)&(correct_val[incumbent]==1)).sum()))
        if ok:eligible.append(n)
    selected=max(eligible,key=lambda n:(records[n]['mean_oof_correct'],records[n]['validation_correct'],n)) if eligible else incumbent
    selection={'incumbent':incumbent,'selected':selected,'promoted':selected!=incumbent,
      'components':{'enhanced_no_style':enhanced_ns,'enhanced_joint':enhanced_j,'evidence_only':evidence},
      'eligible':eligible,'records':records,'test_used':False}
    save(out/'selection.json',selection)
    np.savez(out/'development-correctness.npz',**{'oof_'+n:v for n,v in correct_oof.items()},**{'val_'+n:v for n,v in correct_val.items()})
    frozen={}
    for n,v in variants.items():
        bundle=out/'variants'/n/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
        config={'alpha':v['alpha'],'members':[]}
        for j,(k,w) in enumerate(v['parts']):
            np.savez(bundle/f'member{j}.npz',**full[k])
            config['members'].append({'config':SPECS[k],'weight':w,'scale':infos[k]['score_scale'] if v['normalized'] else 1.})
        save(bundle/'config.json',config)
        assets={p.name:digest(p) for p in bundle.iterdir()}
        size=sum(p.stat().st_size for p in bundle.iterdir())
        assert size<16*2**20
        frozen[n]={'validation_correct':records[n]['validation_correct'],'assets':assets,'asset_bytes':size}
    np.savez(out/'oof-scores.npz',**oof)
    save(out/'freeze.json',{'variants':frozen,'selected':selected,'source_sha256':sources(),
      'elapsed_training_and_freezing_seconds':time.perf_counter()-started,'versions':{'torch':torch.__version__,'numpy':np.__version__},
      'training_only_assets':True,'no_test_access_before_freeze':True})
    print(json.dumps({'frozen':len(frozen),'selection':selected,'components':selection['components']}),flush=True)

def evaluate(out):
    f=json.loads((out/'freeze.json').read_text(encoding='utf8'))
    for p,h in f['source_sha256'].items():assert digest(Path(p))==h,('source changed',p)
    results=json.loads((out/'official-results.json').read_text(encoding='utf8')) if (out/'official-results.json').exists() else {}
    for name,v in f['variants'].items():
        bundle=out/'variants'/name/'model_bundle'
        for p,h in v['assets'].items():assert digest(bundle/p)==h
        results.setdefault(name,{})
        for split in ('validation','test'):
            if split in results[name]:continue
            score,_=official(out/'official',name,'evidence_models.py',bundle,split)
            if split=='validation':assert score['correct']==v['validation_correct']
            results[name][split]=score;save(out/'official-results.json',results)
            print(json.dumps({'variant':name,'split':split,**score}),flush=True)
    check_data(splits=['train','validation','test'])
    save(out/'compliance.json',{'original_data_hashes_passed':True,'frozen_sources_and_assets_passed':True,
      'max_asset_bytes':max(v['asset_bytes'] for v in f['variants'].values()),
      'max_test_fresh_seconds':max(r['test']['fresh_prediction_plus_scoring_seconds'] for r in results.values()),
      'cpu_threads':4,'no_external_data_or_pretrained_weights':True,'reference_Xeon_not_measured':True})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['train','evaluate'],default='train')
    p.add_argument('--output',type=Path,default=Path('runs/evidence_round'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    (train if a.stage=='train' else evaluate)(a.output)
