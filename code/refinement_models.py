"""NumPy-only refinement inference: answer groups, OOF fusion and lexical residuals."""
import json
from pathlib import Path
import re
import zlib
import numpy as np
from common import parse_answer
from reasoning_features import extract_features
from vector_vote_fusion import answer_information,select_from_scores

DIMS=1054


def raw_features(bank,arrays):
    emb=np.asarray(arrays['embeddings'],dtype=np.float32)
    if emb.shape!=(len(bank),4,1024):raise ValueError('Expected [N,4,1024] embeddings')
    return np.concatenate([emb,extract_features(bank,'textcalc')],axis=-1)


def lexical_counts(text,dims):
    tokens=re.findall(r'[a-z]+|\d+(?:\.\d+)?',text.lower())
    tokens=['<n>' if t[0].isdigit() else t for t in tokens]
    terms=['u:'+t for t in tokens]+['b:'+a+'_'+b for a,b in zip(tokens,tokens[1:])]
    indices=np.fromiter((zlib.crc32(t.encode('utf-8'))%dims for t in terms),dtype=np.int64)
    if not len(indices):return np.zeros(0,dtype=np.int64),np.zeros(0,dtype=np.float32)
    idx,count=np.unique(indices,return_counts=True)
    return idx,(1+np.log(count)).astype(np.float32)


def lexical_score(bank,weight,idf):
    result=[]
    for row in bank:
        for c in row['candidates']:
            idx,count=lexical_counts(c['text'],len(weight));value=count*idf[idx]
            norm=max(float(np.linalg.norm(value)),1e-12)
            result.append(float(value@weight[idx]/norm))
    return np.asarray(result).reshape(len(bank),4)


def stack_features(bank,x,base):
    # Centering removes irrelevant common within-question logit offsets.
    centered=base-base.mean(axis=1,keepdims=True)
    _,counts,votes=answer_information(bank)
    normalized=centered
    groups=[];masks=[];maps=[]
    for i,row in enumerate(bank):
        answers=[parse_answer(c['text']) for c in row['candidates']]
        unique=list(counts[i])
        if not unique:unique=[None]
        rows=[];mapping=np.zeros(4,dtype=np.int64)
        for g,a in enumerate(unique):
            ix=[j for j,b in enumerate(answers) if b==a] if a is not None else list(range(4))
            for j in ix:mapping[j]=g
            b=normalized[i,ix]
            support=len(ix)/4
            # Group summaries distinguish duplicated support from independent quality.
            feature=np.concatenate([b.max(axis=0),b.mean(axis=0),b.std(axis=0),b.min(axis=0),
                [support,len(unique)/4,len(set(row['candidates'][j]['text'] for j in ix))/len(ix)],
                x[i,ix,1024:1046].mean(axis=0),x[i,ix,1046:].mean(axis=0),x[i,ix,1046:].max(axis=0)])
            rows.append(feature)
        dim=len(rows[0]);pad=np.zeros((4,dim));pad[:len(rows)]=rows
        groups.append(pad);masks.append(np.arange(4)<len(rows));maps.append(mapping)
    dim=53 # 12 score summaries +3 group statistics +22 text +8 calc mean +8 calc max
    if len(bank):dim=groups[0].shape[-1]
    return np.asarray(groups,dtype=np.float64).reshape(len(bank),4,dim),np.asarray(masks,dtype=bool).reshape(-1,4),np.asarray(maps,dtype=np.int64).reshape(-1,4)


def score_assets(bank,x,config,asset):
    kind=config['kind']
    if kind in ('linear','lexical'):
        scores=x@asset['weight']+float(asset['bias'].item())
        if kind=='lexical':scores+=lexical_score(bank,asset['lexical_weight'],asset['idf'])
        return scores
    base=x@asset['base_weight'].T+asset['base_bias']
    base=(base-base.mean(axis=1,keepdims=True))/asset['base_scale']
    if kind=='blend':
        return base@asset['blend_weight']
    _,_,votes=answer_information(bank)
    if kind=='candidate_stack':
        features=np.concatenate([base,votes[:,:,None] if votes.ndim==2 else votes],axis=-1)
        return ((features-asset['meta_mean'])/asset['meta_scale'])@asset['meta_weight']
    group,mask,mapping=stack_features(bank,x,base)
    group=(group-asset['meta_mean'])/asset['meta_scale']
    if kind=='group_mlp':group=np.maximum(group@asset['meta_hidden_weight']+asset['meta_hidden_bias'],0)
    scores=group@asset['meta_weight']
    return np.take_along_axis(scores,mapping,axis=1)


def predict(bank,arrays,checkpoint):
    if checkpoint is None:raise ValueError('Supply a model bundle')
    bundle=Path(checkpoint);config=json.loads((bundle/'config.json').read_text(encoding='utf-8'))
    x=raw_features(bank,arrays)
    with np.load(bundle/'model.npz',allow_pickle=False) as asset:scores=score_assets(bank,x,config,asset)
    return select_from_scores(bank,scores,'weighted',config.get('alpha',0.))
