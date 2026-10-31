"""Old strong scorers + learned mathematical evidence; NumPy-only inference."""
import json
from pathlib import Path
import numpy as np
from broad_models import raw_inputs,STYLE
from direct_group_models import inputs as joint_inputs,membership,pool_numpy
from math_evidence import extract_evidence
from vector_vote_fusion import answer_information,select_from_scores

def make_inputs(bank,arrays):
    blocks,diagnostics=extract_evidence(bank)
    member,mask,mapping=membership(bank);_,_,votes=answer_information(bank)
    return {'raw':raw_inputs(bank,arrays),'joint':joint_inputs(bank,arrays,'joint'),
      'member':member,'group_mask':mask,'mapping':mapping,'votes':votes,**blocks},diagnostics

def subset(data,index):return {k:v[index] for k,v in data.items()}
def block(data,name):
    if name in ('semantic','verify'):return data[name]
    parts=[data['semantic'],data['verify']]
    if name=='relative':parts.append(data['relative'])
    return np.concatenate(parts,axis=-1)

def base_design(data,asset,kind):
    raw=data['joint'] if kind=='joint' else data['raw']
    x=(raw-asset['b_mean'])/asset['b_scale']
    if kind!='joint':x=np.clip(x,-20,20)
    return np.ascontiguousarray(x[:,:,asset['b_keep']],dtype=np.float32)

def base_raw(data,asset,kind):
    if kind=='none':return np.zeros((len(data['raw']),4),np.float64)
    if kind=='joint':return data['joint'].astype(np.float64)@asset['b_weight']+asset['b_bias']
    return (base_design(data,asset,kind)@asset['b_weight']).astype(np.float64)

def pooled(data,s,kind):
    if kind not in ('joint','none'):return s
    group=pool_numpy(s,data['member'],data['group_mask'],'mean')
    return np.take_along_axis(group,data['mapping'],axis=1)

def group_margin(data,s):
    group=pool_numpy(s,data['member'],data['group_mask'],'max')
    order=np.sort(group,axis=1)
    margin=order[:,-1]-order[:,-2]
    # A single valid answer is uncompetitive and should keep the original choice.
    return np.where(data['group_mask'].sum(axis=1)>=2,margin,1e12)

def extra_design(data,asset,name):
    return np.clip((block(data,name)-asset['e_mean'])/asset['e_scale'],-8,8).astype(np.float32)

def member_scores(data,c,a):
    if len(data['raw'])==0:return np.empty((0,4),np.float64)
    s=base_raw(data,a,c['base'])
    if c['mode']!='control':
        correction=(extra_design(data,a,c['block'])@a['e_weight']).astype(np.float64)
        if c['mode']=='gated':
            old=pooled(data,s,c['base']);margin=group_margin(data,old)/float(a['base_score_scale'])
            available=(data['verify'][:,:,0]>0).any(axis=1)|(data['semantic'][:,:,2]>0).any(axis=1)|(data['semantic'][:,:,5]>0).any(axis=1)
            gate=(margin<=c['gate_tau'])&available
            cap=float(a['base_score_scale'])*c['cap_norm']
            correction=gate[:,None]*cap*np.tanh(correction/max(cap,1e-6))
        s=s+correction
    return pooled(data,s,c['base'])

def predict(bank,arrays,checkpoint):
    if checkpoint is None:raise ValueError('Supply frozen model bundle')
    bundle=Path(checkpoint);c=json.loads((bundle/'config.json').read_text(encoding='utf8'))
    data,_=make_inputs(bank,arrays);result=np.zeros((len(bank),4),np.float64)
    for i,m in enumerate(c['members']):
        with np.load(bundle/f'member{i}.npz',allow_pickle=False) as asset:
            s=member_scores(data,m['config'],asset)
            result+=m['weight']*(s-s.mean(axis=1,keepdims=True))/m['scale']
    return select_from_scores(bank,result,'weighted',c['alpha'])
