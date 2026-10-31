"""Official frozen evaluation and constraints audit for direct group training."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
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
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('runs/direct_group_round'));args=p.parse_args();out=args.output
    f=json.loads((out/'freeze.json').read_text())
    for n,h in f['source_sha256'].items():assert hashlib.sha256(Path(n).read_bytes()).hexdigest()==h,n
    methods={};counts={}
    references=[('previous_validation_choice','refinement_models.py',Path('runs/priority_refinements'),'simple_blend_weighted'),
                ('previous_single_text','remaining_models.py',Path('runs/remaining_directions'),'linear_text_weighted')]
    for name,method,parent,variant in references:
        prior=json.loads((parent/'freeze.json').read_text());bundle=parent/variant/'model_bundle'
        for a,h in prior['variants'][variant]['assets'].items():assert hashlib.sha256((bundle/a).read_bytes()).hexdigest()==h
        methods[name]=(method,bundle);counts[name]=prior['variants'][variant]['validation_correct']
    for name,v in f['variants'].items():
        bundle=out/name/'model_bundle'
        for a,h in v['assets'].items():assert hashlib.sha256((bundle/a).read_bytes()).hexdigest()==h
        assert v['asset_bytes']<=16*2**20
        methods[name]=('direct_group_models.py',bundle);counts[name]=v['validation_correct']
    preferred=max(counts,key=counts.get)
    save(out/'validation-recommendation.json',{'method':preferred,'correct':counts[preferred],'method_file':methods[preferred][0],
         'checkpoint':str(methods[preferred][1]),'basis':'validation accuracy; ties retain earlier/previous variant'})
    results={};predictions={}
    for split in ('validation','test'):
        results[split]={}
        for name,(method,bundle) in methods.items():
            value,choice=official(out,name,method,bundle,split);results[split][name]=value
            if split=='validation':predictions[name]=choice
            print(json.dumps({'split':split,'method':name,'correct':value['correct'],'accuracy':value['accuracy'],'seconds':value['fresh_prediction_plus_scoring_seconds']}),flush=True)
    assert all(results['validation'][n]['correct']==value for n,value in counts.items())
    bank,_=load_inputs('validation');y=labels(bank,'validation');answers,ac,votes=answer_information(bank)
    correctness={n:y[np.arange(len(y)),choice] for n,choice in predictions.items()}
    ties=np.asarray([sum(v==max(c.values()) for v in c.values())>1 if c else False for c in ac])
    masks={'all':np.ones(len(y),bool),'answer_disagreement':np.array([len(c)>1 for c in ac]),'tied_leaders':ties,'unique_leader':~ties};groups={}
    for group,mask in masks.items():
        groups[group]={'n':int(mask.sum()),'methods':{}}
        for n,c in correctness.items():
            result={'correct':int(c[mask].sum()),'accuracy':100*float(c[mask].mean())}
            for ref in ('previous_single_text','previous_validation_choice'):
                result['vs_'+ref]={'fixed':int((mask&c&~correctness[ref]).sum()),'broken':int((mask&~c&correctness[ref]).sum())}
            groups[group]['methods'][n]=result
    save(out/'validation-cases.json',[{'position':i,'id':row['id'],'question':row['question'],'answers':answers[i],
        'correct_indices':np.flatnonzero(y[i]).tolist(),'selected':{n:int(c[i]) for n,c in predictions.items()},
        'correct':{n:bool(c[i]) for n,c in correctness.items()}} for i,row in enumerate(bank)])
    hardware={'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,'threads':4,'device':'cpu'}
    if sys.platform=='win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:hardware['cpu_name']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    manifest=json.loads(Path('PACKAGE_MANIFEST.json').read_text());unchanged=all(hashlib.sha256((Path('..')/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items());assert unchanged
    compliance={n:{'asset_bytes':v['asset_bytes'],'asset_limit_pass':v['asset_bytes']<=16*2**20,
        'local_seconds':results['test'][n]['fresh_prediction_plus_scoring_seconds'],'local_time_limit_pass':results['test'][n]['fresh_prediction_plus_scoring_seconds']<=30} for n,v in f['variants'].items()}
    save(out/'experiment-results.json',{'evaluations':results,'validation_groups':groups,'hardware':hardware,'recommended':preferred,
        'compliance':compliance,'official_files_unchanged':unchanged,'note':'One fresh prediction process + independent scoring. Local hardware only; reference Xeon not tested. Selection frozen before test.'})


if __name__=='__main__':main()
