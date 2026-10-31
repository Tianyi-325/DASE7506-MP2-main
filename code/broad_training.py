"""Bounded CPU training implementations; borrowed architectures, no external weights."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import math,time,copy
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from broad_models import design,model_scores

SPECS={
 'baseline':dict(arch='linear',design='base',epochs=120,l2=.01),
 'gbdt':dict(arch='tree',design='compact',epochs=100,objective='bce',depth=3),
 'lambdamart':dict(arch='tree',design='compact',epochs=100,objective='lambda',depth=3),
 'gam':dict(arch='linear',design='gam',epochs=180,l2=.02),
 'fm':dict(arch='fm',design='base',epochs=60,l2=.01),
 'rff':dict(arch='linear',design='rff',epochs=180,l2=.01),
 'charcnn':dict(arch='cnn',design='base',epochs=12,l2=.01),
 'supcon':dict(arch='supcon',design='base',epochs=20,l2=.01),
 'extended_features':dict(arch='linear',design='full',epochs=120,l2=.01),
 'supervision_balanced':dict(arch='linear',design='base',epochs=120,l2=.01,balanced=True),
 'valid_training_mask':dict(arch='linear',design='base',epochs=120,l2=.01,mask=True),
 'stable_features':dict(arch='linear',design='stable',epochs=120,l2=.01),
 'no_style':dict(arch='linear',design='nostyle',epochs=120,l2=.01),
 'numeric_quality':dict(arch='linear',design='quality',epochs=120,l2=.01),
 'residual':dict(arch='residual',design='base',epochs=20,l2=.01,width=16),
 'residual_width32':dict(arch='residual',design='base',epochs=20,l2=.01,width=32),
 'residual_dropout':dict(arch='residual',design='base',epochs=20,l2=.01,width=16,dropout=.2),
 'residual_adam_l2':dict(arch='residual',design='base',epochs=20,l2=.01,width=16,adam_l2=True),
 'linear_lbfgs':dict(arch='linear',design='base',epochs=60,l2=.01,lbfgs=True),
 'linear_earlystop':dict(arch='linear',design='base',epochs=360,l2=.01,earlystop=True),
 'residual_batch128':dict(arch='residual',design='base',epochs=20,l2=.01,width=16,batch=128),
 'residual_ema':dict(arch='residual',design='base',epochs=20,l2=.01,width=16,average='ema'),
 'residual_swa':dict(arch='residual',design='base',epochs=20,l2=.01,width=16,average='swa'),
 'residual_sam':dict(arch='residual',design='base',epochs=20,l2=.01,width=16,sam=True),
}

def preprocess(raw):
    flat=raw.reshape(-1,raw.shape[-1])
    mean=flat.mean(axis=0,dtype=np.float64).astype(np.float32)
    scale=np.maximum(flat.std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
    x=np.clip((raw-mean)/scale,-20,20);a={'mean':mean,'scale':scale}
    torch.manual_seed(77)
    with torch.no_grad():
        _,_,v=torch.pca_lowrank(torch.from_numpy(x[:,:,:1024].reshape(-1,1024)),q=32,center=False,niter=2)
    a['pca']=v.numpy()
    a['knots']=np.quantile(x[:,:,1024:].reshape(-1,50),[.2,.4,.6,.8],axis=0).T.astype(np.float32)
    rng=np.random.default_rng(77);a['rff_w']=rng.normal(0,.15,(82,128)).astype(np.float32)
    a['rff_b']=rng.uniform(0,2*np.pi,128).astype(np.float32)
    return a

def select_quality(x):
    # Old arithmetic is replaced by stricter checks; keep text, consensus, semantic flags.
    return np.concatenate([x[:,:,:1046],x[:,:,1054:]],axis=-1)

def data_loss(s,y,config,weights=None,valid=None):
    if config.get('mask'):s=s.masked_fill(~valid,-1e9)
    each=torch.logsumexp(s,dim=1)-torch.logsumexp(s.masked_fill(~y.bool(),-torch.inf),dim=1)
    return each.mean() if weights is None else (each*weights).sum()/weights.sum()

def linear_fit(x,y,config,valid,eval_data=None,forced_epochs=None):
    xt=torch.from_numpy(x);yt=torch.from_numpy(y);vt=torch.from_numpy(valid)
    w=torch.zeros(x.shape[-1],requires_grad=True)
    count=y.sum(axis=1).astype(int);weights=None
    if config.get('balanced'):
        sizes={v:int((count==v).sum()) for v in (1,2,3)}
        ww=np.array([1/max(sizes.get(v,len(y)),1) for v in count],np.float32);ww/=ww.mean();weights=torch.from_numpy(ww)
    epochs=forced_epochs or config['epochs'];lr=.03
    curves=[];best=None
    if config.get('lbfgs'):
        opt=torch.optim.LBFGS([w],lr=1.,max_iter=epochs,tolerance_grad=1e-7,line_search_fn='strong_wolfe')
        def closure():
            opt.zero_grad();loss=data_loss(xt@w,yt,config,weights,vt)+.5*config['l2']*w.square().sum()
            loss.backward();return loss
        opt.step(closure)
        curves.append({'epoch':epochs,'objective':float(closure().detach()),'gradient':float(w.grad.norm())})
    else:
        opt=torch.optim.Adam([w],lr=lr)
        for epoch in range(1,epochs+1):
            opt.zero_grad();loss=data_loss(xt@w,yt,config,weights,vt)+.5*config['l2']*w.square().sum()
            loss.backward();opt.step()
            if epoch==1 or epoch%60==0:curves.append({'epoch':epoch,'objective':float(loss.detach()),'gradient':float(w.grad.norm())})
            if eval_data is not None and (epoch%60==0 or epoch==epochs):
                ex,ey,ev=eval_data
                with torch.no_grad():
                    es=torch.from_numpy(ex)@w
                    objective=float(data_loss(es,torch.from_numpy(ey),config,valid=torch.from_numpy(ev)))
                    score=es.numpy().copy();score[~ev]=-1e9
                    correct=int(ey[np.arange(len(ey)),score.argmax(axis=1)].sum())
                rank=(correct,-objective)
                if best is None or rank>best[0]:best=(rank,epoch,w.detach().numpy().copy())
    if best is not None:return best[2],{'epochs':best[1],'curves':curves,'inner_selected':True}
    return w.detach().numpy().copy(),{'epochs':epochs,'curves':curves}

def fit_tree(x,y,config):
    flat=x.reshape(-1,x.shape[-1]);truth=y.reshape(-1);n,d=flat.shape
    cuts=np.quantile(flat,np.arange(1,16)/16,axis=0).T.astype(np.float32)
    bins=np.stack([np.searchsorted(cuts[f],flat[:,f],side='left') for f in range(d)],axis=1).astype(np.int16)
    init=float(np.log(np.clip(truth.mean(),1e-4,1-1e-4)/(1-np.clip(truth.mean(),1e-4,1-1e-4)))) if config['objective']=='bce' else 0.
    score=np.full((len(y),4),init);trees=[];curves=[];rng=np.random.default_rng(2026)
    for iteration in range(config['epochs']):
        if config['objective']=='bce':
            p=1/(1+np.exp(-np.clip(score,-20,20)));g=p-y;h=np.maximum(p*(1-p),1e-4)
        else:
            # LambdaMART-style pairwise lambdas weighted by changes in NDCG.
            g=np.zeros_like(score);h=np.zeros_like(score)
            rank=np.argsort(np.argsort(-score,axis=1),axis=1)
            discount=1/np.log2(rank+2)
            ideal=np.array([sum(1/math.log2(k+2) for k in range(int(v))) for v in y.sum(axis=1)])
            for i in range(4):
                for j in range(4):
                    mask=(y[:,i]>y[:,j]);delta=np.abs(discount[:,i]-discount[:,j])/np.maximum(ideal,1e-6)
                    p=1/(1+np.exp(np.clip(score[:,i]-score[:,j],-20,20)))
                    lam=mask*delta*p;curv=mask*delta*p*(1-p)
                    g[:,i]-=lam;g[:,j]+=lam;h[:,i]+=curv;h[:,j]+=curv
            h=np.maximum(h,1e-4)
        gf=g.ravel();hf=h.ravel();farr=np.full(15,-1,np.int32);tarr=np.zeros(15,np.float32)
        left=np.zeros(15,np.int32);right=np.zeros(15,np.int32);values=np.zeros(15,np.float32)
        feat=rng.choice(d,max(8,int(.75*d)),replace=False);nodecount=[0]
        def build(indices,depth):
            node=nodecount[0];nodecount[0]+=1
            G=gf[indices].sum();H=hf[indices].sum();values[node]=np.clip(-.08*G/(H+10),-.4,.4)
            if depth>=config['depth'] or len(indices)<80:return node
            best=None;parent=G*G/(H+10)
            for f in feat:
                gb=np.bincount(bins[indices,f],weights=gf[indices],minlength=16)
                hb=np.bincount(bins[indices,f],weights=hf[indices],minlength=16)
                nb=np.bincount(bins[indices,f],minlength=16)
                gl=np.cumsum(gb)[:-1];hl=np.cumsum(hb)[:-1];nl=np.cumsum(nb)[:-1]
                gain=gl*gl/(hl+10)+(G-gl)**2/(H-hl+10)-parent
                gain[(nl<30)|(len(indices)-nl<30)|(hl<1e-4)|(H-hl<1e-4)]=-np.inf
                k=int(gain.argmax())
                if best is None or gain[k]>best[0]:best=(float(gain[k]),int(f),k)
            if best is None or best[0]<=1e-6:return node
            _,f,k=best;sel=bins[indices,f]<=k;farr[node]=f;tarr[node]=cuts[f,k]
            left[node]=build(indices[sel],depth+1);right[node]=build(indices[~sel],depth+1)
            return node
        build(np.arange(n),0);ix=np.zeros(n,np.int64)
        for _ in range(4):
            ff=farr[ix];active=ff>=0;rr=np.flatnonzero(active)
            if not len(rr):break
            nodes=ix[rr];ix[rr]=np.where(flat[rr,ff[rr]]<=tarr[nodes],left[nodes],right[nodes])
        score+=values[ix].reshape(-1,4);trees.append((farr,tarr,left,right,values))
        if (iteration+1)%25==0:curves.append({'epoch':iteration+1,'candidate_bce':float(np.mean(np.logaddexp(0,score)-y*score))})
    asset={'tree_bias':np.asarray(init)}
    for k,name in enumerate(('tree_f','tree_t','tree_l','tree_r','tree_v')):asset[name]=np.stack([v[k] for v in trees])
    return asset,{'epochs':config['epochs'],'curves':curves}

class Correction(nn.Module):
    def __init__(self,d,config,base):
        super().__init__();self.config=config
        self.linear=nn.Parameter(torch.from_numpy(base.copy()),requires_grad=False)
        arch=config['arch'];width=config.get('width',32)
        if arch=='fm':
            self.v=nn.Parameter(torch.randn(d,4)*.001)
        elif arch in ('residual','supcon'):
            self.hidden=nn.Linear(d,width);self.output=nn.Linear(width,1)
            nn.init.zeros_(self.output.weight);nn.init.zeros_(self.output.bias)
        elif arch=='cnn':
            self.embed=nn.Embedding(128,8,padding_idx=0)
            self.convs=nn.ModuleList([nn.Conv1d(8,12,k) for k in (3,5)])
            self.output=nn.Linear(24,1);nn.init.zeros_(self.output.weight);nn.init.zeros_(self.output.bias)
        self.drop=nn.Dropout(config.get('dropout',0.))
    def forward(self,x,tokens=None):
        score=x@self.linear;arch=self.config['arch'];h=None
        if arch=='fm':score=score+.5*((x@self.v).square()-x.square()@self.v.square()).sum(dim=-1)
        elif arch in ('residual','supcon'):
            h=self.hidden(x);h=torch.tanh(h) if arch=='supcon' else F.relu(h)
            score=score+self.output(self.drop(h)).squeeze(-1)
        else:
            e=self.embed(tokens.reshape(-1,tokens.shape[-1])).transpose(1,2)
            h=torch.cat([F.relu(conv(e)).amax(dim=-1) for conv in self.convs],dim=-1)
            score=score+self.output(self.drop(h)).reshape(-1,4)
        return score,h
    def export(self):
        a={'linear_w':self.linear.detach().numpy().copy(),'linear_b':np.asarray(0.,np.float32)}
        arch=self.config['arch']
        if arch=='fm':a['fm_v']=self.v.detach().numpy().copy()
        elif arch in ('residual','supcon'):
            for k,v in [('hidden_w',self.hidden.weight.T),('hidden_b',self.hidden.bias),
                        ('out_w',self.output.weight.flatten()),('out_b',self.output.bias.squeeze())]:a[k]=v.detach().numpy().copy()
        else:
            a['char_embedding']=self.embed.weight.detach().numpy().copy()
            for k,conv in zip((3,5),self.convs):
                a['conv'+str(k)+'_w']=conv.weight.detach().numpy().transpose(2,1,0).reshape(k*8,12).copy()
                a['conv'+str(k)+'_b']=conv.bias.detach().numpy().copy()
            a['cnn_out_w']=self.output.weight.detach().numpy().ravel().copy();a['cnn_out_b']=self.output.bias.detach().numpy().squeeze().copy()
        return a

def local_contrast(h,y):
    z=F.normalize(h,dim=-1);sim=z@z.transpose(1,2)/.2
    eye=torch.eye(4,dtype=torch.bool)[None]
    positives=y.bool()[:,:,None]&y.bool()[:,None,:]&~eye
    anchors=positives.any(dim=-1)&(~y.bool()).any(dim=1)[:,None]
    if not anchors.any():return sim.sum()*0
    logp=sim.masked_fill(eye,-1e9).log_softmax(dim=-1)
    losses=-(logp*positives).sum(dim=-1)/positives.sum(dim=-1).clamp_min(1)
    return losses[anchors].mean()

def correction_fit(x,y,config,valid,tokens,base,eval_data=None,forced_epochs=None):
    torch.manual_seed(2026);model=Correction(x.shape[-1],config,base)
    params=[p for p in model.parameters() if p.requires_grad]
    lr=.003 if config['arch']!='fm' else .001
    opt=(torch.optim.Adam(params,lr=lr) if config.get('adam_l2') else torch.optim.AdamW(params,lr=lr,weight_decay=config['l2']))
    xt=torch.from_numpy(x);yt=torch.from_numpy(y);tt=torch.from_numpy(tokens) if tokens is not None else None
    vt=torch.from_numpy(valid);epochs=forced_epochs or config['epochs'];curves=[];rng=np.random.default_rng(2026)
    avg=None;averaged=0;best=None
    for epoch in range(1,epochs+1):
        model.train();order=rng.permutation(len(y));batch=config.get('batch',256 if config['arch']=='cnn' else 512)
        losses=[];contrast_values=[]
        for start in range(0,len(y),batch):
            ix=order[start:start+batch]
            def closure():
                opt.zero_grad();s,h=model(xt[ix],tt[ix] if tt is not None else None)
                loss=data_loss(s,yt[ix],config,valid=vt[ix]);con=s.sum()*0
                if config['arch']=='supcon':con=local_contrast(h,yt[ix]);loss=loss+.05*con
                if config.get('adam_l2'):loss=loss+.5*config['l2']*sum(p.square().sum() for p in params)
                loss.backward();return loss,con
            loss,con=closure()
            if config.get('sam'):
                norm=torch.sqrt(sum(p.grad.square().sum() for p in params)).clamp_min(1e-12)
                perturb=[p.grad.detach().clone()*(.03/norm) for p in params]
                with torch.no_grad():
                    for p,e in zip(params,perturb):p.add_(e)
                closure()
                with torch.no_grad():
                    for p,e in zip(params,perturb):p.sub_(e)
            torch.nn.utils.clip_grad_norm_(params,5.);opt.step();losses.append(float(loss.detach()));contrast_values.append(float(con.detach()))
        if config.get('average') and epoch>=max(2,config['epochs']//2):
            state={k:v.detach().clone() for k,v in model.state_dict().items()}
            if avg is None:avg=state
            else:
                factor=.9 if config['average']=='ema' else averaged/(averaged+1)
                for k in avg:avg[k].mul_(factor).add_(state[k],alpha=1-factor)
            averaged+=1
        if epoch==1 or epoch%4==0 or epoch==epochs:
            curves.append({'epoch':epoch,'train_loss':float(np.mean(losses)),'contrast_loss':float(np.mean(contrast_values))})
            if eval_data is not None:
                ex,ey,ev,et=eval_data;model.eval()
                current=copy.deepcopy(model.state_dict())
                if avg is not None:model.load_state_dict(avg)
                with torch.no_grad():
                    es,_=model(torch.from_numpy(ex),torch.from_numpy(et) if et is not None else None)
                    obj=float(data_loss(es,torch.from_numpy(ey),config,valid=torch.from_numpy(ev)))
                    score=es.numpy().copy();score[~ev]=-1e9
                    correct=int(ey[np.arange(len(ey)),score.argmax(axis=1)].sum())
                if best is None or (correct,-obj)>best[0]:best=((correct,-obj),epoch,copy.deepcopy(model.state_dict()))
                model.load_state_dict(current)
    if best is not None:model.load_state_dict(best[2]);chosen=best[1]
    else:
        if avg is not None:model.load_state_dict(avg)
        chosen=epochs
    model.eval()
    with torch.no_grad():expected=model(xt[:7],tt[:7] if tt is not None else None)[0].numpy()
    return model.export(),{'epochs':chosen,'curves':curves,'train_probe':expected.tolist()}

def fit_model(raw,y,valid,tokens,prep,config,eval_data=None,forced_epochs=None,base_cache=None):
    start=time.perf_counter();a={k:v.copy() for k,v in prep.items()}
    if config['design']=='stable':
        xx=np.clip((raw-a['mean'])/a['scale'],-20,20)[:,:,1024:]
        xx=xx-xx.mean(axis=1,keepdims=True);yy=y-y.mean(axis=1,keepdims=True)
        order=np.random.default_rng(2026).permutation(len(y));parts=np.array_split(order,2);corr=[]
        for ix in parts:
            cov=(xx[ix]*yy[ix,:,None]).mean(axis=(0,1));den=np.maximum(np.sqrt((xx[ix]**2).mean(axis=(0,1))*(yy[ix]**2).mean()),1e-6);corr.append(cov/den)
        stable=(corr[0]*corr[1]>0)&(np.minimum(abs(corr[0]),abs(corr[1]))>.015)
        a['stable_mask']=np.concatenate([np.ones(1024,bool),stable])
    x=design(raw,a,config['design']).astype(np.float32)
    transformed=None
    if eval_data is not None:
        er,ey,ev,et=eval_data;ex=design(er,a,config['design']).astype(np.float32);transformed=(ex,ey,ev,et)
    if config['arch']=='tree':learned,info=fit_tree(x,y,config)
    elif config['arch']=='linear':
        learned_w,info=linear_fit(x,y,config,valid,(transformed[:3] if transformed is not None and config.get('earlystop') else None),forced_epochs)
        learned={'linear_w':learned_w,'linear_b':np.asarray(0.,np.float32)}
    else:
        base=base_cache
        if base is None:base,_=linear_fit(x,y,{'epochs':120,'l2':.01},valid)
        learned,info=correction_fit(x,y,config,valid,tokens,base,transformed,forced_epochs)
    a.update(learned)
    actual=model_scores(raw[:7],[],config,a,tokens=tokens[:7] if tokens is not None else None)
    if 'train_probe' in info:assert np.allclose(actual,info.pop('train_probe'),atol=3e-5,rtol=1e-5),(config,np.max(abs(actual-np.asarray(info.get('train_probe')))))
    scores=model_scores(raw,[],config,a,tokens=tokens)
    score_scale=max(float((scores-scores.mean(axis=1,keepdims=True)).std()),1e-6)
    info.update(seconds=time.perf_counter()-start,score_scale=score_scale)
    # Keep only transformations actually needed for inference.
    for k in ('pca','knots','rff_w','rff_b'):
        if not ((k=='pca' and config['design'] in ('compact','rff')) or (k=='knots' and config['design']=='gam') or (k.startswith('rff') and config['design']=='rff')):a.pop(k,None)
    return a,info
