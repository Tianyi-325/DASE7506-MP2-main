"""Matched linear/additive selection; NumPy inference, no reference access."""
import json
from pathlib import Path
import numpy as np
from broad_models import raw_inputs,STYLE
from vector_vote_fusion import select_from_scores

NARROW_STYLE=[0,1,2,8,9,12,13,14,21]
INTERACTIONS=[(30,17),(30,7),(37,18),(41,34),(38,33),(30,46)]

def standardized(raw,a):
    return np.clip((np.asarray(raw,np.float64)-a['mean'])/a['scale'],-20,20)

def derived(x,a,c):
    parts=[]
    if c['basis'].startswith('orth_'):
        v=x[:,:,1024+a['orth_indices']]
        h=np.maximum(v-a['orth_knots'],0)-v*a['orth_slope']-a['orth_intercept']
        parts.append(h)
    if c['basis'] in ('hinges','both'):
        ix=a['scalar_keep']
        h=np.maximum(x[:,:,1024+ix,None]-a['knots'],0)
        parts.append(h.reshape(*x.shape[:2],-1))
    if c['basis'] in ('interactions','both','orth_both'):
        e=x[:,:,1024:]
        parts.append(np.stack([e[:,:,i]*e[:,:,j] for i,j in INTERACTIONS],axis=-1))
    return np.concatenate(parts,axis=-1) if parts else np.empty((*x.shape[:2],0),np.float64)

def design(raw,a,c):
    x=standardized(raw,a);linear=x[:,:,a['keep']]
    if c['basis']=='linear':return np.ascontiguousarray(linear)
    nonlinear=derived(x,a,c)
    nonlinear=np.clip((nonlinear-a['derived_mean'])/a['derived_scale'],-20,20)
    return np.ascontiguousarray(np.concatenate([linear,nonlinear],axis=-1))

def preprocessing(raw,c):
    flat=np.asarray(raw,np.float64).reshape(-1,raw.shape[-1])
    a={'mean':flat.mean(axis=0),'scale':np.maximum(flat.std(axis=0),1e-6)}
    d=1046 if c['features']=='base' else 1074
    keep=np.zeros(raw.shape[-1],bool);keep[:d]=True
    removed=STYLE if c['style']=='broad' else NARROW_STYLE if c['style']=='narrow' else []
    keep[1024+np.asarray(removed,dtype=int)]=False;a['keep']=keep
    a['scalar_keep']=np.flatnonzero(keep[1024:]).astype(np.int64)
    if c['basis'] in ('hinges','both'):
        x=standardized(raw,a)
        a['knots']=np.quantile(x[:,:,1024+a['scalar_keep']].reshape(-1,len(a['scalar_keep'])),[.2,.4,.6,.8],axis=0).T
    if c['basis'].startswith('orth_'):
        sx=standardized(raw,a)[:,:,1024:].reshape(-1,50)
        indices=[];knots=[];slopes=[];intercepts=[]
        for j in a['scalar_keep']:
            v=sx[:,j];var=v.var()
            if var<1e-12:continue
            for knot in np.unique(np.quantile(v,[.2,.4,.6,.8])):
                h=np.maximum(v-knot,0);slope=((v-v.mean())*(h-h.mean())).mean()/var;intercept=h.mean()-slope*v.mean()
                residual=h-slope*v-intercept
                if residual.std()<1e-6:continue
                indices.append(j);knots.append(knot);slopes.append(slope);intercepts.append(intercept)
        a.update(orth_indices=np.asarray(indices,np.int64),orth_knots=np.asarray(knots),orth_slope=np.asarray(slopes),orth_intercept=np.asarray(intercepts))
    if c['basis']!='linear':
        dd=derived(standardized(raw,a),a,c).reshape(-1,derived(standardized(raw[:1],a),a,c).shape[-1])
        a['derived_mean']=dd.mean(axis=0);a['derived_scale']=np.maximum(dd.std(axis=0),1e-6)
    return a

def scores(raw,a,c):
    if len(raw)==0:return np.empty((0,4),np.float64)
    return design(raw,a,c)@a['weight']

def bundle_scores(bank,arrays,bundle):
    bundle=Path(bundle);config=json.loads((bundle/'config.json').read_text(encoding='utf8'))
    raw=raw_inputs(bank,arrays);out=np.zeros((len(bank),4),np.float64)
    for i,m in enumerate(config['members']):
        with np.load(bundle/f'member{i}.npz',allow_pickle=False) as z:
            out+=m['weight']*scores(raw,z,m['config'])/m['scale']
    return out,config

def predict(bank,arrays,checkpoint):
    if checkpoint is None:raise ValueError('Supply a frozen bundle')
    s,c=bundle_scores(bank,arrays,checkpoint)
    return select_from_scores(bank,s,'weighted',c['alpha'])
