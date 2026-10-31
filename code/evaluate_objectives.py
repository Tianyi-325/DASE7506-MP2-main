"""Fresh CPU official evaluations of already frozen objective experiments."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='4'
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np
from common import load_inputs
from run_fusion_experiments import official,labels,save
from vector_vote_fusion import answer_information


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/vector_objectives'))
    args=parser.parse_args()
    out=args.output
    freeze=json.loads((out/'freeze.json').read_text())
    for name,value in freeze['source_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==value,name
    for name,v in freeze['variants'].items():
        for file,digest in v['assets'].items():
            assert hashlib.sha256((out/name/'model_bundle'/file).read_bytes()).hexdigest()==digest
    old=Path('runs/vector_vote_fusion')
    old_freeze=json.loads((old/'freeze.json').read_text())
    methods={}
    for alias,mode in [('original_valid_only','valid_only'),('original_weighted','weighted')]:
        bundle=old/mode/'model_bundle'
        for file,digest in old_freeze['variants'][mode]['assets'].items():
            assert hashlib.sha256((bundle/file).read_bytes()).hexdigest()==digest
        methods[alias]=bundle
    methods.update({name:out/name/'model_bundle' for name in freeze['variants']})
    evaluations={}
    predictions={}
    for split in ('validation','test'):
        evaluations[split]={}
        for name,bundle in methods.items():
            result,choices=official(out,name,'vector_vote_fusion.py',bundle,split)
            evaluations[split][name]=result
            if split=='validation':
                predictions[name]=choices
            print(json.dumps({'split':split,'method':name,'correct':result['correct'],'accuracy':result['accuracy'],'seconds':result['fresh_prediction_plus_scoring_seconds']}),flush=True)
    for name,v in freeze['variants'].items():
        assert evaluations['validation'][name]['correct']==v['validation_correct']
    bank,_=load_inputs('validation')
    y=labels(bank,'validation')
    answers,counts,votes=answer_information(bank)
    correct={name:y[np.arange(len(y)),choices] for name,choices in predictions.items()}
    ties=np.array([sum(n==max(c.values()) for n in c.values())>1 if c else False for c in counts])
    masks={'all':np.ones(len(y),dtype=bool),'answer_disagreement':np.array([len(c)>1 for c in counts]),
           'tied_leaders':ties,'unique_leader':~ties}
    groups={}
    for group,mask in masks.items():
        groups[group]={'n':int(mask.sum()),'methods':{}}
        for name,value in correct.items():
            detail={'correct':int(value[mask].sum()),'accuracy':100*float(value[mask].mean())}
            for ref in ('original_valid_only','original_weighted'):
                detail['vs_'+ref]={'fixed':int((mask&value&~correct[ref]).sum()),'broken':int((mask&~value&correct[ref]).sum())}
            groups[group]['methods'][name]=detail
    cases=[{'position':i,'id':row['id'],'question':row['question'],'answers':answers[i],
            'correct_indices':np.flatnonzero(y[i]).tolist(),
            'selected':{name:int(choices[i]) for name,choices in predictions.items()},
            'correct':{name:bool(value[i]) for name,value in correct.items()}} for i,row in enumerate(bank)]
    save(out/'validation-case-comparisons.json',cases)
    hardware={'platform':platform.platform(),'python':sys.version,'threads':4,'numpy':np.__version__}
    if sys.platform=='win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            hardware['cpu_name']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    save(out/'experiment-results.json',{'hardware':hardware,'evaluations':evaluations,'validation_groups':groups,
         'validation_preferred_variant':freeze['validation_preferred_variant'],
         'asset_bytes':{name:v['asset_bytes'] for name,v in freeze['variants'].items()},
         'note':'Each scorer selected by valid-only validation accuracy; alpha fixed 0.25. Test scored only after freeze. Local CPU timing, not reference-machine certification.'})


if __name__=='__main__':
    main()
