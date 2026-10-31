"""Validation-only failure, subgroup and fusion-scale analysis. Does not read test."""
import json
from pathlib import Path
import numpy as np
from common import load_inputs
from train_vector import labels
from vector_vote_fusion import answer_information,select_from_scores
from run_fusion_experiments import save
OUT=Path('runs/broad_round')
def main():
    f=json.loads((OUT/'freeze.json').read_text());c=json.loads((OUT/'comparison-results.json').read_text())
    train=dict(np.load(OUT/'training-cache.npz'));oof=dict(np.load(OUT/'oof-scores.npz'))
    vs=dict(np.load(OUT/'validation-scores.npz'));sc=dict(np.load(OUT/'oof-scales.npz'))
    full=json.loads((OUT/'full-training-records.json').read_text());fold=train['fold']
    chosen=f['selected'];d=c['records'][chosen]['definition']
    selected_oof=np.zeros_like(train['y'],np.float64);selected_val=np.zeros_like(vs['baseline'])
    for m,w in zip(d['members'],d['weights']):
        selected_oof+=w*oof[m]/(sc[m][fold,None] if d['normalize'] else 1)
        selected_val+=w*vs[m]/(full[m]['score_scale'] if d['normalize'] else 1)
    results={};cases=[]
    for split in ('train_oof','validation'):
        if split=='train_oof':
            b,_=load_inputs('train');y=train['y'];values={'baseline':oof['baseline'],'gam':oof['gam'],'no_style':oof['no_style'],'selected':selected_oof}
        else:
            b,_=load_inputs('validation');y=labels('validation',b);values={'baseline':vs['baseline'],'gam':vs['gam'],'no_style':vs['no_style'],'selected':selected_val}
        answers,counts,votes=answer_information(b)
        choices={n:np.asarray(select_from_scores(b,s,'weighted',d['alpha'] if n=='selected' else .25)) for n,s in values.items()}
        correct={n:y[np.arange(len(y)),ch].astype(bool) for n,ch in choices.items()}
        distinct=np.array(list(map(len,counts)))
        ties=np.array([sum(v==max(cc.values()) for v in cc.values())>1 if cc else False for cc in counts])
        masks={'all':np.ones(len(y),bool),'one_answer':distinct==1,'disagreement':distinct>1,
          'tied_leaders':ties,'unique_leader':~ties,'one_correct_candidate':y.sum(axis=1)==1,'has_invalid':(votes==0).any(axis=1)}
        results[split]={}
        for group,mask in masks.items():
            results[split][group]={'n':int(mask.sum()),'methods':{}}
            for n,a in correct.items():
                results[split][group]['methods'][n]={'correct':int(a[mask].sum()),'accuracy':100*float(a[mask].mean()) if mask.any() else None,
                  'fixed_vs_base':int((mask&a&~correct['baseline']).sum()),'broken_vs_base':int((mask&~a&correct['baseline']).sum())}
        if split=='validation':
            for i,row in enumerate(b):
                if not correct['selected'][i] or correct['selected'][i]!=correct['baseline'][i]:
                    cases.append({'position':i,'id':row['id'],'question':row['question'],
                      'answers':answers[i],'correct_indices':np.flatnonzero(y[i]).tolist(),
                      'selected':{n:int(ch[i]) for n,ch in choices.items()},
                      'correct':{n:bool(a[i]) for n,a in correct.items()},
                      'candidates':row['candidates']})
    scales={n:{'oof_fit_score_std':sc[n].tolist(),'full_fit_score_std':full[n]['score_scale'],
               'full_over_mean_fold':float(full[n]['score_scale']/sc[n].mean())} for n in full}
    save(OUT/'subgroup-analysis.json',results);save(OUT/'validation-error-cases.json',cases);save(OUT/'fusion-scale-audit.json',scales)
    print(json.dumps({'selected':chosen,'validation':results['validation'],'scale_selected':{n:scales[n] for n in d['members']}},ensure_ascii=False))
if __name__=='__main__':main()
