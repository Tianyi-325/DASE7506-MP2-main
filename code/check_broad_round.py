"""Behavior and export checks for the broad round (validation inputs only)."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,json,copy
from pathlib import Path
import numpy as np
from common import load_inputs,parse_answer
from broad_models import raw_inputs,char_tokens,predict,bundle_scores
def main():
    p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--output',type=Path,default=Path('runs/broad_round'));args=p.parse_args()
    b,a=load_inputs('train' if args.smoke else 'validation')
    if args.smoke:
        import torch
        from train_vector import labels
        from broad_training import SPECS,preprocess,fit_model
        torch.set_num_threads(4);torch.set_num_interop_threads(1)
        b=b[:80];a={'embeddings':a['embeddings'][:80]};y=labels('train',load_inputs('train')[0])[:80]
        raw=raw_inputs(b,a);t=char_tokens(b);valid=raw[:,:,1039]>0
        prep=preprocess(raw);base=None
        for name,spec in SPECS.items():
            c={**spec,'epochs':2};asset,info=fit_model(raw,y,valid,t,prep,c,base_cache=base)
            if name=='baseline':base=asset['linear_w']
            assert all(np.isfinite(v).all() for v in asset.values())
            print(json.dumps({'smoke_pass':name,'seconds':info['seconds']}),flush=True)
        return
    f=json.loads((args.output/'freeze.json').read_text());checked=[]
    assert 'torch' not in __import__('sys').modules
    for name in f['variants']:
        bundle=args.output/'variants'/name/'model_bundle'
        for n in (0,1,7):
            sb=b[:n];sa={'embeddings':a['embeddings'][:n]}
            pred=predict(sb,sa,bundle);assert len(pred)==n and all(type(v) is int and 0<=v<4 for v in pred)
        sb=copy.deepcopy(b[:7]);sa={'embeddings':a['embeddings'][:7].copy()}
        original=predict(sb,sa,bundle)
        for row in sb:row['id']='arbitrary-id-'+row['id']
        assert predict(sb,sa,bundle)==original
        perm=np.array([2,0,3,1]);permuted=copy.deepcopy(sb)
        for row in permuted:
            row['candidates']=[copy.deepcopy(row['candidates'][int(k)]) for k in perm]
            for j,c in enumerate(row['candidates']):c['index']=j
        pp=predict(permuted,{'embeddings':sa['embeddings'][:,perm]},bundle)
        for i,(oi,pi) in enumerate(zip(original,pp)):
            assert parse_answer(sb[i]['candidates'][oi]['text'])==parse_answer(permuted[i]['candidates'][pi]['text']),(name,i)
        fake=[{'id':'new','question':'new question','candidates':[{'index':j,'text':'unknown'} for j in range(4)]}]
        assert predict(fake,{'embeddings':np.zeros((1,4,1024),np.float32)},bundle)==[0]
        checked.append(name)
    (args.output/'checks.json').write_text(json.dumps({'passed':True,'variants':checked,
      'checks':['empty, one and seven question banks','unknown IDs','candidate permutation by numeric answer',
      'all unparseable fallback','NumPy-only inference; no torch import']},indent=2)+'\n')
    print(json.dumps({'checks_passed':len(checked)}))
if __name__=='__main__':main()
