"""Numerical and input-contract checks for focused models."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,copy,json
from pathlib import Path
import numpy as np
from common import load_inputs,parse_answer
from focused_models import predict,bundle_scores
def main():
    p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--output',type=Path,default=Path('runs/focused_round'));a=p.parse_args()
    bank,arrays=load_inputs('train' if a.smoke else 'validation')
    if a.smoke:
        import torch
        from train_vector import labels
        from run_focused_round import SPECS,fit
        from broad_models import raw_inputs
        from vector_vote_fusion import answer_information
        torch.set_num_threads(4);torch.set_num_interop_threads(1)
        y=labels('train',bank)[:128];bank=bank[:128];arrays={'embeddings':arrays['embeddings'][:128]}
        raw=raw_inputs(bank,arrays);_,count,votes=answer_information(bank);distinct=np.array(list(map(len,count)));valid=votes>0
        for name,c in SPECS.items():
            asset,info=fit(raw,y,valid,distinct,c)
            assert all(np.isfinite(v).all() for v in asset.values())
            print(json.dumps({'smoke':name,'seconds':info['seconds'],'parameters':info['parameters']}),flush=True)
        return
    assert 'torch' not in __import__('sys').modules
    f=json.loads((a.output/'freeze.json').read_text());done=[]
    for name in f['variants']:
        bundle=a.output/'variants'/name/'model_bundle'
        for n in (0,1,7):
            sb=bank[:n];sa={'embeddings':arrays['embeddings'][:n]};p=predict(sb,sa,bundle)
            assert len(p)==n and all(type(v) is int and 0<=v<4 for v in p)
        sb=copy.deepcopy(bank[:7]);sa={'embeddings':arrays['embeddings'][:7].copy()}
        original,conf=bundle_scores(sb,sa,bundle)
        for row in sb:row['id']='new-'+row['id']
        new,_=bundle_scores(sb,sa,bundle);assert np.allclose(new,original,atol=1e-10)
        perm=np.array([2,0,3,1]);pb=copy.deepcopy(sb)
        for row in pb:
            row['candidates']=[copy.deepcopy(row['candidates'][int(k)]) for k in perm]
            for i,c in enumerate(row['candidates']):c['index']=i
        ps,_=bundle_scores(pb,{'embeddings':sa['embeddings'][:,perm]},bundle)
        assert np.allclose(ps,original[:,perm],atol=1e-9,rtol=1e-9),name
        fake=[{'id':'new','question':'new question','candidates':[{'index':i,'text':'unknown'} for i in range(4)]}]
        assert predict(fake,{'embeddings':np.zeros((1,4,1024),np.float32)},bundle)==[0]
        done.append(name)
    (a.output/'checks.json').write_text(json.dumps({'passed':True,'variants':done,'checks':['NumPy-only inference',
      'empty, one and seven question banks','arbitrary IDs','candidate permutation score equivariance','all invalid fallback']},indent=2)+'\n')
    print(json.dumps({'checked':len(done)}))
if __name__=='__main__':main()
