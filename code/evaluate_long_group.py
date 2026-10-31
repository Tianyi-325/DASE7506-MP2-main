"""Evaluate the frozen longer-training model against previous group checkpoints."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[k]='4'
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
    parser.add_argument('--output',type=Path,default=Path('runs/group_long_training'))
    args=parser.parse_args();out=args.output
    freeze=json.loads((out/'freeze.json').read_text())
    for name,h in freeze['source_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    methods={}
    old=Path('runs/vector_objectives')
    old_freeze=json.loads((old/'freeze.json').read_text())
    for mode in ('valid_only','weighted'):
        name='group_'+mode;bundle=old/name/'model_bundle'
        for file,h in old_freeze['variants'][name]['assets'].items():
            assert hashlib.sha256((bundle/file).read_bytes()).hexdigest()==h
        methods['previous_'+mode]=bundle
    for name,v in freeze['variants'].items():
        bundle=out/name/'model_bundle'
        for file,h in v['assets'].items():
            assert hashlib.sha256((bundle/file).read_bytes()).hexdigest()==h
        methods['long_'+name]=bundle
    # Persist recommendation from validation counts before opening test scores.
    prior={mode:old_freeze['variants']['group_'+mode]['validation_correct'] for mode in ('valid_only','weighted')}
    validation_counts={'previous_'+mode:count for mode,count in prior.items()}
    validation_counts.update({'long_'+mode:v['validation_correct'] for mode,v in freeze['variants'].items()})
    selected=max(validation_counts,key=validation_counts.get)
    save(out/'validation-recommendation.json',{'method':selected,'correct':validation_counts[selected],
         'basis':'validation accuracy; ties preserve previous model, then valid_only',
         'checkpoint':str(methods[selected])})
    evaluations={};predictions={}
    for split in ('validation','test'):
        evaluations[split]={}
        for name,bundle in methods.items():
            result,choices=official(out,name,'vector_vote_fusion.py',bundle,split)
            evaluations[split][name]=result
            if split=='validation':
                predictions[name]=choices
            print(json.dumps({'split':split,'method':name,'correct':result['correct'],'accuracy':result['accuracy'],'seconds':result['fresh_prediction_plus_scoring_seconds']}),flush=True)
    assert all(evaluations['validation'][name]['correct']==count for name,count in validation_counts.items())
    bank,_=load_inputs('validation');y=labels(bank,'validation')
    answers,counts,votes=answer_information(bank)
    correct={name:y[np.arange(len(y)),choice] for name,choice in predictions.items()}
    ties=np.array([sum(v==max(c.values()) for v in c.values())>1 if c else False for c in counts])
    masks={'all':np.ones(len(y),dtype=bool),'answer_disagreement':np.array([len(c)>1 for c in counts]),'tied_leaders':ties,'unique_leader':~ties}
    groups={}
    for group,mask in masks.items():
        groups[group]={'n':int(mask.sum()),'methods':{}}
        for name,value in correct.items():
            groups[group]['methods'][name]={'correct':int(value[mask].sum()),'accuracy':100*float(value[mask].mean()),
                'vs_previous_weighted':{'fixed':int((mask&value&~correct['previous_weighted']).sum()),
                                        'broken':int((mask&~value&correct['previous_weighted']).sum())}}
    save(out/'validation-cases.json',[{'position':i,'id':row['id'],'question':row['question'],'answers':answers[i],
        'correct_indices':np.flatnonzero(y[i]).tolist(),'selected':{n:int(c[i]) for n,c in predictions.items()},
        'correct':{n:bool(c[i]) for n,c in correct.items()}} for i,row in enumerate(bank)])
    hardware={'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,'threads':4}
    if sys.platform=='win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            hardware['cpu_name']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    save(out/'experiment-results.json',{'evaluations':evaluations,'validation_groups':groups,'hardware':hardware,
         'asset_bytes':{name:v['asset_bytes'] for name,v in freeze['variants'].items()},'recommended':selected,
         'timing':'Single fresh prediction + independent scoring, including startup/import/load; local CPU, not reference machine.',
         'test_policy':'No test results used for selection or further adjustment in this experiment.'})


if __name__=='__main__':
    main()
