"""Matched CPU search: candidate BCE vs multi-positive group likelihood."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='4'
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
import torch.nn.functional as F
from common import load_inputs
from train_vector import labels
from vector_vote_fusion import select_from_scores

LRS=(0.01,0.03)
L2S=(0.0001,0.001,0.01)
EPOCHS=(120,360,1000)


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+chr(10),encoding='utf-8')


def group_loss(scores,positive):
    # Probability mass of ANY correct candidate, never a single arbitrary gold.
    return (torch.logsumexp(scores,dim=1)-torch.logsumexp(scores.masked_fill(~positive.bool(),-torch.inf),dim=1)).mean()


def loss_of(scores,target,objective):
    return F.binary_cross_entropy_with_logits(scores,target) if objective=='bce' else group_loss(scores,target)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/vector_objectives'))
    args=parser.parse_args()
    out=args.output
    if (out/'freeze.json').exists():
        raise FileExistsError('Choose a new output directory to retain the frozen run')
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2026)
    torch.use_deterministic_algorithms(True)
    started=time.perf_counter()
    bank,arrays=load_inputs('train')
    vb,va=load_inputs('validation')
    y=labels('train',bank)
    vy=labels('validation',vb)
    raw=arrays['embeddings'].reshape(-1,1024)
    mean=raw.mean(axis=0,dtype=np.float64).astype(np.float32)
    scale=np.maximum(raw.std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
    x=torch.from_numpy(((raw-mean)/scale).reshape(-1,4,1024))
    tx=x.reshape(-1,1024)
    target=torch.from_numpy(y)
    vx=torch.from_numpy(((va['embeddings']-mean)/scale).reshape(-1,1024))
    vt=torch.from_numpy(vy)
    records=[]
    curves=[]
    best={}
    for objective in ('bce','group'):
        for lr in LRS:
            for l2 in L2S:
                weight=torch.zeros(1024,requires_grad=True)
                # Group likelihood is invariant to a common intercept.
                bias=torch.tensor(float(np.log(y.mean()/(1-y.mean()))) if objective=='bce' else 0.,requires_grad=objective=='bce')
                optimizer=torch.optim.Adam([weight,bias] if objective=='bce' else [weight],lr=lr)
                tick=time.perf_counter()
                for epoch in range(1,max(EPOCHS)+1):
                    optimizer.zero_grad(set_to_none=True)
                    scores=(tx@weight+bias).reshape(-1,4)
                    data_loss=loss_of(scores,target,objective)
                    loss=data_loss+0.5*l2*weight.square().sum()
                    loss.backward()
                    grad_norm=float(torch.sqrt(weight.grad.square().sum()+(bias.grad.square() if objective=='bce' else 0)))
                    optimizer.step()
                    if epoch==1 or epoch%20==0:
                        with torch.no_grad():
                            after=(tx@weight+bias).reshape(-1,4)
                            dl=float(loss_of(after,target,objective))
                            curves.append({'objective':objective,'lr':lr,'l2':l2,'epoch':epoch,
                                           'train_data_loss':dl,'train_regularized_loss':dl+0.5*l2*float(weight.square().sum()),
                                           'gradient_norm_before_step':grad_norm,'weight_norm':float(weight.norm())})
                    if epoch not in EPOCHS:
                        continue
                    with torch.no_grad():
                        vs=(vx@weight+bias).reshape(-1,4)
                        validation_loss=float(loss_of(vs,vt,objective))
                        vals=vs.numpy()
                    counts={}
                    for name,alpha in [('valid_only',0.),('weighted',0.25)]:
                        choices=select_from_scores(vb,vals,name,alpha)
                        counts[name]=int(vy[np.arange(len(vb)),choices].sum())
                    rec={'objective':objective,'lr':lr,'l2':l2,'epoch':epoch,'validation_loss':validation_loss,
                         'validation_correct':counts,'gradient_norm_before_step':grad_norm,
                         'elapsed_path_seconds':time.perf_counter()-tick}
                    records.append(rec)
                    # One scorer per objective: select using valid-only accuracy.
                    # Fixed-alpha fusion is a secondary comparison, not a second search.
                    rank=(counts['valid_only'],-validation_loss)
                    if objective not in best or rank>best[objective]['rank']:
                        best[objective]={'rank':rank,'record':rec,'w':weight.detach().numpy().copy(),'b':float(bias.detach())}
                    print(json.dumps(rec),flush=True)
    variants={}
    for objective,chosen in best.items():
        weight=chosen['w'].astype(np.float64)/scale.astype(np.float64)
        bias=chosen['b']-float(mean.astype(np.float64)@weight)
        for mode,alpha in [('valid_only',0.),('weighted',0.25)]:
            name=f'{objective}_{mode}'
            bundle=out/name/'model_bundle'
            bundle.mkdir(parents=True,exist_ok=True)
            np.savez(bundle/'model.npz',weight=weight,bias=np.asarray(bias))
            config={'mode':mode,'alpha':alpha,'objective':objective,'training':chosen['record'],
                    'seed':2026,'device':'cpu','threads':4,'optimizer':'full batch Adam',
                    'selection':'valid_only validation accuracy then objective validation loss',
                    'fusion_alpha':'fixed at 0.25, not retuned','standardization':'train only, folded into exported weight/bias',
                    'group_formula':'logsumexp(all logits)-logsumexp(correct logits)',
                    'numpy':np.__version__,'torch_training':torch.__version__}
            save(bundle/'config.json',config)
            actual=select_from_scores(vb,va['embeddings']@weight+bias,mode,alpha)
            count=int(vy[np.arange(len(vb)),actual].sum())
            assert count==chosen['record']['validation_correct'][mode]
            variants[name]={'objective':objective,'mode':mode,'validation_correct':count,
                            'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(bundle.iterdir())},
                            'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir())}
    sources=('train_objectives.py','train_vector.py','vector_vote_fusion.py','vector_logistic.py','evaluate_objectives.py','check_objectives.py')
    freeze={'selection_data':'validation only','variants':variants,'grid':{'lr':LRS,'l2':L2S,'epochs':EPOCHS},
            'selected':{key:value['record'] for key,value in best.items()},
            'source_sha256':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources},
            'validation_preferred_variant':max(variants,key=lambda name:variants[name]['validation_correct'])}
    save(out/'freeze.json',freeze)
    save(out/'training-results.json',{'grid_records':records,'training_curves':curves,
         'training_search_seconds_excluding_startup_imports':time.perf_counter()-started,
         'training_questions':len(y),'all_correct_train_questions':int((y.sum(axis=1)==4).sum()),
         'group_informative_train_questions':int((y.sum(axis=1)<4).sum()),
         'note':'All-positive questions have zero group data loss. Group bias fixed at zero. Same grid does not make BCE/group regularization scales equivalent.'})
    print(json.dumps({'selected':freeze['selected'],'variants':{k:v['validation_correct'] for k,v in variants.items()}}),flush=True)


if __name__=='__main__':
    main()
