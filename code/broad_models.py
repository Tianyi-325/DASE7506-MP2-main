"""Small offline model families. Inference imports NumPy only; no reference IO."""
import json,re,math
from pathlib import Path
from fractions import Fraction
import numpy as np
from common import parse_answer
from reasoning_features import extract_features,numeric_tokens,safe_arithmetic
from vector_vote_fusion import answer_information,select_from_scores

EXTRA_NAMES=['support','support_gap','distinct_answers','answer_abs_log','answer_fraction',
 'answer_question_ratio','answer_question_close','q_remaining','q_percent','q_rate','q_difference',
 'q_count','remaining_answer_negative','count_answer_fraction','percent_answer_over100',
 'strict_checked','strict_wrong_fraction','strict_unknown','strict_answer_match','unit_overlap']
STYLE=[0,1,2,3,4,8,9,10,11,12,13,14,21]

def strict_equations(text,answer):
    checked=wrong=unknown=matched=0
    for line in text.replace('×','*').replace('÷','/').replace('−','-').splitlines():
        line=line.strip().replace(',','')
        if '=' not in line:continue
        m=re.fullmatch(r'\s*([-+0-9.()*/ \t]+)\s*=\s*([-+0-9.()*/ \t]+)\s*[.]?\s*',line)
        if not m:unknown+=1;continue
        try:
            l,r=[safe_arithmetic(v) for v in m.groups()]
            checked+=1;wrong+=int(abs(l-r)>1e-3*max(1,abs(l),abs(r)))
            if answer is not None:
                a=float(Fraction(answer));matched|=int(abs(r-a)<=1e-3*max(1,abs(r),abs(a)))
        except (ValueError,SyntaxError,ZeroDivisionError,OverflowError):unknown+=1
    return [math.log1p(checked),wrong/max(1,checked),float(checked==0),float(matched)]

def engineered(bank):
    if not bank:return np.empty((0,4,50),np.float32)
    text=extract_features(bank,'textcalc');answers,counts,votes=answer_information(bank);extras=[]
    for i,row in enumerate(bank):
        q=row['question'].lower();qnums=[abs(float(Fraction(v))) for v in numeric_tokens(q)]
        maximum=max(qnums,default=1.)
        flags=[float(bool(re.search(p,q))) for p in
          (r'left|remain|rest|after',r'percent|%',r'per |each|every|rate',r'more|less|difference',r'how many|number of')]
        qw=set(re.findall(r'[a-z]+',q));units=qw&{'hours','minutes','seconds','days','weeks','months','years','dollars','cents','miles','feet','meters','kilometers','pounds'}
        extra=[]
        for j,c in enumerate(row['candidates']):
            a=answers[i][j];av=float(Fraction(a)) if a is not None else 0.;av=np.clip(av,-1e15,1e15)
            f=float(a is not None and Fraction(a).denominator!=1)
            extra.append([votes[i,j]/4,(votes[i,j]-votes[i].max())/4,len(counts[i])/4,
              math.log1p(abs(av)),f,math.log1p(abs(av)/max(maximum,1e-6)),
              float(any(abs(abs(av)-v)<1e-6 for v in qnums)),*flags,
              flags[0]*float(av<0),flags[4]*f,flags[1]*float(abs(av)>100),
              *strict_equations(c['text'],a),
              len(units&set(re.findall(r'[a-z]+',c['text'].lower())))/max(1,len(units))])
        extras.append(extra)
    return np.concatenate([text,np.asarray(extras,np.float32)],axis=-1).astype(np.float32)

def raw_inputs(bank,arrays):
    emb=np.asarray(arrays['embeddings'],np.float32)
    if emb.shape!=(len(bank),4,1024):raise ValueError('Expected [N,4,1024]')
    return np.concatenate([emb,engineered(bank)],axis=-1)

def char_tokens(bank,length=256):
    out=np.zeros((len(bank),4,length),np.int64)
    for i,row in enumerate(bank):
        q=row['question'].lower()[-64:]
        for j,c in enumerate(row['candidates']):
            t=c['text'].lower();s=q+'\n'+t[:95]+'\n'+t[-95:]
            vals=[ord(ch) if 0<ord(ch)<128 else 1 for ch in s[:length]]
            out[i,j,:len(vals)]=vals
    return out

