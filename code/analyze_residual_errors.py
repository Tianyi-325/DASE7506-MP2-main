"""Validation/OOF residual error audit. Never reads test references or test cases."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import json
from pathlib import Path
from collections import Counter
import numpy as np
from common import load_inputs,read_jsonl,DATA,parse_answer
from vector_vote_fusion import answer_information
from run_fusion_experiments import save,labels
OUT=Path('runs/residual_error_audit')
def read(p):return json.loads(Path(p).read_text())
def main():
    out=OUT;out.mkdir(parents=True,exist_ok=True)
    b,a=load_inputs('validation');y=labels(b,'validation');answers,counts,votes=answer_information(b)
    main_path=Path('runs/focused_round/official/base_all_linear_l210/validation-predictions.json')
    paths={'current':main_path,
      'mature_text':Path('runs/remaining_directions/linear_text_weighted/validation-predictions.json'),
      'historical_joint':Path('runs/direct_group_round/joint_group_valid_only/validation-predictions.json')}
    # Some prior evaluators store predictions under the variant directory, others in official.
    predictions={}
    for n,p in paths.items():
        r=read(p);assert r['ids']==[row['id'] for row in b];predictions[n]=np.array(r['selected'])
    current=predictions['current'];wrong=~y[np.arange(len(b)),current]
    refs=read_jsonl(DATA/'gsm8k_validation.jsonl')
    f=read('runs/focused_round/freeze.json');all_correct=[]
    for n in f['variants']:
        p=read(Path('runs/focused_round/official')/n/'validation-predictions.json')
        assert p['ids']==[row['id'] for row in b]
        all_correct.append(y[np.arange(len(b)),p['selected']])
    oracle=np.stack(all_correct).any(axis=0)
    records=[]
    for i in np.flatnonzero(wrong):
        selected=int(current[i]);gold=next(answers[i][j] for j in np.flatnonzero(y[i]))
        leader=max(counts[i].values());lead_groups=sum(v==leader for v in counts[i].values())
        records.append({'position':int(i),'id':b[i]['id'],'question':b[i]['question'],
          'gold':gold,'selected':selected,'answers':answers[i],'correct_indices':np.flatnonzero(y[i]).tolist(),
          'vote_counts':dict(counts[i]),'selected_votes':int(votes[i,selected]),'gold_votes':int(counts[i][gold]),
          'leader_tie':bool(lead_groups>1),'selected_is_leader':bool(votes[i,selected]==leader),
          'all_focused_models_wrong':bool(not oracle[i]),
          'predictions':{n:int(p[i]) for n,p in predictions.items()},
          'correct':{n:bool(y[i,p[i]]) for n,p in predictions.items()},
          'candidates':b[i]['candidates'],'reference_solution':refs[i]['answer']})
    stats={'source':'validation residuals of focused-round selected baseline; train OOF diagnostics; no test case/reference access',
      'n':len(b),'wrong':int(wrong.sum()),'wrong_by_gold_candidate_count':dict(Counter(int(y[i].sum()) for i in np.flatnonzero(wrong))),
      'selected_leader':sum(r['selected_is_leader'] for r in records),
      'selected_wrong_unique_plurality':sum(r['selected_is_leader'] and not r['leader_tie'] for r in records),
      'selected_wrong_tied_leader':sum(r['selected_is_leader'] and r['leader_tie'] for r in records),
      'gold_has_more_votes_than_selected':sum(r['gold_votes']>r['selected_votes'] for r in records),
      'all_focused_wrong':sum(r['all_focused_models_wrong'] for r in records),
      'validation_oracle_correct_among56':int(oracle.sum()),
      'reference_models':{n:{'correct':int(y[np.arange(len(b)),p].sum()),
        'also_wrong_on_current_wrong':int((wrong&~y[np.arange(len(b)),p]).sum()),
        'fix_current_errors':int((wrong&y[np.arange(len(b)),p]).sum())} for n,p in predictions.items()},
      'warning':'Oracle uses validation labels and is only a complementarity upper bound, never an implementable selector.'}
    # OOF stability and a fixed random sample of persistent TRAIN errors for reading.
    z=dict(np.load('runs/focused_round/training-cache.npz'));ty=z['y'];rr=[]
    for seed in (101,307):
        s=np.load(f'runs/focused_round/oof-{seed}.npz')['base_all_linear_l210']
        scale=np.load(f'runs/focused_round/scales-{seed}.npz')['base_all_linear_l210']
        s=s/scale[z[f'fold_{seed}'],None]+.25*(z['votes']-1);s[~z['valid']]=-1e30
        rr.append(s.argmax(axis=1))
    train_wrong=[~ty[np.arange(len(ty)),c].astype(bool) for c in rr]
    persistent=train_wrong[0]&train_wrong[1]
    stats['train_oof']={'wrong_each_seed':[int(v.sum()) for v in train_wrong],
      'wrong_both':int(persistent.sum()),'wrong_either':int((train_wrong[0]|train_wrong[1]).sum())}
    tb,_=load_inputs('train');tr=read_jsonl(DATA/'gsm8k_train.jsonl')
    chosen=np.random.default_rng(2026).choice(np.flatnonzero(persistent),12,replace=False)
    samples=[]
    for i in chosen:
        samples.append({'position':int(i),'question':tb[i]['question'],'selected':[int(c[i]) for c in rr],
          'correct_indices':np.flatnonzero(ty[i]).tolist(),'candidates':tb[i]['candidates'],'reference_solution':tr[i]['answer']})
    save(out/'validation-errors.json',records);save(out/'stats.json',stats);save(out/'train-oof-sample.json',samples)
    print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
