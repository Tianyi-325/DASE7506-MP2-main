"""Bounded priority-ordered refinements. All fits use train; selection uses validation."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from torch import nn
from common import load_inputs
from train_vector import labels
from train_objectives import group_loss
from run_fusion_experiments import save
from vector_vote_fusion import answer_information,select_from_scores
from refinement_models import raw_features,stack_features,score_assets,lexical_counts,DIMS


def standardize(raw,ix):
    selected=raw[:,:,ix]
    mean=selected.reshape(-1,len(ix)).mean(axis=0,dtype=np.float64).astype(np.float32)
    scale=np.maximum(selected.reshape(-1,len(ix)).std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
    return torch.from_numpy((selected-mean)/scale),mean,scale


def folded(weight,mean,scale,ix):
    vector=np.zeros(DIMS,dtype=np.float64);vector[ix]=weight.detach().numpy()/scale.astype(np.float64)
    return {'weight':vector,'bias':np.asarray(-float(mean.astype(np.float64)@vector[ix]))}


def reference_linear(bundle,ix):
    with np.load(bundle/'model.npz',allow_pickle=False) as a:
        mean=np.concatenate([a['embedding_mean'],a['feature_mean']]);scale=np.concatenate([a['embedding_scale'],a['feature_scale']])
        w=a['linear_weight'].reshape(-1).astype(np.float64)/scale.astype(np.float64)
        result=np.zeros(DIMS,dtype=np.float64);result[ix]=w
        return result,float(a['linear_bias'].item()-mean.astype(np.float64)@w)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('runs/priority_refinements'))
    args=parser.parse_args();out=args.output
    if (out/'freeze.json').exists():raise FileExistsError('Use a new output directory')
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(2026)
    started=time.perf_counter();bank,arrays=load_inputs('train');vb,va=load_inputs('validation')
    raw=raw_features(bank,arrays);vraw=raw_features(vb,va);y=labels('train',bank);vy=labels('validation',vb);target=torch.from_numpy(y)
    _,_,votes=answer_information(bank)
    _,_,validation_votes=answer_information(vb)
    choices=np.arange(len(vb));records=[];best={};curves=[]
    def consider(family,kind,assets,metadata,loss,alphas=(0.,0.25),joint_alpha=False):
        config={'kind':kind,**metadata,'alpha':0.}
        vals=score_assets(vb,vraw,config,assets)
        counts={str(a):int(vy[choices,select_from_scores(vb,vals,'weighted',a)].sum()) for a in alphas}
        alpha=max(alphas,key=lambda a:(counts[str(a)],-a)) if joint_alpha else 0.
        selected_vals=vals+alpha*(validation_votes-1)
        validation_loss=float(group_loss(torch.from_numpy(np.where(validation_votes>0,selected_vals,-1e9)),torch.from_numpy(vy)))
        rank=(counts[str(alpha)],-validation_loss)
        record={'family':family,'kind':kind,'metadata':metadata,'validation_correct':counts,'validation_group_loss':validation_loss,'training_objective':float(loss)}
        records.append(record)
        if family not in best or rank>best[family]['rank']:
            best[family]={'rank':rank,'assets':{k:np.array(v,copy=True) for k,v in assets.items()},'record':record,'alphas':(alpha,) if joint_alpha else alphas}
        save(out/'progress.json',{'latest':record,'completed_validation_checks':len(records)})
        print(json.dumps(record),flush=True)
    # Priorities 1-2: five folds by QUESTION, fixed previous base configurations.
    embed=list(range(1024));text=embed+list(range(1024,1046));calc=embed+list(range(1046,1054))
    definitions=[('linear_text',text,0.01,120),('linear_calc',calc,0.01,120),('linear_control',embed,0.001,360)]
    rng=np.random.default_rng(2026);permutation=rng.permutation(len(bank));folds=np.empty(len(bank),dtype=int)
    for fold,index in enumerate(np.array_split(permutation,5)):folds[index]=fold
    oof=np.zeros((len(bank),4,3));base_weight=[];base_bias=[]
    prior=Path('runs/remaining_directions');prior_freeze=json.loads((prior/'freeze.json').read_text())
    for m,(name,ix,l2,epochs) in enumerate(definitions):
        bundle=prior/(name+'_valid_only')/'model_bundle'
        for file,h in prior_freeze['variants'][name+'_valid_only']['assets'].items():assert hashlib.sha256((bundle/file).read_bytes()).hexdigest()==h
        fullw,fullb=reference_linear(bundle,ix);base_weight.append(fullw);base_bias.append(fullb)
        for fold in range(5):
            fit=np.flatnonzero(folds!=fold);hold=np.flatnonzero(folds==fold);assert not np.intersect1d(fit,hold).size
            x,mean,scale=standardize(raw[fit],ix);xt=x.reshape(-1,len(ix));yt=target[fit]
            weight=torch.zeros(len(ix),requires_grad=True);optimizer=torch.optim.Adam([weight],lr=0.03)
            tick=time.perf_counter()
            for epoch in range(epochs):
                optimizer.zero_grad(set_to_none=True);logits=(xt@weight).reshape(-1,4)
                loss=group_loss(logits,yt)+0.5*l2*weight.square().sum();loss.backward();optimizer.step()
            asset=folded(weight,mean,scale,ix);oof[hold,:,m]=raw[hold]@asset['weight']+asset['bias']
            print(json.dumps({'oof_model':name,'fold':fold,'fit_questions':len(fit),'held_questions':len(hold),'seconds':time.perf_counter()-tick}),flush=True)
    save(out/'oof-split.json',{'seed':2026,'fold_by_train_position':folds.tolist(),'questions':len(bank),'folds':5,
        'fit_policy':'Each held question and all its candidates excluded from fitting AND standardization; no validation labels used in OOF fitting.'})
    np.savez(out/'oof-training-scores.npz',scores=oof)
    centered=oof-oof.mean(axis=1,keepdims=True)
    base_scale=np.maximum(centered.reshape(-1,3).std(axis=0),1e-6)
    common={'base_weight':np.asarray(base_weight),'base_bias':np.asarray(base_bias),'base_scale':base_scale}
    obase=centered/base_scale
    vbase=(vraw@common['base_weight'].T+common['base_bias']);vbase=(vbase-vbase.mean(axis=1,keepdims=True))/base_scale
    blends=[(1,0,0),(.75,.25,0),(.5,.5,0),(.75,0,.25),(.5,0,.5),(.5,.25,.25)]
    for weights in blends:
        a={**common,'blend_weight':np.asarray(weights)}
        consider('simple_blend','blend',a,{'weights':weights,'scaling':'train OOF centered standard deviation'},0.,alphas=(0.,.25,.5),joint_alpha=True)
    gf,gmask,mapping=stack_features(bank,raw,obase)
    gy=np.zeros((len(bank),4),dtype=np.float32)
    for i in range(len(bank)):
        for j in np.flatnonzero(y[i]):gy[i,mapping[i,j]]=1
    candidate=np.concatenate([obase,votes[:,:,None]],axis=-1)
    for family,kind,data,mask,truth,regularizers in [
        ('candidate_stack','candidate_stack',candidate,votes>0,y,(.001,.01,.1)),
        ('answer_group_linear','group_linear',gf,gmask,gy,(.001,.01,.1)),
        ('answer_group_mlp','group_mlp',gf,gmask,gy,(.001,.01))]:
        valid=data[mask];mean=valid.mean(axis=0);scale=np.maximum(valid.std(axis=0),1e-6)
        x=torch.from_numpy(((data-mean)/scale).astype(np.float32));yt=torch.from_numpy(truth);mt=torch.from_numpy(mask)
        for l2 in regularizers:
            torch.manual_seed(2026)
            model=(nn.Sequential(nn.Linear(x.shape[-1],16),nn.ReLU(),nn.Linear(16,1,bias=False)) if kind=='group_mlp' else nn.Linear(x.shape[-1],1,bias=False))
            if kind!='group_mlp':nn.init.zeros_(model.weight)
            optimizer=torch.optim.Adam(model.parameters(),lr=.01 if kind=='group_mlp' else .03)
            for epoch in range(1,301):
                optimizer.zero_grad(set_to_none=True);s=model(x).squeeze(-1).masked_fill(~mt,-1e9)
                loss=group_loss(s,yt)+.5*l2*sum(p.square().sum() for p in model.parameters());loss.backward();optimizer.step()
                if epoch not in (100,300):continue
                a={**common,'meta_mean':mean,'meta_scale':scale}
                if kind=='group_mlp':a.update({'meta_hidden_weight':model[0].weight.detach().numpy().T,'meta_hidden_bias':model[0].bias.detach().numpy(),'meta_weight':model[2].weight.detach().numpy().reshape(-1)})
                else:a['meta_weight']=model.weight.detach().numpy().reshape(-1)
                consider(family,kind,a,{'l2':l2,'epoch':epoch,'meta_fit':'question-level train OOF scores; full-train bases at inference'},float(loss.detach()),alphas=(0.,))
    # Priority 3: text blocks and block-wise regularization, no stacked in-sample scores.
    subsets={'numeric_only':embed+[1024+i for i in (6,7,16,17,18,19,20)],
             'style_only':embed+[1024+i for i in (0,1,2,3,8,9,10,11,12,13,14,21)],
             'no_style':embed+[1024+i for i in (4,5,6,7,15,16,17,18,19,20)]}
    experiments=[(name,ix,'group',.01,.01,0.) for name,ix in subsets.items()]
    experiments += [('block_regularized',text,'group',be,fe,0.) for be in (.001,.01) for fe in (.0001,.001,.01)]
    # Priorities 4-5: joint objective, pairwise comparisons and train-label-defined hard weighting.
    experiments += [('joint_bce',text,'joint',.01,.01,l) for l in (.1,.3)]
    experiments += [('pairwise',text,'pairwise',.01,.01,0.),('hard_weighted',text,'hard',.01,.01,0.)]
    for family,ix,objective,be,fe,mix in experiments:
        x,mean,scale=standardize(raw,ix);xt=x.reshape(-1,len(ix));weight=torch.zeros(len(ix),requires_grad=True)
        intercept=torch.tensor(float(np.log(y.mean()/(1-y.mean()))) if objective=='joint' else 0.,requires_grad=objective=='joint')
        optimizer=torch.optim.Adam([weight,intercept] if objective=='joint' else [weight],lr=.03);penalty=torch.tensor([be if i<1024 else fe for i in ix],dtype=torch.float32)
        pair_mask=target[:,:,None].bool()&~target[:,None,:].bool();pair_count=pair_mask.sum(dim=(1,2)).clamp_min(1)
        hard=torch.where(target.sum(dim=1)==1,2.,1.)
        for epoch in range(1,361):
            optimizer.zero_grad(set_to_none=True);s=(xt@weight+intercept).reshape(-1,4)
            if objective=='joint':dl=group_loss(s,target)+mix*torch.nn.functional.binary_cross_entropy_with_logits(s,target)
            elif objective=='pairwise':
                differences=s[:,:,None]-s[:,None,:]
                dl=((torch.nn.functional.softplus(-differences)*pair_mask).sum(dim=(1,2))/pair_count).mean()
            elif objective=='hard':
                row=torch.logsumexp(s,1)-torch.logsumexp(s.masked_fill(~target.bool(),-torch.inf),1);dl=(row*hard).mean()
            else:dl=group_loss(s,target)
            loss=dl+.5*(penalty*weight.square()).sum();loss.backward();optimizer.step()
            if epoch%60==0:curves.append({'family':family,'objective':objective,'embedding_l2':be,'feature_l2':fe,'mix':mix,'epoch':epoch,'loss':float(loss.detach())})
            if epoch not in (120,360):continue
            a=folded(weight,mean,scale,ix);a['bias']+=float(intercept.detach())
            consider(family,'linear',a,{'objective':objective,'embedding_l2':be,'feature_l2':fe,'mix':mix,'epoch':epoch,'feature_columns':ix[1024:]},float(loss.detach()))
    # Priority 6: training-only hashed unigram/bigram TF-IDF, with numeric identities normalized.
    x,mean,scale=standardize(raw,text);xt=x.reshape(-1,len(text))
    for dims,l2 in [(8192,.001),(16384,.01)]:
        docs=[];df=np.zeros(dims,dtype=np.float64)
        for row in bank:
            for c in row['candidates']:
                idx,count=lexical_counts(c['text'],dims);docs.append((idx,count));df[idx]+=1
        idf=np.log((1+len(docs))/(1+df))+1
        rows=[];cols=[];values=[]
        for i,(idx,count) in enumerate(docs):
            value=count*idf[idx];value=value/max(np.linalg.norm(value),1e-12)
            rows.extend([i]*len(idx));cols.extend(idx.tolist());values.extend(value.tolist())
        sparse=torch.sparse_coo_tensor(torch.tensor([rows,cols]),torch.tensor(values,dtype=torch.float32),(len(docs),dims)).coalesce()
        weight=torch.zeros(len(text),requires_grad=True);lw=torch.zeros(dims,requires_grad=True)
        optimizer=torch.optim.Adam([weight,lw],lr=.03)
        for epoch in range(1,361):
            optimizer.zero_grad(set_to_none=True);s=(xt@weight+torch.sparse.mm(sparse,lw[:,None]).squeeze(1)).reshape(-1,4)
            loss=group_loss(s,target)+.5*.01*weight.square().sum()+.5*l2*lw.square().sum();loss.backward();optimizer.step()
            if epoch not in (120,360):continue
            a={**folded(weight,mean,scale,text),'lexical_weight':lw.detach().numpy(),'idf':idf}
            consider('lexical_tfidf','lexical',a,{'hash_dimensions':dims,'token_l2':l2,'base_l2':.01,'epoch':epoch,'tokenization':'candidate word unigrams/bigrams; numeric identities normalized; CRC32 hashing; train-only IDF'},float(loss.detach()))
    variants={}
    for family,b in best.items():
        for alpha in b['alphas']:
            suffix='weighted' if alpha else 'valid_only';name=family+'_'+suffix;bundle=out/name/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
            config={'kind':b['record']['kind'],'family':family,'alpha':alpha,'selection':b['record'],
                'device':'cpu','threads':4,'seed':2026,'numpy':np.__version__,'torch_training':torch.__version__}
            np.savez(bundle/'model.npz',**b['assets']);save(bundle/'config.json',config)
            count=int(vy[choices,select_from_scores(vb,score_assets(vb,vraw,config,b['assets']),'weighted',alpha)].sum())
            variants[name]={'validation_correct':count,'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(bundle.iterdir())},
                            'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir())}
    sources=('train_refinements.py','evaluate_refinements.py','refinement_models.py','reasoning_features.py','vector_vote_fusion.py','vector_logistic.py',
             'train_objectives.py','train_vector.py','run_fusion_experiments.py','check_refinements.py')
    save(out/'freeze.json',{'variants':variants,'selected':{n:b['record'] for n,b in best.items()},
        'source_sha256':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in sources},
        'validation_preferred':max(variants,key=lambda n:variants[n]['validation_correct']),
        'data_policy':'Train-only fitting including fold-local preprocessing and IDF; validation selection; test only after freeze.'})
    save(out/'training-results.json',{'records':records,'curves':curves,'seconds_excluding_startup_imports':time.perf_counter()-started,
         'oof_fits':15,'oof_folds':5,'base_order':[d[0] for d in definitions],
         'candidate_families':list(best),'notes':'OOF meta fitting uses out-of-fold bases; full-data base deployment can shift score distributions. No outer nested CV was performed.'})
    print(json.dumps({'frozen':True,'variants':{n:v['validation_correct'] for n,v in variants.items()}}),flush=True)


if __name__=='__main__':main()