def design(raw,asset,kind):
    x=np.clip((raw-asset['mean'])/asset['scale'],-20,20)
    if kind=='base':return x[:,:,:1046]
    if kind=='stable':return x[:,:,asset['stable_mask']]
    if kind=='quality':return np.concatenate([x[:,:,:1046],x[:,:,1054:]],axis=-1)
    if kind=='nostyle':
        keep=np.ones(x.shape[-1],bool);keep[1024+np.asarray(STYLE)]=False
        return x[:,:,keep]
    if kind in ('compact','rff'):
        small=x[:,:,:1024]@asset['pca']
        z=np.concatenate([small,x[:,:,1024:]],axis=-1)
        if kind=='compact':return z
        rf=np.cos(z@asset['rff_w']+asset['rff_b'])*math.sqrt(2/asset['rff_w'].shape[1])
        return np.concatenate([x[:,:,:1046],rf],axis=-1)
    if kind=='gam':
        scalar=x[:,:,1024:]
        hinges=np.maximum(scalar[:,:,:,None]-asset['knots'],0).reshape(*x.shape[:2],-1)
        e=x[:,:,1024:];inter=np.stack([e[:,:,30]*e[:,:,17],e[:,:,30]*e[:,:,7],
          e[:,:,37]*e[:,:,18],e[:,:,41]*e[:,:,34],e[:,:,38]*e[:,:,33],
          e[:,:,30]*e[:,:,46]],axis=-1)
        return np.concatenate([x[:,:,:1046],hinges,inter],axis=-1)
    return x

def tree_scores(x,asset):
    flat=x.reshape(-1,x.shape[-1]);out=np.full(len(flat),float(asset['tree_bias']),np.float64)
    for f,t,l,r,v in zip(asset['tree_f'],asset['tree_t'],asset['tree_l'],asset['tree_r'],asset['tree_v']):
        ix=np.zeros(len(flat),np.int64)
        for _ in range(4):
            feature=f[ix];active=feature>=0
            if not active.any():break
            rows=np.flatnonzero(active);nodes=ix[rows]
            ix[rows]=np.where(flat[rows,feature[rows]]<=t[nodes],l[nodes],r[nodes])
        out+=v[ix]
    return out.reshape(x.shape[:2])

def cnn_numpy(tokens,asset):
    flat=tokens.reshape(-1,tokens.shape[-1]);result=[]
    from numpy.lib.stride_tricks import sliding_window_view
    for start in range(0,len(flat),64):
        e=asset['char_embedding'][flat[start:start+64]];parts=[]
        for k in (3,5):
            windows=sliding_window_view(e,k,axis=1).transpose(0,1,3,2)
            h=windows.reshape(-1,k*e.shape[-1])@asset['conv'+str(k)+'_w']+asset['conv'+str(k)+'_b']
            parts.append(np.maximum(h.reshape(len(e),-1,h.shape[-1]),0).max(axis=1))
        result.append(np.concatenate(parts,axis=-1)@asset['cnn_out_w']+asset['cnn_out_b'])
    return np.concatenate(result).reshape(tokens.shape[:2]) if result else np.empty(tokens.shape[:2])

def model_scores(raw,bank,config,asset,tokens=None):
    if len(raw)==0:return np.empty((0,4),np.float64)
    x=design(raw,asset,config['design']).astype(np.float32)
    arch=config['arch']
    if arch=='tree':s=tree_scores(x,asset)
    else:
        s=x@asset['linear_w']+asset.get('linear_b',0.)
        if arch=='fm':
            v=asset['fm_v'];s+=.5*((x@v)**2-(x*x)@(v*v)).sum(axis=-1)
        elif arch in ('residual','supcon'):
            h=x@asset['hidden_w']+asset['hidden_b']
            h=np.tanh(h) if arch=='supcon' else np.maximum(h,0)
            s+=h@asset['out_w']+asset['out_b']
        elif arch=='cnn':s+=cnn_numpy(char_tokens(bank) if tokens is None else tokens,asset)
    return np.asarray(s,np.float64)

def bundle_scores(bank,arrays,bundle):
    bundle=Path(bundle);config=json.loads((bundle/'config.json').read_text(encoding='utf8'))
    if config.get('ensemble'):
        scores=0.
        for i,member in enumerate(config['members']):
            with np.load(bundle/f'member{i}.npz',allow_pickle=False) as a:
                raw=raw_inputs(bank,arrays) if i==0 else raw
                scores=scores+member['weight']*model_scores(raw,bank,member['config'],dict(a))/member['score_scale']
        return scores,config
    with np.load(bundle/'model.npz',allow_pickle=False) as a:
        scores=model_scores(raw_inputs(bank,arrays),bank,config,dict(a))
    return scores,config

def predict(bank,arrays,checkpoint):
    if checkpoint is None:raise ValueError('Supply frozen model bundle')
    scores,config=bundle_scores(bank,arrays,checkpoint)
    return select_from_scores(bank,scores,'weighted',config.get('alpha',0.))
