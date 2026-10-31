"""Official CPU evaluation after the three-direction model freeze."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='4'
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np
from common import load_inputs
from run_fusion_experiments import official,labels,save
from reasoning_features import extract_features
from vector_vote_fusion import answer_information
from remaining_models import candidate_scores


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('runs/remaining_directions'))
    args=parser.parse_args();out=args.output
    freeze=json.loads((out/'freeze.json').read_text())
    for name,h in freeze['source_sha256'].items(): assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    methods={}
    prior=Path('runs/vector_objectives');pf=json.loads((prior/'freeze.json').read_text())
    for mode in ('valid_only','weighted'):
        name='group_'+mode;bundle=prior/name/'model_bundle'
        for file,h in pf['variants'][name]['assets'].items(): assert hashlib.sha256((bundle/file).read_bytes()).hexdigest()==h
        methods['previous_'+mode]=('vector_vote_fusion.py',bundle)
    for name,v in freeze['variants'].items():
        bundle=out/name/'model_bundle'
        for file,h in v['assets'].items(): assert hashlib.sha256((bundle/file).read_bytes()).hexdigest()==h
        methods[name]=('remaining_models.py',bundle)
    counts={'previous_'+mode:pf['variants']['group_'+mode]['validation_correct'] for mode in ('valid_only','weighted')}
    counts.update({n:v['validation_correct'] for n,v in freeze['variants'].items()})
    preferred=max(counts,key=counts.get)
    save(out/'validation-recommendation.json',{'method':preferred,'validation_correct':counts[preferred],
        'checkpoint':str(methods[preferred][1]),'basis':'validation accuracy; ties preserve earlier simpler model'})
    evaluations={};predictions={}
    for split in ('validation','test'):
        evaluations[split]={}
        for name,(method,bundle) in methods.items():
            r,c=official(out,name,method,bundle,split);evaluations[split][name]=r
            if split=='validation': predictions[name]=c
            print(json.dumps({'split':split,'method':name,'correct':r['correct'],'accuracy':r['accuracy'],'seconds':r['fresh_prediction_plus_scoring_seconds']}),flush=True)
    assert all(evaluations['validation'][name]['correct']==count for name,count in counts.items())
    bank,arrays=load_inputs('validation');y=labels(bank,'validation');answers,acounts,votes=answer_information(bank)
    correct={n:y[np.arange(len(y)),c] for n,c in predictions.items()}
    ties=np.array([sum(v==max(c.values()) for v in c.values())>1 if c else False for c in acounts])
    masks={'all':np.ones(len(y),dtype=bool),'answer_disagreement':np.array([len(c)>1 for c in acounts]),'tied_leaders':ties,'unique_leader':~ties}
    groups={}
    for group,mask in masks.items():
        groups[group]={'n':int(mask.sum()),'methods':{}}
        for n,c in correct.items():
            detail={'correct':int(c[mask].sum()),'accuracy':100*float(c[mask].mean())}
            for ref in ('previous_weighted','mlp_valid_only','context_valid_only','linear_control_valid_only'):
                detail['vs_'+ref]={'fixed':int((mask&c&~correct[ref]).sum()),'broken':int((mask&~c&correct[ref]).sum())}
            groups[group]['methods'][n]=detail
    save(out/'validation-cases.json',[{'position':i,'id':r['id'],'question':r['question'],'answers':answers[i],
        'correct_indices':np.flatnonzero(y[i]).tolist(),'selected':{n:int(c[i]) for n,c in predictions.items()},
        'correct':{n:bool(c[i]) for n,c in correct.items()}} for i,r in enumerate(bank)])
    calc=extract_features(bank,'calc');checked=calc[:,:,0]>0
    coverage={'total_candidates':int(checked.size),'candidates_with_checked_equations':int(checked.sum()),
        'questions_with_checked_equations':int(checked.any(axis=1).sum()),
        'candidates_with_detected_wrong_equations':int((calc[:,:,2]>0).sum()),
        'note':'Limited arithmetic patterns; unrecognized is unknown, not wrong. This is not full reasoning verification.'}
    confidence={}
    for family in freeze['selected']:
        raw=candidate_scores(bank,arrays,out/(family+'_valid_only')/'model_bundle')
        for mode,alpha in [('valid_only',0.),('weighted',0.25)]:
            n=family+'_'+mode;score=raw+alpha*(votes-1);data=[]
            for i,c in enumerate(acounts):
                if len(c)<2: continue
                group_scores=sorted(max(score[i,j] for j,a2 in enumerate(answers[i]) if a2==a) for a in c)
                data.append((float(group_scores[-1]-group_scores[-2]),bool(correct[n][i])))
            data.sort(key=lambda p:p[0]);quartiles=[]
            for ix in np.array_split(np.arange(len(data)),4):
                q=[data[j] for j in ix]
                quartiles.append({'n':len(q),'accuracy':100*sum(v[1] for v in q)/len(q),'min_margin':q[0][0],'max_margin':q[-1][0]})
            confidence[n]=quartiles
    hardware={'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,'threads':4,'device':'cpu'}
    if sys.platform=='win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            hardware['cpu_name']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    save(out/'experiment-results.json',{'hardware':hardware,'evaluations':evaluations,'validation_groups':groups,
        'confidence_quartiles':confidence,'arithmetic_coverage':coverage,'asset_bytes':{n:v['asset_bytes'] for n,v in freeze['variants'].items()},
        'validation_recommendation':preferred,'timing':'Fresh prediction plus independent official scoring processes; includes startup/import/load/features; local CPU, single run.'})


if __name__=='__main__': main()
