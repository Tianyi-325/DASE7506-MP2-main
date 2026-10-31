"""Bounded longer-training study: constant vs cosine LR, same linear group objective."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[k]='4'
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
import torch
from common import load_inputs
from train_vector import labels
from train_objectives import group_loss
from vector_vote_fusion import select_from_scores
from run_fusion_experiments import save

CHECKPOINTS=(360,1000,3000)
L2S=(0.0001,0.001,0.01)


def learning_rate(schedule,epoch):
    if schedule=='constant':
        return 0.01
    fraction=(epoch-1)/(max(CHECKPOINTS)-1)
    return 1e-5+0.5*(0.03-1e-5)*(1+math.cos(math.pi*fraction))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/group_long_training'))
    args=parser.parse_args()
    out=args.output
    if (out/'freeze.json').exists():
        raise FileExistsError('Use a new output directory')
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2026)
    torch.use_deterministic_algorithms(True)
    start=time.perf_counter()
    bank,arrays=load_inputs('train')
    vb,va=load_inputs('validation')
    y=labels('train',bank);vy=labels('validation',vb)
    raw=arrays['embeddings'].reshape(-1,1024)
    mean=raw.mean(axis=0,dtype=np.float64).astype(np.float32)
    std=np.maximum(raw.std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
    x=torch.from_numpy((raw-mean)/std)
    target=torch.from_numpy(y)
    vx=torch.from_numpy(((va['embeddings']-mean)/std).reshape(-1,1024))
    vt=torch.from_numpy(vy)
    records=[];curves=[];best=None
    for schedule in ('constant','cosine'):
        for l2 in L2S:
            weight=torch.zeros(1024,requires_grad=True)
            optimizer=torch.optim.Adam([weight],lr=learning_rate(schedule,1))
            tick=time.perf_counter()
            for epoch in range(1,max(CHECKPOINTS)+1):
                lr=learning_rate(schedule,epoch)
                optimizer.param_groups[0]['lr']=lr
                optimizer.zero_grad(set_to_none=True)
                scores=(x@weight).reshape(-1,4)
                data_loss=group_loss(scores,target)
                loss=data_loss+0.5*l2*weight.square().sum()
                loss.backward()
                grad=float(weight.grad.norm())
                optimizer.step()
                if epoch==1 or epoch%100==0 or epoch in CHECKPOINTS:
                    with torch.no_grad():
                        updated=(x@weight).reshape(-1,4)
                        dl=float(group_loss(updated,target))
                        curves.append({'schedule':schedule,'l2':l2,'epoch':epoch,'lr':lr,
                            'train_data_loss':dl,'train_regularized_loss':dl+0.5*l2*float(weight.square().sum()),
                            'gradient_norm_before_step':grad,'weight_norm':float(weight.norm())})
                if epoch not in CHECKPOINTS:
                    continue
                with torch.no_grad():
                    vs=(vx@weight).reshape(-1,4)
                    vl=float(group_loss(vs,vt))
                    vals=vs.numpy()
                counts={mode:int(vy[np.arange(len(vb)),select_from_scores(vb,vals,mode,alpha)].sum())
                        for mode,alpha in [('valid_only',0.),('weighted',0.25)]}
                rec={'schedule':schedule,'l2':l2,'epoch':epoch,'lr':lr,'validation_group_loss':vl,
                     'validation_correct':counts,'gradient_norm_before_step':grad,
                     'elapsed_trajectory_seconds':time.perf_counter()-tick}
                records.append(rec)
                rank=(counts['valid_only'],-vl)
                if best is None or rank>best['rank']:
                    best={'rank':rank,'record':rec,'weight':weight.detach().numpy().copy()}
                save(out/'progress.json',{'latest':rec,'completed_checkpoints':len(records),'best_validation':best['record']})
                print(json.dumps(rec),flush=True)
    folded=best['weight'].astype(np.float64)/std.astype(np.float64)
    bias=-float(mean.astype(np.float64)@folded)
    variants={}
    for mode,alpha in [('valid_only',0.),('weighted',0.25)]:
        bundle=out/mode/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
        np.savez(bundle/'model.npz',weight=folded,bias=np.asarray(bias))
        config={'mode':mode,'alpha':alpha,'training':best['record'],'objective':'multi-positive group likelihood',
                'selection':'valid_only validation accuracy, ties by validation group loss',
                'alpha_policy':'fixed 0.25; not searched','standardization':'train only folded into weight and bias',
                'device':'cpu','threads':4,'seed':2026,'numpy':np.__version__,'torch_training':torch.__version__}
        save(bundle/'config.json',config)
        count=int(vy[np.arange(len(vb)),select_from_scores(vb,va['embeddings']@folded+bias,mode,alpha)].sum())
        assert count==best['record']['validation_correct'][mode]
        variants[mode]={'validation_correct':count,'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(bundle.iterdir())},
                        'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir())}
    sources=('train_long_group.py','evaluate_long_group.py','train_objectives.py','train_vector.py',
             'vector_logistic.py','vector_vote_fusion.py','run_fusion_experiments.py')
    save(out/'freeze.json',{'selected':best['record'],'variants':variants,'grid':{'schedules':['constant','cosine'],'l2':L2S,'epochs':CHECKPOINTS},
         'cosine':{'initial':0.03,'minimum':1e-5,'total_epochs':3000},'constant_lr':0.01,
         'source_sha256':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources},
         'selection':'validation only; one common scorer for both inference modes'})
    save(out/'training-results.json',{'checkpoints':records,'curves':curves,
         'search_seconds_excluding_startup_imports':time.perf_counter()-start,
         'train_questions':len(bank),'new_trajectories':6,'total_optimizer_steps':6*max(CHECKPOINTS)})
    print(json.dumps({'frozen':True,'selected':best['record']}),flush=True)


if __name__=='__main__':
    main()
