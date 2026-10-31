"""Select fusion alpha on validation, freeze, then run official CPU evaluations."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key] = '4'
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import numpy as np
from common import DATA, load_inputs, parse_answer, read_jsonl
from vector_logistic import candidate_scores
from vector_vote_fusion import answer_information, select_from_scores

ALPHAS = (0.0, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
VARIANTS = ('valid_only', 'vote_first', 'weighted')
SOURCES = ('vector_vote_fusion.py','run_fusion_experiments.py','vector_logistic.py','baseline_majority.py','check_fusion.py')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+chr(10), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def labels(bank, split):
    refs = read_jsonl(DATA/f'gsm8k_{split}.jsonl')
    assert len(refs) == len(bank)
    result=[]
    for row, ref in zip(bank, refs):
        assert row['id'] == ref['id'] and row['question'] == ref['question']
        gold = parse_answer(ref['answer'])
        assert gold is not None
        result.append([int((a := parse_answer(c['text'])) is not None and a == gold) for c in row['candidates']])
    result=np.asarray(result,dtype=bool)
    assert result.any(axis=1).all()
    return result


def select_and_freeze(out, source):
    if (out/'freeze.json').exists():
        raise FileExistsError('Frozen run exists; use --stage evaluate or a new --output directory')
    original = json.loads((source.parent/'freeze.json').read_text())
    for name, value in original['assets'].items():
        assert digest(source/name) == value, f'Original asset changed: {name}'
    bank, arrays = load_inputs('validation')
    y = labels(bank, 'validation')
    scores = candidate_scores(bank, arrays, source)
    records=[]
    for alpha in ALPHAS:
        choices=select_from_scores(bank,scores,'weighted',alpha)
        correct=int(y[np.arange(len(bank)), choices].sum())
        records.append({'alpha':alpha,'correct':correct,'n':len(bank),'accuracy':100*correct/len(bank)})
    # Fixed tie rule: smaller vote weight. No test input/reference is read here.
    best=max(records,key=lambda r:(r['correct'],-r['alpha']))
    variants={}
    for mode in VARIANTS:
        bundle=out/mode/'model_bundle'
        bundle.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/'model.npz',bundle/'model.npz')
        config={'mode':mode,'alpha':best['alpha'] if mode=='weighted' else 0.0,
                'vector_model_sha256':digest(source/'model.npz'),
                'formula':'raw vector logit + alpha*(same parsed answer count - 1)',
                'invalid_candidates':'excluded; all invalid falls back to zero',
                'ties':'earliest candidate among equal final scores',
                'selection':'validation only, accuracy then smaller alpha',
                'numpy_version':np.__version__}
        save(bundle/'config.json',config)
        choices=select_from_scores(bank,scores,mode,config['alpha'])
        correct=int(y[np.arange(len(bank)),choices].sum())
        variants[mode]={'config':config,'validation_correct':correct,'validation_accuracy':100*correct/len(bank),
                        'assets':{p.name:digest(p) for p in sorted(bundle.iterdir())},
                        'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir())}
    assert variants['valid_only']['validation_correct']==records[0]['correct']
    freeze={'source_bundle':str(source.resolve()),'vector_asset_sha256':digest(source/'model.npz'),
            'alpha_grid':records,'selected_alpha':best['alpha'],'selection_data':'validation only',
            'source_sha256':{name:digest(Path(name)) for name in SOURCES},'variants':variants}
    save(out/'freeze.json',freeze)
    print(json.dumps({'selected_alpha':best['alpha'],'validation_correct':{k:v['validation_correct'] for k,v in variants.items()}},indent=2),flush=True)


def official(out, name, method, checkpoint, split):
    folder=out/name
    pred=folder/f'{split}-predictions.json'
    score=folder/f'{split}-score.json'
    folder.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-B','predict.py','--method',method,'--split',split,'--output',str(pred)]
    if checkpoint is not None:
        command += ['--checkpoint',str(checkpoint)]
    tick=time.perf_counter()
    first=subprocess.run(command,check=True,capture_output=True,text=True)
    second=subprocess.run([sys.executable,'-B','score_predictions.py','--split',split,'--predictions',str(pred),'--output',str(score)],check=True,capture_output=True,text=True)
    elapsed=time.perf_counter()-tick
    (folder/f'{split}-process-log.txt').write_text(first.stdout+first.stderr+second.stdout+second.stderr,encoding='utf-8')
    result=json.loads(score.read_text())
    result['fresh_prediction_plus_scoring_seconds']=elapsed
    return result,json.loads(pred.read_text())['selected']


def diagnostics(out, predictions, freeze):
    bank,arrays=load_inputs('validation')
    y=labels(bank,'validation')
    answers,counts,votes=answer_information(bank)
    correct={name:y[np.arange(len(bank)),choices] for name,choices in predictions.items()}
    ties=np.array([sum(n==max(c.values()) for n in c.values())>1 if c else False for c in counts])
    masks={'all':np.ones(len(bank),dtype=bool),'answer_disagreement':np.array([len(c)>1 for c in counts]),
           'tied_leaders':ties,'unique_leader':~ties,'has_unparseable':(votes==0).any(axis=1)}
    groups={}
    for group,mask in masks.items():
        groups[group]={'n':int(mask.sum()),'methods':{}}
        for name,value in correct.items():
            detail={'correct':int(value[mask].sum()),'accuracy':100*float(value[mask].mean())}
            for reference in ('baseline','vector','valid_only'):
                detail[f'vs_{reference}']={'fixed':int((mask & value & ~correct[reference]).sum()),
                                          'broken':int((mask & ~value & correct[reference]).sum())}
            groups[group]['methods'][name]=detail
    pattern={}
    for i,c in enumerate(counts):
        key='-'.join(map(str,sorted(c.values(),reverse=True))) or 'none'
        key+=f';valid={int((votes[i]>0).sum())}'
        if key not in pattern:
            pattern[key]={'n':0, 'correct':dict.fromkeys(predictions,0)}
        pattern[key]['n']+=1
        for name in predictions:
            pattern[key]['correct'][name]+=int(correct[name][i])
    rows=[]
    for i,row in enumerate(bank):
        rows.append({'position':i,'id':row['id'],'question':row['question'],'answers':answers[i],
                     'correct_indices':np.flatnonzero(y[i]).tolist(),
                     'choices':{k:int(v[i]) for k,v in predictions.items()},
                     'correct':{k:bool(v[i]) for k,v in correct.items()}})
    save(out/'validation-case-comparisons.json',rows)
    raw=candidate_scores(bank,arrays,out/'valid_only/model_bundle')
    margins={}
    for mode in VARIANTS:
        alpha=freeze['variants'][mode]['config']['alpha']
        data=[]
        for i,c in enumerate(counts):
            allowed=[a for a,n in c.items() if mode!='vote_first' or n==max(c.values())]
            group_scores=[max(raw[i,j]+(alpha*(votes[i,j]-1) if mode=='weighted' else 0)
                              for j,a2 in enumerate(answers[i]) if a2==a) for a in allowed]
            if len(group_scores)>1:
                ordered=sorted(group_scores)
                data.append((ordered[-1]-ordered[-2],bool(correct[mode][i])))
        data.sort(key=lambda x:x[0])
        quartiles=[]
        for indices in np.array_split(np.arange(len(data)),4):
            if len(indices):
                values=[data[j] for j in indices]
                quartiles.append({'n':len(values),'min_margin':values[0][0],'max_margin':values[-1][0],
                                  'accuracy':100*sum(v[1] for v in values)/len(values)})
        margins[mode]={'competitive_questions':len(data),'quartiles_low_to_high':quartiles}
    return {'groups':groups,'vote_patterns':pattern,'answer_group_margin':margins,
            'confidence_note':'Margins compare distinct eligible answers, not duplicate correct candidates. They are not calibrated probabilities.'}


def evaluate(out,source):
    freeze=json.loads((out/'freeze.json').read_text())
    for name,value in freeze['source_sha256'].items():
        assert digest(Path(name))==value,f'Source changed: {name}'
    assert digest(source/'model.npz')==freeze['vector_asset_sha256']
    for name,variant in freeze['variants'].items():
        for asset,value in variant['assets'].items():
            assert digest(out/name/'model_bundle'/asset)==value
    evaluations={}
    validation_predictions={}
    methods=[('baseline','baseline_majority.py',None),('vector','vector_logistic.py',source)]
    methods += [(name,'vector_vote_fusion.py',out/name/'model_bundle') for name in VARIANTS]
    for split in ('validation','test'):
        evaluations[split]={}
        for name,method,bundle in methods:
            result,choices=official(out,name,method,bundle,split)
            evaluations[split][name]=result
            if split=='validation':
                validation_predictions[name]=choices
            print(json.dumps({'split':split,'method':name,'accuracy':result['accuracy'],'seconds':result['fresh_prediction_plus_scoring_seconds']}),flush=True)
    for name,variant in freeze['variants'].items():
        assert evaluations['validation'][name]['correct']==variant['validation_correct']
    hardware={'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,'threads':4,'logical_cpus':os.cpu_count()}
    if sys.platform=='win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            hardware['cpu_name']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    result={'hardware':hardware,'evaluations':evaluations,'validation_diagnostics':diagnostics(out,validation_predictions,freeze),
            'inference_assets':{name:{'bytes':v['asset_bytes'],'MiB':v['asset_bytes']/2**20} for name,v in freeze['variants'].items()},
            'timing_note':'Single fresh prediction plus separate official scoring process, including startup/imports/load; four-thread environment. Local hardware only.',
            'selection_note':'All three strategies and weighted alpha frozen before test scoring. Test results are descriptive, not used to choose alpha or this round preferred method.'}
    save(out/'experiment-results.json',result)
    # Preferred strategy is derived exclusively from frozen validation results.
    chosen=max(VARIANTS,key=lambda name:(freeze['variants'][name]['validation_correct'],-VARIANTS.index(name)))
    save(out/'validation-selected-method.json',{'method':chosen,'basis':'validation accuracy, ties prefer earlier simpler strategy','checkpoint':str(out/chosen/'model_bundle')})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/vector_vote_fusion'))
    parser.add_argument('--source-bundle',type=Path,default=Path('runs/vector_logistic/model_bundle'))
    parser.add_argument('--stage',choices=('all','select','evaluate'),default='all')
    args=parser.parse_args()
    subprocess.run([sys.executable,'-B','check_fusion.py'],check=True)
    started=time.perf_counter()
    if args.stage in ('all','select'):
        select_and_freeze(args.output,args.source_bundle)
        save(args.output/'selection-resources.json',{'selection_seconds':time.perf_counter()-started,'new_training':False,'alpha_candidates':len(ALPHAS)})
    if args.stage in ('all','evaluate'):
        evaluate(args.output,args.source_bundle)


if __name__=='__main__':
    main()
