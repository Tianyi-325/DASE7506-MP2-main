"""Direct answer-group training, consensus interactions, mixtures and resampling."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from common import load_inputs
from train_vector import labels
from train_objectives import group_loss
from run_fusion_experiments import save
from vector_vote_fusion import select_from_scores
from direct_group_models import inputs,membership,pool_numpy,member_scores,scores_with_assets

FAMILIES={'control':('base','candidate'),'group_mean':('base','mean'),'group_max':('base','max'),
 'group_logmeanexp':('base','logmeanexp'),'joint_candidate':('joint','candidate'),
 'joint_group':('joint','mean'),'joint_relations':('relations','logmeanexp')}


def pool_torch(s,member,mask,mode):
    if mode=='candidate':return s
    count=member.sum(dim=2).clamp_min(1)
    if mode=='mean':out=(s[:,None,:]*member).sum(dim=2)/count
    elif mode=='max':out=s[:,None,:].masked_fill(~member,-1e9).max(dim=2).values
    else:out=torch.logsumexp(s[:,None,:].masked_fill(~member,-1e9),dim=2)-count.log()
    return out.masked_fill(~mask,-1e9)


def data_loss(s,y,member,mask,group_y,mode):
    return group_loss(s,y) if mode=='candidate' else group_loss(pool_torch(s,member,mask,mode),group_y)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('runs/direct_group_round'))
    args=parser.parse_args();out=args.output
    if (out/'freeze.json').exists():raise FileExistsError('Use a new output directory')
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.manual_seed(2026);torch.use_deterministic_algorithms(True)
    started=time.perf_counter();bank,arrays=load_inputs('train');vb,va=load_inputs('validation')
    y=labels('train',bank);vy=labels('validation',vb)
    member,mask,mapping=membership(bank);vm,vk,vmap=membership(vb)
    gy=np.zeros_like(y)
    for i in range(len(y)):
        for j in np.flatnonzero(y[i]):gy[i,mapping[i,j]]=1
    assert (gy.sum(axis=1)==1).all()
    raw={kind:inputs(bank,arrays,kind) for kind in ('base','joint','relations')}
    vraw={kind:inputs(vb,va,kind) for kind in raw}
    best={};records=[];curves=[];stability=[];variants={};models={}
    def fit(family,l2,epochs,fit_index,checkpoints=(),held_index=None):
        kind,mode=FAMILIES[family];subset=raw[kind][fit_index]
        mean=subset.reshape(-1,subset.shape[-1]).mean(axis=0,dtype=np.float64).astype(np.float32)
        scale=np.maximum(subset.reshape(-1,subset.shape[-1]).std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
        x=torch.from_numpy((subset-mean)/scale);yt=torch.from_numpy(y[fit_index]);gt=torch.from_numpy(gy[fit_index])
        mt=torch.from_numpy(member[fit_index]);kt=torch.from_numpy(mask[fit_index])
        weight=torch.zeros(x.shape[-1],requires_grad=True);optimizer=torch.optim.Adam([weight],lr=.03)
        for epoch in range(1,epochs+1):
            optimizer.zero_grad(set_to_none=True);s=x.reshape(-1,x.shape[-1])@weight;s=s.reshape(-1,4)
            dl=data_loss(s,yt,mt,kt,gt,mode);loss=dl+.5*l2*weight.square().sum();loss.backward();optimizer.step()
            if checkpoints and epoch%60==0:curves.append({'family':family,'l2':l2,'epoch':epoch,'loss':float(loss.detach()),'gradient_norm_before_update':float(weight.grad.norm())})
            if epoch in checkpoints:
                w=weight.detach().numpy().astype(np.float64)/scale.astype(np.float64);bias=-float(mean.astype(np.float64)@w)
                vals=member_scores(vb,vraw[kind],vm,vk,vmap,mode,w,bias)
                counts={str(a):int(vy[np.arange(len(vb)),select_from_scores(vb,vals,'weighted',a)].sum()) for a in (0.,.25)}
                standardized=torch.from_numpy((vraw[kind]-mean)/scale)
                with torch.no_grad():vl=float(data_loss((standardized.reshape(-1,len(w))@weight).reshape(-1,4),torch.from_numpy(vy),torch.from_numpy(vm),torch.from_numpy(vk),torch.from_numpy(group_labels(vy,vmap)),mode))
                record={'family':family,'input':kind,'pool':mode,'l2':l2,'epoch':epoch,'validation_correct':counts,'validation_objective':vl}
                records.append(record);rank=(counts['0.0'],-vl)
                if family not in best or rank>best[family]['rank']:best[family]={'rank':rank,'record':record,'w':w.copy(),'b':bias}
                save(out/'progress.json',{'latest':record,'completed_checkpoints':len(records)})
                print(json.dumps(record),flush=True)
        w=weight.detach().numpy().astype(np.float64)/scale.astype(np.float64);bias=-float(mean.astype(np.float64)@w)
        return w,bias
    def group_labels(truth,maps):
        result=np.zeros_like(truth)
        for i in range(len(truth)):
            for j in np.flatnonzero(truth[i]):result[i,maps[i,j]]=1
        return result
    full=np.arange(len(bank))
    for family in FAMILIES:
        for l2 in ((.01,) if family=='control' else (.001,.01,.1)):
            fit(family,l2,120 if family=='control' else 360,full,(120,) if family=='control' else (120,360))
    def register(name,members,weights,scale_scores=True,metadata=None):
        asset={};spec=[];scales=[]
        for i,(family,w,b) in enumerate(members):
            kind,mode=FAMILIES[family];asset[f'm{i}_weight']=w;asset[f'm{i}_bias']=np.asarray(b);spec.append({'input':kind,'pool':mode,'family':family})
            s=member_scores(bank,raw[kind],member,mask,mapping,mode,w,b)
            scales.append(max(float((s-s.mean(axis=1,keepdims=True)).std()),1e-6) if scale_scores else 1.)
        asset['score_scales']=np.asarray(scales)
        config={'members':spec,'weights':list(weights),'alpha':0.,'metadata':metadata or {},'seed':2026,'device':'cpu','threads':4,
                'scaling':'train within-question centered score std' if scale_scores else 'none'}
        scores=scores_with_assets(vb,va,config,asset)
        counts={str(a):int(vy[np.arange(len(vb)),select_from_scores(vb,scores,'weighted',a)].sum()) for a in (0.,.25)}
        models[name]={'asset':asset,'config':config,'counts':counts}
        return counts,scores
    for family,b in best.items():register(family,[(family,b['w'],b['b'])],[1.],False,{'selected_training':b['record']})
    group_family=max(('group_mean','group_max','group_logmeanexp'),key=lambda n:best[n]['record']['validation_correct']['0.0'])
    joint_family=max(('joint_candidate','joint_group','joint_relations'),key=lambda n:best[n]['record']['validation_correct']['0.0'])
    # Three overlapping train-only 80/20 splits; baseline config fixed in advance.
    resampled={group_family:[],joint_family:[]}
    for seed in (17,29,43):
        rng=np.random.default_rng(seed);order=rng.permutation(len(bank));cut=int(.8*len(bank));fi=order[:cut];hi=order[cut:]
        assert not np.intersect1d(fi,hi).size
        baseline_w,baseline_b=fit('control',.01,120,fi)
        bm,bk,bmap=membership([bank[i] for i in hi]);baseline=member_scores([bank[i] for i in hi],raw['base'][hi],bm,bk,bmap,'candidate',baseline_w,baseline_b)
        base_choice=select_from_scores([bank[i] for i in hi],baseline,'weighted',.25)
        base_correct=y[hi,np.asarray(base_choice)].astype(bool)
        split_record={'seed':seed,'fit_questions':len(fi),'held_questions':len(hi),'baseline_correct':int(base_correct.sum()),'methods':{}}
        for family in (group_family,joint_family):
            config=best[family]['record'];w,b=fit(family,config['l2'],config['epoch'],fi);resampled[family].append((family,w,b))
            kind,mode=FAMILIES[family]
            s=member_scores([bank[i] for i in hi],raw[kind][hi],bm,bk,bmap,mode,w,b)
            a={}
            for alpha in (0.,.25):
                selected=select_from_scores([bank[i] for i in hi],s,'weighted',alpha);right=y[hi,np.asarray(selected)].astype(bool)
                a[str(alpha)]={'correct':int(right.sum()),'fixed':int((right&~base_correct).sum()),'broken':int((~right&base_correct).sum())}
            split_record['methods'][family]=a
        stability.append(split_record);save(out/'stability-progress.json',stability);print(json.dumps({'stability':split_record}),flush=True)
    for family,members in resampled.items():register('bag_'+family,members,[1/3]*3,True,{'training_subsets':'three 80% train resamples; seeds17,29,43','stability_note':'individual heldout diagnostics; overlapping resamples are not independent'})
    for name,left,right in [('group_joint_mix',group_family,joint_family),('group_text_mix',group_family,'control')]:
        selected=None
        for beta in (.25,.5,.75):
            members=[(n,best[n]['w'],best[n]['b']) for n in (left,right)]
            counts,scores=register(name,members,[beta,1-beta],True,{'left':left,'right':right,'left_weight':beta})
            record={'family':name,'weight':beta,'validation_correct':counts};records.append(record)
            rank=(counts['0.0'],-beta)
            if selected is None or rank>selected[0]:selected=(rank,models[name])
        models[name]=selected[1]
    for name,model in models.items():
        for alpha in (0.,.25):
            suffix='weighted' if alpha else 'valid_only';variant=name+'_'+suffix;bundle=out/variant/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
            config={**model['config'],'alpha':alpha,'family':name,'validation_correct':model['counts'][str(alpha)],'numpy':np.__version__,'torch_training':torch.__version__}
            np.savez(bundle/'model.npz',**model['asset']);save(bundle/'config.json',config)
            variants[variant]={'validation_correct':config['validation_correct'],'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(bundle.iterdir())},'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir())}
    sources=('train_direct_groups.py','evaluate_direct_groups.py','direct_group_models.py','check_direct_groups.py','reasoning_features.py',
             'train_vector.py','train_objectives.py','vector_vote_fusion.py','vector_logistic.py','run_fusion_experiments.py')
    save(out/'freeze.json',{'variants':variants,'selected':{n:b['record'] for n,b in best.items()},'group_branch':group_family,'joint_branch':joint_family,
         'source_sha256':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in sources},
         'policy':'All parameters selected by validation before test. Three internal train splits diagnose stability, not an independent final test.'})
    save(out/'training-results.json',{'records':records,'curves':curves,'stability':stability,'seconds_excluding_startup_imports':time.perf_counter()-started,
         'grid':{'l2':[.001,.01,.1],'epochs':[120,360],'lr':.03,'split_seeds':[17,29,43]},
         'notes':'Group models train directly from raw features, not from frozen base scores. Consensus interactions are jointly fitted. Bag members use only 80% training subsets.'})
    print(json.dumps({'frozen':True,'variants':{n:v['validation_correct'] for n,v in variants.items()}}),flush=True)


if __name__=='__main__':main()
