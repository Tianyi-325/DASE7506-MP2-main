"""Evaluate frozen vector model and baseline in fresh CPU processes."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key] = '4'
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
from common import load_inputs, parse_answer
from train_vector import labels
from vector_logistic import candidate_scores

OUT = Path('runs/vector_logistic')
BUNDLE = OUT/'model_bundle'


def fresh_evaluation(method, split, checkpoint=None):
    folder = OUT / ('baseline' if checkpoint is None else 'vector')
    folder.mkdir(parents=True, exist_ok=True)
    prediction = folder/f'{split}-predictions.json'
    score = folder/f'{split}-score.json'
    command = [sys.executable, '-B', 'predict.py', '--method', method, '--split', split, '--output', str(prediction)]
    if checkpoint is not None:
        command += ['--checkpoint', str(checkpoint)]
    started = time.perf_counter()
    subprocess.run(command, check=True)
    subprocess.run([sys.executable, '-B', 'score_predictions.py', '--split', split,
                    '--predictions', str(prediction), '--output', str(score)], check=True)
    elapsed = time.perf_counter()-started
    result = json.loads(score.read_text())
    result['fresh_prediction_plus_scoring_seconds'] = elapsed
    return result, json.loads(prediction.read_text())['selected']


def validation_diagnostics():
    bank, arrays = load_inputs('validation')
    y = labels('validation', bank)
    vector = json.loads((OUT/'vector/validation-predictions.json').read_text())['selected']
    baseline = json.loads((OUT/'baseline/validation-predictions.json').read_text())['selected']
    vr = y[np.arange(len(y)), vector].astype(bool)
    br = y[np.arange(len(y)), baseline].astype(bool)
    from collections import Counter
    all_cases = []
    for row in bank:
        answers = [parse_answer(c['text']) for c in row['candidates']]
        counts = Counter(a for a in answers if a is not None)
        maximum = max(counts.values(), default=0)
        all_cases.append({'answers': answers, 'leaders': [a for a,n in counts.items() if n == maximum]})
    groups = {}
    for name, mask in {
        'all': np.ones(len(bank), dtype=bool),
        'answer_disagreement': np.array([len(set(a for a in c['answers'] if a is not None))>=2 for c in all_cases]),
        'tied_leaders': np.array([len(c['leaders'])>1 for c in all_cases]),
        'unique_leader': np.array([len(c['leaders'])==1 for c in all_cases]),
    }.items():
        groups[name] = {'n': int(mask.sum()), 'vector_correct': int(vr[mask].sum()),
                        'baseline_correct': int(br[mask].sum()),
                        'fixed': int((mask & vr & ~br).sum()), 'broken': int((mask & ~vr & br).sum())}
    scores = candidate_scores(bank, arrays, BUNDLE)
    probabilities = 1/(1+np.exp(-np.clip(scores, -60, 60)))
    flat_y = y.reshape(-1)
    flat_p = probabilities.reshape(-1)
    brier = float(np.mean((flat_p-flat_y)**2))
    bins = []
    ece = 0.0
    for low in np.arange(0,1,0.1):
        mask = (flat_p >= low) & ((flat_p < low+0.1) if low<0.9 else (flat_p<=1))
        if mask.any():
            confidence = float(flat_p[mask].mean())
            frequency = float(flat_y[mask].mean())
            ece += mask.mean()*abs(confidence-frequency)
            bins.append({'lower': float(low),'n': int(mask.sum()),'mean_probability':confidence,'actual_correct_fraction':frequency})
    margin = np.sort(scores, axis=1)[:,-1]-np.sort(scores,axis=1)[:,-2]
    order = np.argsort(margin, kind='stable')
    margin_groups=[]
    for i, indices in enumerate(np.array_split(order,4)):
        margin_groups.append({'quartile_low_to_high':i+1,'n':len(indices),'accuracy':float(100*vr[indices].mean()),
                              'min_logit_margin':float(margin[indices].min()),'max_logit_margin':float(margin[indices].max())})
    return {'groups':groups, 'candidate_brier': brier, 'candidate_ece_10_bins':float(ece),
            'candidate_probability_bins':bins, 'selection_margin_quartiles':margin_groups,
            'note':'Raw sigmoid probabilities are not calibrated selection probabilities; ECE is descriptive and bin-dependent.'}


def main():
    freeze = json.loads((OUT/'freeze.json').read_text())
    for name, digest in freeze['assets'].items():
        assert hashlib.sha256((BUNDLE/name).read_bytes()).hexdigest() == digest
    for name, digest in freeze['source_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
    results = {}
    # Test is scored only after training has written the frozen selection and hashes.
    for split in ('validation','test'):
        for name, method, checkpoint in [('baseline','baseline_majority.py',None),('vector','vector_logistic.py',BUNDLE)]:
            results[f'{name}_{split}'], _ = fresh_evaluation(method, split, checkpoint)
    hardware = {'platform':platform.platform(), 'processor': platform.processor(), 'logical_cpus':os.cpu_count(),
                'python':sys.version, 'threads':4}
    if sys.platform == 'win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            hardware['cpu_name'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    final = {'hardware':hardware, 'evaluations': results, 'validation_diagnostics':validation_diagnostics(),
             'asset_bytes': freeze['asset_bytes'], 'asset_MiB':freeze['asset_bytes']/2**20,
             'timing_note':'Single fresh prediction process + fresh official scoring process; includes startup/loading/imports, four-thread environment. Local CPU, not reference eligibility certification.'}
    (OUT/'experiment-results.json').write_text(json.dumps(final,indent=2)+chr(10), encoding='utf-8')
    print(json.dumps(final, indent=2))


if __name__ == '__main__':
    main()
