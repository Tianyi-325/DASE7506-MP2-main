"""Focused round: matched supervision, style and additive ablations."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,hashlib,json,time,sys,platform
from pathlib import Path
import numpy as np
import torch
from common import load_inputs
from train_vector import labels
from broad_models import raw_inputs
from focused_models import preprocessing,design,scores
from vector_vote_fusion import answer_information,select_from_scores
from run_fusion_experiments import save,official

OUT=Path('runs/focused_round')
SEEDS=[101,307]
SOURCES=['focused_models.py','run_focused_round.py','check_focused_round.py','broad_models.py',
 'reasoning_features.py','vector_vote_fusion.py','vector_logistic.py','common.py','train_vector.py',
 'run_fusion_experiments.py','predict.py','score_predictions.py']
SPECS={}
def spec(features='full',style='all',basis='linear',l2=.01,policy='all'):
    return dict(features=features,style=style,basis=basis,l2=l2,policy=policy)
for style in ('all','broad'):
    for basis in ('linear','hinges','interactions','both'):
        for l2 in (.01,.02):
            SPECS[f'full_{style}_{basis}_l2{int(l2*1000)}']=spec(style=style,basis=basis,l2=l2)
for style in ('all','narrow','broad'):
    SPECS[f'base_{style}_linear_l210']=spec(features='base',style=style)
SPECS['base_all_linear_l220']=spec(features='base',l2=.02)
SPECS['full_narrow_linear_l210']=spec(style='narrow')
for features,style in [('base','all'),('full','broad')]:
    for policy in ('informative_full','informative_mean','hard_full','hard_mean',
                   'hard_mask_full','all_mask_full','hard_prep_mean'):
        SPECS[f'{features}_{style}_{policy}']=spec(features=features,style=style,policy=policy)
for style in ('all','broad'):
    for basis in ('orth_hinges','orth_both'):
        for l2 in (.01,.02):
            SPECS[f'full_{style}_{basis}_l2{int(l2*1000)}']=spec(style=style,basis=basis,l2=l2)
BASE='base_all_linear_l210'

def log(x):print(json.dumps(x,ensure_ascii=False),flush=True)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def choices(s,valid,votes,alpha=.25):
    t=np.asarray(s).copy()+alpha*(votes-1);t[~valid]=-1e30
    return t.argmax(axis=1)
def right(s,y,valid,votes,alpha=.25):return y[np.arange(len(y)),choices(s,valid,votes,alpha)].astype(bool)
def loss_each(s,y,mask=None):
    if mask is not None:s=s.masked_fill(~mask,-1e30)
    return torch.logsumexp(s,dim=1)-torch.logsumexp(s.masked_fill(~y.bool(),-torch.inf),dim=1)

def fit(raw,y,valid,distinct,c):
    started=time.perf_counter();policy=c['policy'];n=len(y)
    select=np.ones(n,bool)
    if policy.startswith('informative'):select=y.sum(axis=1)<4
    elif policy.startswith('hard'):select=distinct>1
    assert select.any()
    prep_raw=raw[select] if policy=='hard_prep_mean' else raw
    a=preprocessing(prep_raw,c);x=design(raw[select],a,c)
    xt=torch.from_numpy(x);yt=torch.from_numpy(y[select]).double()
    mask=torch.from_numpy(valid[select]) if 'mask' in policy else None
    factor=float(select.sum()/n) if policy.endswith('_full') else 1.
    weight=torch.zeros(x.shape[-1],dtype=torch.float64,requires_grad=True)
    opt=torch.optim.LBFGS([weight],lr=1.,max_iter=100,max_eval=140,history_size=12,
          tolerance_grad=1e-7,tolerance_change=1e-11,line_search_fn='strong_wolfe')
    def closure():
        opt.zero_grad(set_to_none=True)
        loss=loss_each(xt@weight,yt,mask).mean()*factor+.5*c['l2']*weight.square().sum()
        loss.backward();return loss
    initial=float(closure().detach());opt.step(closure);objective=float(closure().detach())
    grad=float(weight.grad.norm());a['weight']=weight.detach().numpy().copy()
    all_scores=scores(raw,a,c);scale=max(float((all_scores-all_scores.mean(axis=1,keepdims=True)).std()),1e-6)
    assert np.allclose(all_scores[select][:7],(xt[:7]@weight).detach().numpy(),atol=1e-9,rtol=1e-9)
    state=opt.state[weight]
    info={'fit_questions':n,'loss_questions':int(select.sum()),'preprocess_questions':len(prep_raw),
      'disagreement_questions':int((distinct>1).sum()),'loss_factor':factor,'parameters':len(weight),
      'initial_objective':initial,'final_objective':objective,'gradient_norm':grad,
      'optimizer_iterations':state.get('n_iter'),'function_evaluations':state.get('func_evals'),
      'score_scale':scale,'seconds':time.perf_counter()-started}
    return a,info

def folds(y,valid,distinct,seed):
    strata={}
    for i in range(len(y)):strata.setdefault((int(y[i].sum()),int(distinct[i]),int(valid[i].sum())),[]).append(i)
    rng=np.random.default_rng(seed);out=np.full(len(y),-1);offset=0
    for _,ix in sorted(strata.items()):
        order=rng.permutation(ix);out[order]=(np.arange(len(order))+offset)%3;offset=(offset+len(order))%3
    assert (out>=0).all()
    return out

def prepare(out):
    out.mkdir(parents=True,exist_ok=True)
    plan={'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'specs':SPECS,'seeds':SEEDS,
      'folds_per_seed':3,'baseline':BASE,'optimizer':{'name':'LBFGS','max_iter':100,'max_eval':140,
      'history_size':12,'dtype':'float64','tolerance_grad':1e-7,'tolerance_change':1e-11},
      'promotion':{'mean_oof_gain_min':8,'each_seed_gain_at_least':0,'positive_folds_at_least':4,
                   'worst_fold_gain_at_least':-6,'validation_gain_at_least':0},
      'selection':'Gate versus normalized-score baseline; rank eligible by mean train OOF correct, minimum seed gain, validation correct, fewer parameters. Otherwise retain baseline.',
      'comparison':'All main and mixed models divide scores by own training within-question std, then use fixed alpha=.25. Raw baseline alpha=.25 and normalized baseline alpha=0 are extra controls, not selectable.',
      'combinations':'OOF-only best hard, best no-style linear and best additive; five prescribed pair types at .5/.75 left weights and one triple .5/.25/.25; same score units and vote alpha.',
      'supervision':'All preprocessing uses all fitting-fold inputs except explicit hard_prep_mean. *_full preserves original full-fold loss denominator; *_mean averages selected questions.',
      'validation':'Only full TRAIN refits evaluated on validation after CV. Test evaluated only after all variants and selection freeze.',
      'limits':{'threads':4,'device':'cpu','asset_bytes':16*2**20,'cpu_seconds':30},
      'notes':['Repeated CV reuses questions; 9510 predictions are not 9510 independent examples.',
        'OOF and historical validation are development data; no claim of unbiased family-selection evaluation.',
        'No new data, pretrained weights or LLM generation. Previous frozen rounds unchanged.'],
      'dependencies':{'python':sys.version,'numpy':np.__version__,'torch':torch.__version__}}
    if (out/'plan.json').exists():
        old=json.loads((out/'plan.json').read_text());assert old['specs']==SPECS and old['seeds']==SEEDS
    else:save(out/'plan.json',plan)
    bank,arrays=load_inputs('train');y=labels('train',bank);_,counts,votes=answer_information(bank)
    raw=raw_inputs(bank,arrays);valid=votes>0;distinct=np.array(list(map(len,counts)))
    assignments={str(seed):folds(y,valid,distinct,seed) for seed in SEEDS}
    np.savez(out/'training-cache.npz',raw=raw,y=y,valid=valid,votes=votes,distinct=distinct,
             **{'fold_'+k:v for k,v in assignments.items()})
    save(out/'folds.json',{'question_ids':[r['id'] for r in bank],
      'folds':{s:v.tolist() for s,v in assignments.items()},'purpose':'Training alignment and reproducibility only; no IDs saved in inference bundles.'})
    # Analytical negative controls: removing zero-loss groups under fixed denominator.
    rng=np.random.default_rng(2026);tt=torch.tensor(rng.normal(size=(len(y),4)),dtype=torch.float64,requires_grad=True)
    yy=torch.from_numpy(y).double();mm=torch.from_numpy(valid)
    each=loss_each(tt,yy);informative=y.sum(axis=1)<4;hard=distinct>1
    tests={}
    for name,all_loss,subset_loss in [
      ('drop_all_positive_fixed_denominator',each.mean(),each[informative].sum()/len(y)),
      ('valid_mask_hard_fixed_denominator',loss_each(tt,yy,mm).mean(),loss_each(tt,yy,mm)[hard].sum()/len(y))]:
        ga=torch.autograd.grad(all_loss,tt,retain_graph=True)[0];gb=torch.autograd.grad(subset_loss,tt,retain_graph=True)[0]
        err=float((ga-gb).abs().max());diff=float(abs(all_loss-subset_loss).detach());assert err<1e-12 and diff<1e-12
        tests[name]={'max_gradient_difference':err,'loss_difference':diff}
    save(out/'objective-controls.json',tests)
    manifest=json.loads(Path('PACKAGE_MANIFEST.json').read_text());assert all(digest(Path('..')/n)==h for n,h in manifest['files'].items())
    log({'prepared':True,'configs':len(SPECS),'question_counts':{'all':len(y),'informative':int(informative.sum()),'hard':int(hard.sum())},'analytical_controls':tests})

def train(out):
    z=dict(np.load(out/'training-cache.npz'));raw,y,valid,distinct,votes=[z[n] for n in ('raw','y','valid','distinct','votes')]
    times=[];oof={};norm={};cv_right={}
    for seed in SEEDS:
        fold=z['fold_'+str(seed)];oof[seed]={n:np.zeros_like(y,np.float64) for n in SPECS};norm[seed]={n:np.zeros(3) for n in SPECS}
        for k in range(3):
            fi=np.flatnonzero(fold!=k);hi=np.flatnonzero(fold==k)
            for name,c in SPECS.items():
                folder=out/'cv'/str(seed)/str(k)/name;folder.mkdir(parents=True,exist_ok=True)
                if not (folder/'result.json').exists():
                    a,info=fit(raw[fi],y[fi],valid[fi],distinct[fi],c);held=scores(raw[hi],a,c)
                    np.savez(folder/'model.npz',**a);np.save(folder/'scores.npy',held)
                    info.update(seed=seed,fold=k,method=name,held_correct=int(right(held/info['score_scale'],y[hi],valid[hi],votes[hi]).sum()),held_n=len(hi))
                    save(folder/'result.json',info)
                info=json.loads((folder/'result.json').read_text());oof[seed][name][hi]=np.load(folder/'scores.npy')
                norm[seed][name][k]=info['score_scale'];times.append(info)
                log({'seed':seed,'fold':k,'method':name,'correct':info['held_correct'],'seconds':info['seconds'],'iterations':info['optimizer_iterations']})
        np.savez(out/f'oof-{seed}.npz',**oof[seed]);np.savez(out/f'scales-{seed}.npz',**norm[seed])
    save(out/'cv-results.json',times)
    # All model choices and combination identities below will use training OOF only.
    vb,va=load_inputs('validation');vr=raw_inputs(vb,va);vy=labels('validation',vb)
    full={};vs={}
    for name,c in SPECS.items():
        folder=out/'full'/name;folder.mkdir(parents=True,exist_ok=True)
        if not (folder/'result.json').exists():
            a,info=fit(raw,y,valid,distinct,c);v=scores(vr,a,c)
            np.savez(folder/'model.npz',**a);np.save(folder/'validation.npy',v)
            save(folder/'result.json',info)
        info=json.loads((folder/'result.json').read_text());vs[name]=np.load(folder/'validation.npy');full[name]=info
        log({'full':name,'seconds':info['seconds'],'iterations':info['optimizer_iterations']})
    np.savez(out/'validation-scores.npz',**vs);save(out/'full-results.json',full)

def paired(a,b):
    delta=a.astype(float)-b.astype(float);rng=np.random.default_rng(2026);boot=[]
    for _ in range(32):boot.extend(delta[rng.integers(0,len(delta),(64,len(delta)))].mean(axis=1).tolist())
    return {'mean_delta_questions':float(delta.sum()),'delta_pp':100*float(delta.mean()),
      'bootstrap_95_pp':(np.quantile(boot,[.025,.975])*100).tolist(),
      'note':'question-paired exploratory interval; unadjusted model search and overlapping CV fits'}

def freeze(out):
    if (out/'freeze.json').exists():raise FileExistsError('Already frozen')
    z=dict(np.load(out/'training-cache.npz'));y,valid,votes=z['y'],z['valid'],z['votes']
    oof={seed:dict(np.load(out/f'oof-{seed}.npz')) for seed in SEEDS}
    norm={seed:dict(np.load(out/f'scales-{seed}.npz')) for seed in SEEDS}
    full=json.loads((out/'full-results.json').read_text());vs=dict(np.load(out/'validation-scores.npz'))
    vb,va=load_inputs('validation');vy=labels('validation',vb);_,_,vv=answer_information(vb);vm=vv>0
    defs={n:{'members':[n],'weights':[1.],'normalized':True,'alpha':.25,'selectable':True} for n in SPECS}
    def normalized(n,seed):return oof[seed][n]/norm[seed][n][z['fold_'+str(seed)],None]
    rank={n:float(np.mean([right(normalized(n,s),y,valid,votes).sum() for s in SEEDS])) for n in SPECS}
    def best(names):return max(names,key=lambda n:(rank[n],-full[n]['parameters'],n))
    representatives={'hard':best([n for n,c in SPECS.items() if c['policy'].startswith('hard')]),
      'nostyle':best([n for n,c in SPECS.items() if c['style']=='broad' and c['basis']=='linear' and c['policy']=='all']),
      'additive':best([n for n,c in SPECS.items() if c['basis']!='linear'])}
    pairs=[(BASE,representatives['hard']),(BASE,representatives['nostyle']),(BASE,representatives['additive']),
           (representatives['hard'],representatives['additive']),(representatives['nostyle'],representatives['additive'])]
    for k,(l,r) in enumerate(pairs):
        for beta in (.5,.75):
            defs[f'mix{k+1}_{int(beta*100)}']={'members':[l,r],'weights':[beta,1-beta],'normalized':True,'alpha':.25,'selectable':True}
    defs['triple']={'members':[BASE,representatives['hard'],representatives['additive']],'weights':[.5,.25,.25],
                   'normalized':True,'alpha':.25,'selectable':True}
    defs['baseline_native_vote']={'members':[BASE],'weights':[1.],'normalized':False,'alpha':.25,'selectable':False}
    defs['baseline_normalized_plain']={'members':[BASE],'weights':[1.],'normalized':True,'alpha':0.,'selectable':False}
    base_right={s:right(normalized(BASE,s),y,valid,votes) for s in SEEDS}
    bv=right(vs[BASE]/full[BASE]['score_scale'],vy,vm,vv);baseline_counts=[int(base_right[s].sum()) for s in SEEDS]
    records={};validation_right={}
    for name,d in defs.items():
        rights={};foldg=[];seedg=[]
        for seed in SEEDS:
            score=sum(w*(normalized(n,seed) if d['normalized'] else oof[seed][n]) for n,w in zip(d['members'],d['weights']))
            rc=right(score,y,valid,votes,d['alpha']);rights[seed]=rc
            seedg.append(int(rc.sum()-base_right[seed].sum()))
            fg=z['fold_'+str(seed)];foldg.extend([int(rc[fg==k].sum()-base_right[seed][fg==k].sum()) for k in range(3)])
        vscore=sum(w*vs[n]/(full[n]['score_scale'] if d['normalized'] else 1) for n,w in zip(d['members'],d['weights']))
        rv=right(vscore,vy,vm,vv,d['alpha']);validation_right[name]=rv
        mean_gain=float(np.mean(seedg));gate=mean_gain>=8 and min(seedg)>=0 and sum(v>0 for v in foldg)>=4 and min(foldg)>=-6
        eligible=bool(d['selectable'] and gate and rv.sum()>=bv.sum())
        records[name]={'definition':d,'oof_correct_by_seed':{str(s):int(rights[s].sum()) for s in SEEDS},
          'mean_oof_correct':float(np.mean([v.sum() for v in rights.values()])),
          'seed_gains':seedg,'fold_gains':foldg,'cv_gate':bool(gate),'eligible':eligible,
          'validation_correct':int(rv.sum()),'validation_gain':int(rv.sum()-bv.sum()),
          'oof_vs_baseline':paired(np.stack(list(rights.values())).mean(axis=0),np.stack(list(base_right.values())).mean(axis=0)),
          'validation_vs_baseline':paired(rv,bv),'parameters':sum(full[n]['parameters'] for n in d['members'])}
    eligible=[n for n,r in records.items() if r['eligible']]
    chosen=max(eligible,key=lambda n:(records[n]['mean_oof_correct'],min(records[n]['seed_gains']),records[n]['validation_correct'],-records[n]['parameters'])) if eligible else BASE
    # External validation diagnostics use its labels, never test.
    strata={}
    for label,mask in [('all',np.ones(len(vy),bool)),('disagreement',vv.max(axis=1)<(vv>0).sum(axis=1)),('one_correct',vy.sum(axis=1)==1)]:
        strata[label]={'n':int(mask.sum()),'methods':{n:int(v[mask].sum()) for n,v in validation_right.items()}}
    # Better exact disagreement mask uses number of distinct valid parsed answers.
    _,count,_=answer_information(vb);mask=np.array([len(v)>1 for v in count])
    strata['disagreement']={'n':int(mask.sum()),'methods':{n:int(v[mask].sum()) for n,v in validation_right.items()}}
    save(out/'comparison.json',{'selected':chosen,'representatives':representatives,'records':records,
      'baseline_counts_by_seed':baseline_counts,'baseline_validation':int(bv.sum()),'eligible':eligible,'validation_strata':strata})
    variants={}
    for name,d in defs.items():
        bundle=out/'variants'/name/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
        config={'alpha':d['alpha'],'members':[],'seed_folds':SEEDS,'threads':4,'training_only':True}
        for i,(n,w) in enumerate(zip(d['members'],d['weights'])):
            (bundle/f'member{i}.npz').write_bytes((out/'full'/n/'model.npz').read_bytes())
            config['members'].append({'config':SPECS[n],'weight':w,'scale':full[n]['score_scale'] if d['normalized'] else 1.})
        save(bundle/'config.json',config)
        variants[name]={'assets':{p.name:digest(p) for p in bundle.iterdir()},'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir()),
                        'validation_correct':records[name]['validation_correct']}
        assert variants[name]['asset_bytes']<=16*2**20
    save(out/'freeze.json',{'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'selected':chosen,
      'selection_basis':'two train-only three-fold partitions, fixed gates, validation noninferiority; no test scoring',
      'variants':variants,'source_sha256':{n:digest(n) for n in SOURCES},'plan_sha256':digest(out/'plan.json')})
    log({'frozen':True,'selected':chosen,'variants':len(variants),'eligible':eligible,'record':records[chosen]})

def evaluate(out):
    f=json.loads((out/'freeze.json').read_text())
    for n,h in f['source_sha256'].items():assert digest(n)==h,n
    assert digest(out/'plan.json')==f['plan_sha256']
    result_path=out/'official-results.json';results=json.loads(result_path.read_text()) if result_path.exists() else {}
    for name,v in f['variants'].items():
        bundle=out/'variants'/name/'model_bundle'
        for n,h in v['assets'].items():assert digest(bundle/n)==h
        if name in results:continue
        entry={}
        for split in ('validation','test'):
            r,_=official(out/'official',name,'focused_models.py',bundle,split);entry[split]=r
            if split=='validation':assert r['correct']==v['validation_correct'],(name,r,v)
        entry['asset_bytes']=v['asset_bytes'];entry['local_limits_pass']=v['asset_bytes']<=16*2**20 and entry['test']['fresh_prediction_plus_scoring_seconds']<=30
        results[name]=entry;save(result_path,results)
        log({'official':name,'validation':entry['validation']['correct'],'test':entry['test']['correct'],'seconds':entry['test']['fresh_prediction_plus_scoring_seconds']})
    manifest=json.loads(Path('PACKAGE_MANIFEST.json').read_text());assert all(digest(Path('..')/n)==h for n,h in manifest['files'].items())
    hardware={'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,'threads':4,'training_device':'cpu'}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:hardware['cpu']=winreg.QueryValueEx(k,'ProcessorNameString')[0].strip()
    except ImportError:pass
    save(out/'compliance.json',{'hardware':hardware,'official_files_unchanged':True,'reference_cpu_tested':False,
      'all_local_limits_pass':all(v['local_limits_pass'] for v in results.values()),
      'max_asset_bytes':max(v['asset_bytes'] for v in results.values()),
      'max_local_test_seconds':max(v['test']['fresh_prediction_plus_scoring_seconds'] for v in results.values()),
      'no_external_data_or_pretrained_weights':True,'selected_before_test':f['selected']})

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','train','freeze','evaluate','all'],default='all');p.add_argument('--output',type=Path,default=OUT);args=p.parse_args()
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.manual_seed(2026);torch.use_deterministic_algorithms(True)
    started=time.perf_counter()
    for name,fn in [('prepare',prepare),('train',train),('freeze',freeze),('evaluate',evaluate)]:
        if args.stage in (name,'all'):fn(args.output)
    save(args.output/f'stage-{args.stage}-timing.json',{'wall_seconds':time.perf_counter()-started})
if __name__=='__main__':main()
