"""Two fixed vote-unit controls, declared after main selection; never change selection."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import argparse,json,shutil
from pathlib import Path
import numpy as np
from common import load_inputs
from run_fusion_experiments import labels,official,save,digest
from vector_vote_fusion import select_from_scores
def main(stage):
    out=Path('runs/evidence_round');sf=out/'unit-controls-freeze.json'
    if stage=='freeze':
        if sf.exists():return
        main=json.loads((out/'freeze.json').read_text(encoding='utf8'))
        bank,arr=load_inputs('train');y=labels(bank,'train');del arr
        with np.load(out/'folds.npz',allow_pickle=False) as z:folds={k:z[k] for k in z.files}
        records={}
        with np.load(out/'oof-scores.npz',allow_pickle=False) as scores:
            for base in ('no_style','joint'):
                name='normalized_'+base+'_control';bundle=out/'unit-controls'/name/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
                old=out/'variants'/base/'model_bundle'
                c=json.loads((old/'config.json').read_text(encoding='utf8'));info=json.loads((out/'fits'/'full'/(base+'.json')).read_text(encoding='utf8'))
                c['alpha']=.125;c['members'][0]['scale']=info['score_scale']
                shutil.copyfile(old/'member0.npz',bundle/'member0.npz');save(bundle/'config.json',c)
                counts=[]
                for r,seed in enumerate((211,509)):
                    scale=np.ones(len(y))
                    for f in range(3):
                        m=json.loads((out/'fits'/f'seed{seed}_fold{f}'/(base+'.json')).read_text(encoding='utf8'))
                        scale[folds[str(seed)]==f]=m['score_scale']
                    s=scores[base][r]/scale[:,None];p=select_from_scores(bank,s,'weighted',.125)
                    counts.append(int(y[np.arange(len(y)),p].sum()))
                records[name]={'base':base,'oof_correct':counts,'assets':{p.name:digest(p) for p in bundle.iterdir()},
                  'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir())}
        save(sf,{'purpose':'Matched single-member normalization/vote units; main selection remains immutable',
          'main_selected':main['selected'],'alpha':.125,'controls':records,'source_sha256':digest(Path(__file__)),
          'no_new_fitting_or_selection':True})
        print(json.dumps({'fixed_unit_controls':records}),flush=True)
        return
    f=json.loads(sf.read_text(encoding='utf8'));assert digest(Path(__file__))==f['source_sha256']
    results={}
    for n,r in f['controls'].items():
        bundle=out/'unit-controls'/n/'model_bundle'
        for p,h in r['assets'].items():assert digest(bundle/p)==h
        results[n]={}
        for split in ('validation','test'):
            results[n][split],_=official(out/'unit-controls-official',n,'evidence_models.py',bundle,split)
            print(json.dumps({'unit_control':n,'split':split,**results[n][split]}),flush=True)
    save(out/'unit-controls-results.json',results)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['freeze','evaluate'],required=True);main(p.parse_args().stage)
