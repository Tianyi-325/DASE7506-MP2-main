"""Safety, numerical export and input-contract checks for evidence round."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,json,copy,time
from pathlib import Path
import numpy as np
from math_evidence import equations,extract_evidence,VERIFY_NAMES,SEM_NAMES
from evidence_models import make_inputs,subset,member_scores,predict,base_raw,pooled

def feature_checks():
    assert equations('7 + 8 = 15')['bad']==0
    assert equations('7 + 8 = 16')['bad']==1
    assert equations(r'\frac{3}{8} = 0.375')['bad']==0
    assert equations(r'\frac{3}{8} = \frac{3}{4}')['bad']==1
    assert equations('2 hours = 120 minutes')['unit_wrong']==0
    assert equations('2 hours = 100 minutes')['unit_wrong']==1
    assert equations('3x+x=4x')['identities']==1
    assert equations('x/4-x/8=3x/8')['homogeneous']==1
    assert equations('2*x=10')['homogeneous']==0
    assert equations('__import__("os").system("bad")=1')['bad']==0
    e=equations('1+4=6\n6*2=12');assert e['repair'][__import__('fractions').Fraction(12)]==10
    b=[{'question':'Three builders each cost 11 dollars for one hour. How much money for all three builders?',
       'candidates':[{'index':j,'text':t} for j,t in enumerate([
       '11*1=11\n#### 11','11*1*3=33\n#### 33','1+4=6\n#### 6',
       '#### Part 2\nThe result is \\boxed{33}'])]}]
    blocks,_=extract_evidence(b)
    assert blocks['semantic'][0,0,SEM_NAMES.index('salient_factor_missing')]>blocks['semantic'][0,1,SEM_NAMES.index('salient_factor_missing')]
    assert blocks['verify'][0,3,VERIFY_NAMES.index('box_official_mismatch')]==1
    assert blocks['relative'][0,1,14]>0
    empty,_=extract_evidence([]);assert all(v.shape[:2]==(0,4) for v in empty.values())

def main():
    p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--output',type=Path,default=Path('runs/evidence_round'));args=p.parse_args()
    feature_checks()
    from common import load_inputs
    bank,arrays=load_inputs('train' if args.smoke else 'validation')
    if args.smoke:
        import torch
        from train_vector import labels
        from evidence_training import fit_base,fit,SPECS,BASE_CONFIGS
        torch.set_num_threads(4);torch.set_num_interop_threads(1)
        y=labels('train',bank)[:96];bank=bank[:96];arrays={'embeddings':arrays['embeddings'][:96]}
        started=time.perf_counter();data,_=make_inputs(bank,arrays)
        print(json.dumps({'feature_96_questions_seconds':time.perf_counter()-started}),flush=True)
        bases={}
        for kind in BASE_CONFIGS:bases[kind],_=fit_base(data,y,kind)
        for name,c in SPECS.items():
            asset,info=fit(data,y,c,bases.get(c['base']))
            assert all(np.isfinite(v).all() for v in asset.values())
            if c['mode']=='gated':
                never={**c,'gate_tau':-1}
                assert np.allclose(member_scores(data,never,asset),pooled(data,base_raw(data,asset,c['base']),c['base']))
            print(json.dumps({'smoke':name,'seconds':info['seconds']}),flush=True)
        return
    assert 'torch' not in __import__('sys').modules
    f=json.loads((args.output/'freeze.json').read_text(encoding='utf8'));done=[]
    for name in f['variants']:
        bundle=args.output/'variants'/name/'model_bundle'
        for n in (0,1,7):
            p=predict(bank[:n],{'embeddings':arrays['embeddings'][:n]},bundle)
            assert len(p)==n and all(type(v) is int and 0<=v<4 for v in p)
        b=copy.deepcopy(bank[:7]);a={'embeddings':arrays['embeddings'][:7].copy()};original=predict(b,a,bundle)
        for row in b:row['id']='unknown-'+row['id']
        assert predict(b,a,bundle)==original
        perm=np.array([2,0,3,1]);pb=copy.deepcopy(b)
        for row in pb:
            row['candidates']=[copy.deepcopy(row['candidates'][int(j)]) for j in perm]
            for j,c in enumerate(row['candidates']):c['index']=j
        pp=predict(pb,{'embeddings':a['embeddings'][:,perm]},bundle)
        from common import parse_answer
        for i,(x,y) in enumerate(zip(original,pp)):assert parse_answer(b[i]['candidates'][x]['text'])==parse_answer(pb[i]['candidates'][y]['text']),(name,i)
        fake=[{'id':'new','question':'new question','candidates':[{'index':j,'text':'unknown'} for j in range(4)]}]
        assert predict(fake,{'embeddings':np.zeros((1,4,1024),np.float32)},bundle)==[0]
        done.append(name)
    (args.output/'checks.json').write_text(json.dumps({'passed':True,'variants':done,
      'feature_checks':['numeric/fraction/unit/algebra','unsupported code not executed','bounded repair hypothesis',
      'condition-use and parser mismatch','cross-candidate claims','empty inputs'],
      'interface_checks':['0/1/7 questions','unknown IDs','candidate permutation by answer','all invalid fallback','NumPy inference']},indent=2)+'\n')
    print(json.dumps({'checked':len(done)}))
if __name__=='__main__':main()
