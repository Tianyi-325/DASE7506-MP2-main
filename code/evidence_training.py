"""Fit old strong references and evidence heads; train-only preprocessing."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import time
import numpy as np
import torch
from broad_training import fit_model as old_fit,SPECS as OLD
from evidence_models import base_design,base_raw,pooled,block,extra_design,member_scores,group_margin

BASE_CONFIGS={
 'no_style':{'base':'no_style','mode':'control','block':'relative','alpha':.25},
 'joint':{'base':'joint','mode':'control','block':'relative','alpha':0.},
 'feature_selection':{'base':'feature_selection','mode':'control','block':'relative','alpha':.25}}
SPECS={n:dict(c) for n,c in BASE_CONFIGS.items()}
for base in ('no_style','joint'):
    for mode in ('refit','residual'):
        for b in ('semantic','verify','both','relative'):
            for reg in (.03,.1):
                SPECS[f'{base}_{mode}_{b}_r{int(reg*100)}']={
                  'base':base,'mode':mode,'block':b,'extra_l2':reg,'alpha':BASE_CONFIGS[base]['alpha']}
for base in ('no_style','joint'):
    for tau in (.5,1.):
        SPECS[f'{base}_gated_{int(tau*10)}']={'base':base,'mode':'gated','block':'relative','extra_l2':.1,
          'gate_tau':tau,'cap_norm':.5,'alpha':BASE_CONFIGS[base]['alpha']}
for b in ('both','relative'):
    SPECS['evidence_only_'+b]={'base':'none','mode':'evidence','block':b,'extra_l2':.03,'alpha':.25}

def torch_pool(s,data):
    member=torch.from_numpy(data['member'])
    out=(s[:,None,:]*member).sum(dim=2)/member.sum(dim=2).clamp_min(1)
    return out.masked_fill(~torch.from_numpy(data['group_mask']),-1e30)

def loss(s,y,data,kind):
    if kind in ('joint','none'):
        s=torch_pool(s,data);positive=(torch.from_numpy(data['member'])*y[:,None,:]).sum(dim=2)>0
    else:positive=y.bool()
    return (torch.logsumexp(s,dim=1)-torch.logsumexp(s.masked_fill(~positive,-torch.inf),dim=1)).mean()

def fit_base(data,y,kind):
    started=time.perf_counter();raw=data['joint'] if kind=='joint' else data['raw']
    mean=raw.reshape(-1,raw.shape[-1]).mean(axis=0,dtype=np.float64).astype(np.float32)
    scale=np.maximum(raw.reshape(-1,raw.shape[-1]).std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
    if kind!='joint':
        family='no_style' if kind=='no_style' else 'stable_features'
        learned,info=old_fit(raw,y,(data['votes']>0),None,{'mean':mean,'scale':scale},OLD[family])
        keep=np.ones(raw.shape[-1],bool)
        if kind=='no_style':
            from broad_models import STYLE
            keep[1024+np.asarray(STYLE)]=False
        else:keep=learned['stable_mask']
        a={'b_mean':mean,'b_scale':scale,'b_keep':keep,'b_weight':learned['linear_w'],'b_bias':np.asarray(0.)}
    else:
        x=torch.from_numpy((raw-mean)/scale);yt=torch.from_numpy(y);w=torch.zeros(raw.shape[-1],requires_grad=True)
        opt=torch.optim.Adam([w],lr=.03);objective=0.
        for epoch in range(360):
            opt.zero_grad(set_to_none=True);objective=loss(x@w,yt,data,kind)+.5*.01*w.square().sum()
            objective.backward();opt.step()
        folded=w.detach().numpy().astype(np.float64)/scale.astype(np.float64)
        a={'b_mean':mean,'b_scale':scale,'b_keep':np.ones(raw.shape[-1],bool),
          'b_weight':folded,'b_bias':np.asarray(-float(mean.astype(np.float64)@folded))}
        info={'epochs':360,'final_objective':float(objective.detach())}
    s=pooled(data,base_raw(data,a,kind),kind)
    a['base_score_scale']=np.asarray(max(float((s-s.mean(axis=1,keepdims=True)).std()),1e-6))
    return a,{'seconds':time.perf_counter()-started,'kind':kind,'training':info,'score_scale':float(a['base_score_scale'])}

def fit(data,y,c,base_asset=None):
    started=time.perf_counter();kind=c['base'];mode=c['mode']
    a={k:v.copy() for k,v in (base_asset or {}).items()}
    if mode=='control':
        score=member_scores(data,c,a)
        return a,{'seconds':time.perf_counter()-started,'optimizer':'frozen reference',
          'score_scale':float(a['base_score_scale']),'parameters':len(a['b_weight'])}
    ev=block(data,c['block'])
    a['e_mean']=ev.reshape(-1,ev.shape[-1]).mean(axis=0)
    a['e_scale']=np.maximum(ev.reshape(-1,ev.shape[-1]).std(axis=0),.05)
    ex=extra_design(data,a,c['block'])
    if mode=='refit':
        bx=base_design(data,a,kind);xt=torch.from_numpy(bx);et=torch.from_numpy(ex)
        target=torch.from_numpy(y);w=torch.zeros(bx.shape[-1],requires_grad=True)
        ew=torch.zeros(ex.shape[-1],requires_grad=True);opt=torch.optim.Adam([w,ew],lr=.03)
        epochs=360 if kind=='joint' else 120
        curves=[]
        for epoch in range(1,epochs+1):
            opt.zero_grad(set_to_none=True);s=xt@w+et@ew
            objective=loss(s,target,data,kind)+.5*.01*w.square().sum()+.5*c['extra_l2']*ew.square().sum()
            objective.backward();opt.step()
            if epoch in (1,120,360):curves.append({'epoch':epoch,'objective':float(objective.detach())})
        if kind=='joint':
            folded=w.detach().numpy().astype(np.float64)/a['b_scale'].astype(np.float64)
            a['b_weight']=folded;a['b_bias']=np.asarray(-float(a['b_mean'].astype(np.float64)@folded))
        else:a['b_weight']=w.detach().numpy().copy()
        a['e_weight']=ew.detach().numpy().copy()
        info={'optimizer':'full-batch Adam','epochs':epochs,'curves':curves}
        with torch.no_grad():expected=(xt[:13]@w+et[:13]@ew).numpy()
        expected=pooled({k:v[:13] for k,v in data.items()},expected,kind)
    else:
        offset=base_raw(data,a,kind);ot=torch.from_numpy(offset).double();et=torch.from_numpy(ex).double()
        target=torch.from_numpy(y).double();ew=torch.zeros(ex.shape[-1],dtype=torch.float64,requires_grad=True)
        opt=torch.optim.LBFGS([ew],lr=1.,max_iter=100,max_eval=140,history_size=12,
          tolerance_grad=1e-7,tolerance_change=1e-11,line_search_fn='strong_wolfe')
        gate=None;cap=1.
        if mode=='gated':
            old=pooled(data,offset,kind);margin=group_margin(data,old)/float(a['base_score_scale'])
            available=(data['verify'][:,:,0]>0).any(axis=1)|(data['semantic'][:,:,2]>0).any(axis=1)|(data['semantic'][:,:,5]>0).any(axis=1)
            gate=torch.from_numpy((margin<=c['gate_tau'])&available)[:,None]
            cap=c['cap_norm']*float(a['base_score_scale'])
        def forward():
            correction=et@ew
            if gate is not None:correction=gate*cap*torch.tanh(correction/max(cap,1e-6))
            return ot+correction
        def closure():
            opt.zero_grad(set_to_none=True);obj=loss(forward(),target,data,kind)+.5*c['extra_l2']*ew.square().sum()
            obj.backward();return obj
        initial=float(closure().detach());opt.step(closure);final=float(closure().detach())
        a['e_weight']=ew.detach().numpy().copy()
        state=opt.state[ew]
        info={'optimizer':'LBFGS fixed-base correction','iterations':state.get('n_iter'),
          'evaluations':state.get('func_evals'),'initial_objective':initial,'final_objective':final,
          'gradient_norm':float(ew.grad.norm()),'active_gate_questions':int(gate.sum()) if gate is not None else len(y)}
        expected=pooled(data,forward().detach().numpy(),kind)[:13]
    score=member_scores(data,c,a);err=float(abs(score[:13]-expected).max())
    assert np.allclose(score[:13],expected,atol=2e-4,rtol=2e-5),(c,err)
    info.update(seconds=time.perf_counter()-started,parameters=sum(v.size for k,v in a.items() if k in ('b_weight','e_weight')),
      extra_features=ex.shape[-1],probe_max_difference=err,
      score_scale=max(float((score-score.mean(axis=1,keepdims=True)).std()),1e-6))
    return a,info
