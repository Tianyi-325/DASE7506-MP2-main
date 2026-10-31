"""Direct answer-group / joint-consensus models; NumPy-only inference."""
import json
from pathlib import Path
import re
import numpy as np
from common import parse_answer
from reasoning_features import extract_features
from vector_vote_fusion import answer_information,select_from_scores


def membership(bank):
    member=np.zeros((len(bank),4,4),bool);mapping=np.zeros((len(bank),4),np.int64)
    for i,row in enumerate(bank):
        a=[parse_answer(c['text']) for c in row['candidates']]
        unique=list(dict.fromkeys(v for v in a if v is not None))
        if not unique:
            member[i,0]=True
        else:
            for g,value in enumerate(unique):
                ix=[j for j,v in enumerate(a) if v==value];member[i,g,ix]=True;mapping[i,ix]=g
    return member,member.any(axis=2),mapping


def inputs(bank,arrays,kind):
    emb=np.asarray(arrays['embeddings'],np.float32)
    if emb.shape!=(len(bank),4,1024):raise ValueError('Expected [N,4,1024]')
    text=extract_features(bank,'text');parts=[emb,text]
    if kind!='base':
        _,counts,votes=answer_information(bank);support=votes[:,:,None]/4
        maxsupport=support.max(axis=1,keepdims=True)
        numeric=text[:,:,[6,7,16,17,18,19,20]]
        distinct=np.asarray([len(c)/4 for c in counts],np.float32).reshape(-1,1,1)
        parts += [support,np.log1p(votes)[:,:,None],support-maxsupport,numeric*support,
                  numeric*(maxsupport-support),numeric*distinct]
        if kind=='relations':
            conditions=[]
            for row in bank:
                q=row['question'].lower()
                conditions.append([bool(re.search(p,q)) for p in
                    (r'percent|%',r'minute|hour|second',r'remain|left|rest',r'more|less|difference',r'per |each|every',r'how many')])
            condition=np.asarray(conditions,np.float32).reshape(len(bank),1,6)
            parts.append((numeric[:,:,:,None]*condition[:,:,None,:]).reshape(len(bank),4,42))
    return np.concatenate(parts,axis=2).astype(np.float32,copy=False)


def pool_numpy(scores,member,mask,mode):
    if mode=='candidate':return scores
    count=member.sum(axis=2).clip(1)
    if mode=='mean':result=(scores[:,None,:]*member).sum(axis=2)/count
    else:
        masked=np.where(member,scores[:,None,:],-1e30);maximum=masked.max(axis=2)
        if mode=='max':result=maximum
        elif mode=='logmeanexp':
            result=maximum+np.log(np.exp(masked-maximum[:,:,None]).sum(axis=2))-np.log(count)
        else:raise ValueError('Unknown pooling')
    return np.where(mask,result,-1e30)


def member_scores(bank,x,member,mask,mapping,mode,weight,bias):
    raw=x@weight+float(np.asarray(bias).item())
    if mode=='candidate':return raw
    grouped=pool_numpy(raw,member,mask,mode)
    return np.take_along_axis(grouped,mapping,axis=1)


def scores_with_assets(bank,arrays,config,asset):
    member,mask,mapping=membership(bank);cache={};result=np.zeros((len(bank),4),np.float64)
    for i,model in enumerate(config['members']):
        kind=model['input']
        if kind not in cache:cache[kind]=inputs(bank,arrays,kind)
        scores=member_scores(bank,cache[kind],member,mask,mapping,model['pool'],asset[f'm{i}_weight'],asset[f'm{i}_bias'])
        centered=scores-scores.mean(axis=1,keepdims=True)
        result+=config['weights'][i]*centered/asset['score_scales'][i]
    return result


def predict(bank,arrays,checkpoint):
    if checkpoint is None:raise ValueError('Supply a bundle')
    bundle=Path(checkpoint);config=json.loads((bundle/'config.json').read_text(encoding='utf-8'))
    with np.load(bundle/'model.npz',allow_pickle=False) as asset:scores=scores_with_assets(bank,arrays,config,asset)
    return select_from_scores(bank,scores,'weighted',config['alpha'])
