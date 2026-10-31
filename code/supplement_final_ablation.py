"""Post-hoc fixed-B ablations: missing S/V/R input subsets, plus matched evidence-only.
No selection and no changes to the historical B checkpoint.
"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,json,time,hashlib,sys
from pathlib import Path
import numpy as np
from common import load_inputs
from run_fusion_experiments import labels,official
from evidence_models import subset,member_scores,predict
from evidence_training import fit
SRC=Path('runs/evidence_round');OUT=Path('runs/final_ablation')
SPECS={
 'R_only':{'semantic':False,'verify':False,'relative':True},
 'SR_without_direct_V':{'semantic':True,'verify':False,'relative':True},
 'VR_without_direct_S':{'semantic':False,'verify':True,'relative':True}}
CONFIG={'base':'joint','mode':'residual','block':'relative','extra_l2':.03,'alpha':0.}
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load_asset(p):
    with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in z.files}
def correctness(bank,y,s):return y[np.arange(len(y)),__import__('vector_vote_fusion').select_from_scores(bank,s,'weighted',0.)].astype(int)
def freeze():
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    if (OUT/'freeze.json').exists():raise RuntimeError('Already frozen; use evaluate')
    OUT.mkdir(parents=True,exist_ok=True)
    plan={'purpose':'Post-hoc explanation of fixed B, no model selection','new_subsets':SPECS,
      'architecture':CONFIG,'two_seeds':[211,509],'folds':3,
      'reuse':'Existing fold-local bases and train/validation feature cache; no historical test rows used',
      'important':'S/V/R are direct feature blocks. R is derived from S/V evidence, so removing direct S/V does not remove their upstream information.',
      'additional_control':'evidence_only_relative weights with alpha=0, identical group objective/L2 to B',
      'source_sha256':{p:digest(Path(p)) for p in ['supplement_final_ablation.py','evidence_models.py','evidence_training.py','math_evidence.py']}}
    if (OUT/'plan.json').exists():assert json.loads((OUT/'plan.json').read_text(encoding='utf8'))==plan
    else:save(OUT/'plan.json',plan)
    start=time.perf_counter()
    tb,ta=load_inputs('train');vb,va=load_inputs('validation');del ta
    ty=labels(tb,'train');vy=labels(vb,'validation')
    with np.load(SRC/'input-cache.npz',allow_pickle=False) as z:
        td={k[2:]:z[k] for k in z.files if k.startswith('t_')};vd={k[2:]:z[k] for k in z.files if k.startswith('v_')}
    with np.load(SRC/'folds.npz',allow_pickle=False) as z:folds={k:z[k] for k in z.files}
    configs={n:CONFIG.copy() for n in SPECS};configs['evidence_only_alpha0']={'base':'none','mode':'evidence','block':'relative','extra_l2':.03,'alpha':0.}
    oof={n:np.zeros((2,len(tb),4)) for n in configs};full={};valid={};infos={}
    for r in range(3):
        for f in (range(3) if r<2 else [0]):
            tag='full' if r==2 else f'seed{(211,509)[r]}_fold{f}'
            ti=np.arange(len(tb)) if r==2 else np.flatnonzero(folds[str((211,509)[r])]!=f)
            hi=np.arange(len(vb)) if r==2 else np.flatnonzero(folds[str((211,509)[r])]==f)
            tr=subset(td,ti);held=vd if r==2 else subset(td,hi)
            base=load_asset(SRC/'fits'/tag/'joint-base.npz')
            for n,c in configs.items():
                path=OUT/'fits'/tag/(n+'.npz');meta=path.with_suffix('.json')
                if path.exists():asset=load_asset(path);info=json.loads(meta.read_text(encoding='utf8'))
                elif n=='evidence_only_alpha0':
                    asset=load_asset(SRC/'fits'/tag/'evidence_only_relative.npz')
                    info={'reused_fit':str(SRC/'fits'/tag/'evidence_only_relative.npz'),'seconds':0.}
                    path.parent.mkdir(parents=True,exist_ok=True);np.savez(path,**asset);save(meta,info)
                else:
                    masked={k:(np.zeros_like(v) if k in SPECS[n] and not SPECS[n][k] else v) for k,v in tr.items()}
                    asset,info=fit(masked,ty[ti],c,base)
                    keep=np.concatenate([np.full(td[k].shape[-1],SPECS[n][k]) for k in ('semantic','verify','relative')])
                    assert np.all(asset['e_weight'][~keep]==0)
                    info.update(retained_feature_count=int(keep.sum()),removed_weights_exactly_zero=True)
                    path.parent.mkdir(parents=True,exist_ok=True);np.savez(path,**asset);save(meta,info)
                scores=member_scores(held,c,asset)
                if r==2:full[n]=asset;infos[n]=info;valid[n]=scores
                else:oof[n][r,hi]=scores
                print(json.dumps({'tag':tag,'variant':n,'seconds':info['seconds']}),flush=True)
    records={}
    for n,c in configs.items():
        bundle=OUT/'variants'/n/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
        np.savez(bundle/'member0.npz',**full[n]);save(bundle/'config.json',{'alpha':0.,'members':[{'config':c,'weight':1.,'scale':1.}]})
        cv=correctness(vb,vy,valid[n]);co=[correctness(tb,ty,oof[n][r]) for r in range(2)]
        # Serialization and inference match cached feature scoring.
        p=predict(vb[:7],{'embeddings':va['embeddings'][:7]},bundle)
        expected=__import__('vector_vote_fusion').select_from_scores(vb[:7],valid[n][:7],'weighted',0.)
        assert p==expected
        records[n]={'oof_correct':[int(x.sum()) for x in co],'validation_correct':int(cv.sum()),
          'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir()),
          'assets':{p.name:digest(p) for p in bundle.iterdir()},'config':c,'training':infos[n]}
    np.savez(OUT/'oof-scores.npz',**oof)
    save(OUT/'freeze.json',{'variants':records,'source_sha256':plan['source_sha256'],
      'elapsed_seconds':time.perf_counter()-start,'fixed_B':'joint_residual_relative_r3',
      'B_assets_sha256':json.loads((SRC/'freeze.json').read_text(encoding='utf8'))['variants']['joint_residual_relative_r3']['assets'],
      'new_model_selection':False,'post_hoc_analysis':True})
def evaluate():
    f=json.loads((OUT/'freeze.json').read_text(encoding='utf8'))
    for p,h in f['source_sha256'].items():assert digest(Path(p))==h
    results=json.loads((OUT/'official-results.json').read_text(encoding='utf8')) if (OUT/'official-results.json').exists() else {}
    for n,v in f['variants'].items():
        bundle=OUT/'variants'/n/'model_bundle'
        for p,h in v['assets'].items():assert digest(bundle/p)==h
        results.setdefault(n,{})
        for split in ('validation','test'):
            if split in results[n]:continue
            score,_=official(OUT/'official',n,'evidence_models.py',bundle,split)
            if split=='validation':assert score['correct']==v['validation_correct']
            results[n][split]=score;save(OUT/'official-results.json',results)
            print(json.dumps({'variant':n,'split':split,**score}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['freeze','evaluate'],required=True)
    (freeze if p.parse_args().stage=='freeze' else evaluate)()
