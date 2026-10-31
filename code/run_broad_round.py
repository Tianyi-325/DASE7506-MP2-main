"""Reproducible broad round: train-only CV -> validation -> freeze -> official test."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,hashlib,json,time,sys,platform
from pathlib import Path
from collections import Counter
import numpy as np
import torch
from common import load_inputs,parse_answer
from train_vector import labels
from broad_models import raw_inputs,char_tokens,model_scores,strict_equations,EXTRA_NAMES
from broad_training import SPECS,preprocess,fit_model
from vector_vote_fusion import answer_information,select_from_scores
from run_fusion_experiments import save,official
OUT=Path('runs/broad_round')
SOURCE_NAMES=['broad_models.py','broad_training.py','run_broad_round.py','check_broad_round.py']
DIRECTIONS={
 'A1':['gbdt'],'A2':['lambdamart'],'A3':['gam'],'A4':['fm'],'A5':['rff'],'A6':['charcnn'],'A7':['supcon'],
 'B1':['three-fold question CV, inner early stopping, fold-local preprocessing'],
 'B2':['predeclared promotion gates, paired bootstrap'],
 'B3':['supervision_balanced'],'B4':['parser and duplicate audit','valid_training_mask'],
 'B5':['numeric_quality','extended_features'],'B6':['no_style','stable_features','fold coefficient stability'],
 'B7':['cross-fitted temperature calibration','OOF scale audit','fixed mixtures'],
 'C1':['residual'],'C2':['residual_width32','residual_dropout','residual_adam_l2'],
 'C3':['linear_lbfgs'],'C4':['linear_earlystop'],'C5':['residual_batch128'],
 'C6':['residual_ema','residual_swa'],'C7':['residual_sam']}

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def log(v):print(json.dumps(v,ensure_ascii=False),flush=True)
def subset_bank(bank,ix):return [bank[int(i)] for i in ix]
def right(scores,y,valid,alpha=0.,votes=None):
    s=np.asarray(scores).copy()
    if votes is not None:s+=alpha*(votes-1)
    s[~valid]=-1e9
    return y[np.arange(len(y)),s.argmax(axis=1)].astype(bool)
def paired(a,b,seed=2026):
    delta=a.astype(int)-b.astype(int);rng=np.random.default_rng(seed)
    means=np.concatenate([delta[rng.integers(0,len(delta),(100,len(delta)))].mean(axis=1) for _ in range(20)])
    return {'fixed':int(((a)&(~b)).sum()),'broken':int(((~a)&b).sum()),
      'delta_questions':int(delta.sum()),'delta_pp':100*float(delta.mean()),
      'paired_bootstrap_95_pp':[100*float(v) for v in np.quantile(means,[.025,.975])],
      'note':'exploratory; not adjusted for searching many models'}

def prepare(out):
    out.mkdir(parents=True,exist_ok=True)
    if not (out/'plan.json').exists():
        save(out/'plan.json',{'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'seed':2026,'folds':3,
          'directions':DIRECTIONS,'specs':SPECS,'threads':4,'device':'cpu',
          'promotion_gate':{'minimum_oof_gain_questions':5,'positive_folds':2,'worst_fold_gain_at_least':-5,
                            'minimum_validation_gain_questions':3},
          'selection':'Gate by train OOF vs matched baseline; candidates passing gate need >=3 external validation questions gain. Rank eligible by OOF correct, validation as tie-break; otherwise retain matched baseline.',
          'mixtures':'Fixed equal or 0.75/0.25 pairs; fixed triple and selected component pairs; OOF and validation only; no post-test adjustments.',
          'calibration':'Train-only cross-fitted distinct-answer group temperature; finite grid, no test fitting.',
          'limitations':'OOF used for comparison/selection, not an untouched final estimate. Existing validation has prior reuse. No formal nested CV for choosing whole families.',
          'dependencies':{'python':sys.version,'numpy':np.__version__,'torch':torch.__version__},
          'external_packages':'PyPI unavailable. Native histogram gradient boosting and lambda ranking are lightweight original implementations, not official XGBoost/LightGBM/EBM.'})
    else:assert json.loads((out/'plan.json').read_text())['specs']==SPECS,'plan/config mismatch'
    bank,arrays=load_inputs('train');y=labels('train',bank);answers,counts,votes=answer_information(bank);valid=votes>0
    raw=raw_inputs(bank,arrays);tokens=char_tokens(bank)
    # Stratification uses TRAIN labels only; every question remains intact.
    strata={}
    for i in range(len(y)):strata.setdefault((int(y[i].sum()),len(counts[i]),int(valid[i].sum())),[]).append(i)
    fold=np.full(len(y),-1);rng=np.random.default_rng(2026);offset=0
    for key,indices in sorted(strata.items()):
        ix=rng.permutation(indices)
        fold[ix]=(np.arange(len(ix))+offset)%3;offset=(offset+len(ix))%3
    assert (fold>=0).all()
    np.savez(out/'training-cache.npz',raw=raw,y=y,valid=valid,votes=votes,tokens=tokens,fold=fold)
    save(out/'folds.json',{'assignment':fold.tolist(),'counts':[int((fold==k).sum()) for k in range(3)],
        'question_ids':[r['id'] for r in bank],'warning':'IDs only align training records; never inference inputs'})
    audit={}
    for split in ('train','validation'):
        sb,sa=(bank,arrays) if split=='train' else load_inputs(split)
        sy=y if split=='train' else labels(split,sb);sr=raw if split=='train' else raw_inputs(sb,sa)
        aa,cc,vv=answer_information(sb)
        normalized=[' '.join(r['question'].lower().split()) for r in sb]
        counter=Counter(normalized)
        audit[split]={'questions':len(sb),'positive_candidate_counts':dict(Counter(map(int,sy.sum(axis=1)))),
          'distinct_answer_counts':dict(Counter(map(len,cc))),'invalid_candidates':int((vv==0).sum()),
          'duplicate_normalized_questions':sum(n-1 for n in counter.values()),
          'all_positive_zero_group_gradient_questions':int((sy.sum(axis=1)==4).sum()),
          'old_equation_candidate_coverage':int((sr[:,:,1046]>0).sum()),
          'strict_equation_candidate_coverage':int((sr[:,:,1069]>0).sum()),
          'strict_detected_inconsistent_candidates':int((sr[:,:,1070]>0).sum()),
          'feature_finite':bool(np.isfinite(sr).all())}
        if split=='train':train_questions=set(normalized)
        else:audit['train_validation_normalized_overlap']=len(train_questions&set(normalized))
    samples=[('2 + 3 = 5','5',[1,0]),('2 + 3 = 6','6',[1,1]),('2 / 0 = 7','7',[0,0]),
      ('x + 3 = 5','5',[0,0]),('2 + 3 = 5 dollars','5',[0,0]),
      ('__import__("os") = 1','1',[0,0]),('2 * (3 + 4) = 14','14',[1,0]),
      ('10 / 4 = 2.5','5/2',[1,0]),('4 × 3 = 11','11',[1,1])]
    audit['strict_equation_synthetic_cases']=[]
    for text,answer,expected in samples:
        f=strict_equations(text,answer);assert (f[0]>0)==bool(expected[0]);assert (f[1]>0)==bool(expected[1])
        audit['strict_equation_synthetic_cases'].append({'text':text,'features':f})
    audit['interpretation']='Coverage is not reliability. Final-answer labels do not validate reasoning steps. Unknown is not wrong. No official parser/labels were modified.'
    manifest=json.loads(Path('PACKAGE_MANIFEST.json').read_text())
    audit['official_files_unchanged']=all(digest(Path('..')/n)==h for n,h in manifest['files'].items());assert audit['official_files_unchanged']
    save(out/'data-audit.json',audit);log({'prepared':True,'folds':np.bincount(fold).tolist(),'features':raw.shape[-1]})

def train(out):
    z=dict(np.load(out/'training-cache.npz'));raw,y,valid,tokens,fold=[z[n] for n in ('raw','y','valid','tokens','fold')]
    timings=[];oof={n:np.zeros_like(y,np.float64) for n in SPECS};scales={n:np.zeros(3) for n in SPECS}
    for k in range(3):
        fit=np.flatnonzero(fold!=k);held=np.flatnonzero(fold==k);rng=np.random.default_rng(900+k)
        order=rng.permutation(fit);cut=int(.85*len(order));inner,stop=order[:cut],order[cut:]
        prep_path=out/'fits'/f'fold{k}'/'preprocessing.npz';prep_path.parent.mkdir(parents=True,exist_ok=True)
        if not prep_path.exists():
            pp=preprocess(raw[fit]);ip=preprocess(raw[inner]);np.savez(prep_path,**{'full_'+a:b for a,b in pp.items()},**{'inner_'+a:b for a,b in ip.items()})
        cached=dict(np.load(prep_path));prep={n[5:]:v for n,v in cached.items() if n.startswith('full_')};iprep={n[6:]:v for n,v in cached.items() if n.startswith('inner_')}
        base_full=base_inner=None
        for name,config in SPECS.items():
            folder=out/'fits'/f'fold{k}'/name;folder.mkdir(parents=True,exist_ok=True)
            if not (folder/'result.json').exists():
                selected_epoch=None;inner_info=None
                if config['arch'] in ('residual','supcon','cnn','fm') or config.get('earlystop'):
                    if base_inner is None:
                        bp,_=fit_model(raw[inner],y[inner],valid[inner],tokens[inner],iprep,SPECS['baseline'])
                        base_inner=bp['linear_w']
                    _,inner_info=fit_model(raw[inner],y[inner],valid[inner],tokens[inner],iprep,config,
                        (raw[stop],y[stop],valid[stop],tokens[stop]),base_cache=base_inner)
                    selected_epoch=inner_info['epochs']
                learned,info=fit_model(raw[fit],y[fit],valid[fit],tokens[fit],prep,config,
                   forced_epochs=selected_epoch,base_cache=base_full)
                score=model_scores(raw[held],[],config,learned,tokens=tokens[held])
                np.savez(folder/'model.npz',**learned);np.save(folder/'held_scores.npy',score)
                info.update(fold=k,method=name,inner=inner_info,held_correct=int(right(score,y[held],valid[held],.25,z['votes'][held]).sum()),held_n=len(held))
                save(folder/'result.json',info)
            asset=dict(np.load(folder/'model.npz'));info=json.loads((folder/'result.json').read_text())
            if name=='baseline':base_full=asset['linear_w']
            oof[name][held]=np.load(folder/'held_scores.npy');scales[name][k]=info['score_scale'];timings.append(info)
            log({'fold':k,'method':name,'held_correct':info['held_correct'],'n':len(held),'epoch':info['epochs'],'seconds':info['seconds']})
    np.savez(out/'oof-scores.npz',**oof)
    np.savez(out/'oof-scales.npz',**scales)
    save(out/'cv-training-records.json',timings)
    # Each full-data refit uses the median of TRAIN-internal chosen epochs, not external validation.
    full_prep_path=out/'full-preprocessing.npz'
    if not full_prep_path.exists():np.savez(full_prep_path,**preprocess(raw))
    prep=dict(np.load(full_prep_path));vb,va=load_inputs('validation');vr=raw_inputs(vb,va);vy=labels('validation',vb);vt=char_tokens(vb)
    base_full=None;full_results={};validation_scores={}
    for name,config in SPECS.items():
        folder=out/'full'/name;folder.mkdir(parents=True,exist_ok=True)
        if not (folder/'result.json').exists():
            epoch=int(np.median([r['epochs'] for r in timings if r['method']==name]))
            learned,info=fit_model(raw,y,valid,tokens,prep,config,forced_epochs=epoch,base_cache=base_full)
            np.savez(folder/'model.npz',**learned)
            vs=model_scores(vr,vb,config,learned,tokens=vt);np.save(folder/'validation_scores.npy',vs)
            info.update(method=name,epochs=epoch,validation_correct=int(vy[np.arange(len(vy)),select_from_scores(vb,vs,'weighted',.25)].sum()))
            save(folder/'result.json',info)
        asset=dict(np.load(folder/'model.npz'));info=json.loads((folder/'result.json').read_text())
        if name=='baseline':base_full=asset['linear_w']
        full_results[name]=info;validation_scores[name]=np.load(folder/'validation_scores.npy')
        log({'full_refit':name,'validation_correct':info['validation_correct'],'epochs':info['epochs'],'seconds':info['seconds']})
    np.savez(out/'validation-scores.npz',**validation_scores);save(out/'full-training-records.json',full_results)

def analysis_and_freeze(out):
    if (out/'freeze.json').exists():raise FileExistsError('Already frozen')
    z=dict(np.load(out/'training-cache.npz'));y=z['y'];valid=z['valid'];fold=z['fold'];votes=z['votes']
    oof=dict(np.load(out/'oof-scores.npz'));scales=dict(np.load(out/'oof-scales.npz'))
    vs=dict(np.load(out/'validation-scores.npz'));full=json.loads((out/'full-training-records.json').read_text())
    vb,va=load_inputs('validation');vy=labels('validation',vb);_,_,vv=answer_information(vb);vvalid=vv>0
    configs={n:dict(c) for n,c in SPECS.items()};definitions={}
    for name in SPECS:
        for alpha in (0.,.25):
            key=name+('_vote' if alpha else '_plain')
            definitions[key]={'members':[name],'weights':[1.],'normalize':False,'alpha':alpha}
    # Predeclared natural pairings, plus top OOF candidates chosen without any test.
    ranking=sorted(SPECS,key=lambda n:int(right(oof[n],y,valid,.25,votes).sum()),reverse=True)
    pairs=[('baseline','gbdt'),('baseline','lambdamart'),('baseline','gam'),('baseline','fm'),
      ('baseline','rff'),('baseline','charcnn'),('baseline','supcon'),
      ('baseline','numeric_quality'),('baseline','no_style'),('baseline','residual_swa'),
      ('gbdt','lambdamart'),('gam','fm'),('gbdt','numeric_quality')]
    for n in ranking[:3]:
        if n!='baseline' and ('baseline',n) not in pairs:pairs.append(('baseline',n))
    for left,right_name in pairs:
        for beta in (.5,.75):
            key=f'mix_{left}_{right_name}_{int(beta*100)}'
            definitions[key]={'members':[left,right_name],'weights':[beta,1-beta],'normalize':True,'alpha':.25}
    definitions['triple_linear_tree_gam']={'members':['baseline','gbdt','gam'],'weights':[.5,.25,.25],'normalize':True,'alpha':.25}
    definitions['triple_top_oof']={'members':ranking[:3],'weights':[1/3]*3,'normalize':True,'alpha':.25}
    base=right(oof['baseline'],y,valid,.25,votes);vbase=right(vs['baseline'],vy,vvalid,.25,vv)
    records={};all_scores={};all_valid_scores={}
    for name,d in definitions.items():
        ts=np.zeros_like(y,np.float64);vscore=np.zeros_like(vy,np.float64)
        for member,weight in zip(d['members'],d['weights']):
            ts+=weight*oof[member]/(scales[member][fold,None] if d['normalize'] else 1)
            vscore+=weight*vs[member]/(full[member]['score_scale'] if d['normalize'] else 1)
        correct=right(ts,y,valid,d['alpha'],votes);vc=right(vscore,vy,vvalid,d['alpha'],vv)
        gains=[int(correct[fold==k].sum()-base[fold==k].sum()) for k in range(3)]
        eligible=int(correct.sum()-base.sum())>=5 and sum(v>0 for v in gains)>=2 and min(gains)>=-5
        records[name]={'definition':d,'oof_correct':int(correct.sum()),'oof_n':len(y),'fold_gains':gains,'cv_gate_pass':eligible,
          'validation_correct':int(vc.sum()),'validation_gain':int(vc.sum()-vbase.sum()),
          'promotion_eligible':bool(eligible and vc.sum()-vbase.sum()>=3),
          'oof_vs_baseline':paired(correct,base),'validation_vs_baseline':paired(vc,vbase)}
        all_scores[name]=ts;all_valid_scores[name]=vscore
    chosen='baseline_vote'
    eligible=[n for n,r in records.items() if r['promotion_eligible']]
    if eligible:chosen=max(eligible,key=lambda n:(records[n]['oof_correct'],records[n]['validation_correct'],-len(definitions[n]['members'])))
    # Calibration is trained on OOF distinct-answer scores, independently of test.
    # Fixed base avoids using a previously selected family to claim unbiased calibration CV.
    tb,_=load_inputs('train');ta,tc,_=answer_information(tb)
    def group_prob(scores,bank,answer_rows,temperature):
        out=[];targets=[]
        for i,answers in enumerate(answer_rows):
            groups=list(dict.fromkeys(a for a in answers if a is not None))
            logits=np.array([max(scores[i,j] for j,a in enumerate(answers) if a==g) for g in groups])/temperature
            if len(logits)<2:continue
            logits-=logits.max();p=np.exp(logits);p/=p.sum()
            out.append(p)
            targets.append([j for j,g in enumerate(groups) if any(y[i,k] and answers[k]==g for k in range(4))][0])
        return out,targets
    # Fit T on each two-fold portion; evaluate held fold. Distinct-answer log loss.
    tempgrid=[.5,.75,1.,1.5,2.,3.];base_logits=oof['baseline']+.25*(votes-1)
    calibration=[]
    group_rows=[]
    for i,answers in enumerate(ta):
        groups=list(dict.fromkeys(a for a in answers if a is not None))
        if len(groups)<2:continue
        ss=np.array([max(base_logits[i,j] for j,a in enumerate(answers) if a==g) for g in groups])
        gold=next(g for g in groups if any(y[i,j] and answers[j]==g for j in range(4)))
        group_rows.append((i,ss,groups.index(gold)))
    def nll(rows,t):
        return float(np.mean([np.logaddexp.reduce(s/t)-s[g]/t for _,s,g in rows]))
    for k in range(3):
        tr=[r for r in group_rows if fold[r[0]]!=k];he=[r for r in group_rows if fold[r[0]]==k]
        t=min(tempgrid,key=lambda t:nll(tr,t))
        calibration.append({'fold':k,'temperature':t,'held_n':len(he),'raw_nll':nll(he,1.),'calibrated_nll':nll(he,t)})
    save(out/'calibration.json',{'folds':calibration,'full_oof_temperature':min(tempgrid,key=lambda t:nll(group_rows,t)),
       'note':'Calibration does not change argmax or accuracy. Second-level OOF calibration diagnostic is not fully nested across base-model fits.'})
    # Feature stability diagnostic uses fold-local fits, not validation labels.
    coefs=np.stack([np.load(out/'fits'/f'fold{k}'/'baseline'/'model.npz')['linear_w'][1024:] for k in range(3)])
    from reasoning_features import TEXT_NAMES
    save(out/'feature-stability.json',{'text':[{'name':n,'weights':coefs[:,i].tolist(),'consistent_sign':bool(np.all(coefs[:,i]>0) or np.all(coefs[:,i]<0))} for i,n in enumerate(TEXT_NAMES)],
      'note':'Sign stability does not establish causality; no post-hoc feature refit after test.'})
    save(out/'comparison-results.json',{'records':records,'selected':chosen,'baseline_oof_correct':int(base.sum()),
       'baseline_validation_correct':int(vbase.sum()),'eligible':eligible,'oof_family_ranking':ranking,
       'notes':['CV and validation reused for selection; exploratory uncertainty only.',
                'Fixed combinations normalized by each training fit score std; no test inputs or labels read.',
                'No automatic promotion merely for highest validation count.']})
    # Freeze every bounded experimental variant before official test, including losing variants.
    variants={}
    for name,d in definitions.items():
        bundle=out/'variants'/name/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
        cfg={'ensemble':len(d['members'])>1,'alpha':d['alpha'],'seed':2026,'threads':4}
        if cfg['ensemble']:
            cfg['members']=[]
            for i,(m,w) in enumerate(zip(d['members'],d['weights'])):
                (bundle/f'member{i}.npz').write_bytes((out/'full'/m/'model.npz').read_bytes())
                cfg['members'].append({'config':configs[m],'weight':w,'score_scale':full[m]['score_scale'] if d['normalize'] else 1.})
        else:
            cfg.update(configs[d['members'][0]]);(bundle/'model.npz').write_bytes((out/'full'/d['members'][0]/'model.npz').read_bytes())
        save(bundle/'config.json',cfg);size=sum(p.stat().st_size for p in bundle.iterdir())
        assert size<=16*2**20,(name,size)
        variants[name]={'validation_correct':records[name]['validation_correct'],'assets':{p.name:digest(p) for p in bundle.iterdir()},'asset_bytes':size}
    save(out/'freeze.json',{'selected':chosen,'selection_basis':'predeclared OOF stability and validation gates, before test',
      'variants':variants,'source_sha256':{n:digest(n) for n in SOURCE_NAMES},
      'plan_sha256':digest(out/'plan.json'),'test_read_before_freeze':False})
    log({'frozen':True,'variants':len(variants),'selected':chosen,'selected_record':records[chosen]})

def evaluate(out):
    f=json.loads((out/'freeze.json').read_text())
    for n,h in f['source_sha256'].items():assert digest(n)==h,n
    assert digest(out/'plan.json')==f['plan_sha256']
    results_path=out/'official-results.json';results=json.loads(results_path.read_text()) if results_path.exists() else {}
    # Historical models are references only; current selection is already frozen.
    for name,v in f['variants'].items():
        bundle=out/'variants'/name/'model_bundle'
        for n,h in v['assets'].items():assert digest(bundle/n)==h
        if name in results:continue
        rec={}
        for split in ('validation','test'):
            r,_=official(out/'official',name,'broad_models.py',bundle,split);rec[split]=r
            if split=='validation':assert r['correct']==v['validation_correct'],(name,r,v)
        rec['asset_bytes']=v['asset_bytes'];rec['local_limits_pass']=v['asset_bytes']<=16*2**20 and rec['test']['fresh_prediction_plus_scoring_seconds']<=30
        results[name]=rec;save(results_path,results)
        log({'official':name,'validation':rec['validation']['correct'],'test':rec['test']['correct'],'seconds':rec['test']['fresh_prediction_plus_scoring_seconds']})
    manifest=json.loads(Path('PACKAGE_MANIFEST.json').read_text());assert all(digest(Path('..')/n)==h for n,h in manifest['files'].items())
    hardware={'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,'threads':4,'training_device':'cpu'}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:hardware['cpu']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    except ImportError:pass
    save(out/'compliance.json',{'hardware':hardware,'official_files_unchanged':True,
      'all_local_limits_pass':all(r['local_limits_pass'] for r in results.values()),
      'max_asset_bytes':max(r['asset_bytes'] for r in results.values()),
      'max_local_test_seconds':max(r['test']['fresh_prediction_plus_scoring_seconds'] for r in results.values()),
      'reference_cpu_tested':False,'no_external_data_or_pretrained_weights':True,
      'inference_libraries':['numpy'],'selected_before_test':f['selected']})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['prepare','train','freeze','evaluate','all'],default='all')
    parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args()
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.manual_seed(2026);torch.use_deterministic_algorithms(True)
    started=time.perf_counter();out=args.output
    for stage,fn in [('prepare',prepare),('train',train),('freeze',analysis_and_freeze),('evaluate',evaluate)]:
        if args.stage in (stage,'all'):fn(out)
    save(out/('stage-'+args.stage+'-timing.json'),{'wall_seconds':time.perf_counter()-started,'stage':args.stage})
if __name__=='__main__':main()
