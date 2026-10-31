"""Train only on train; choose among nine fixed settings on validation."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '4'
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
import torch.nn.functional as F
from common import DATA, load_inputs, parse_answer, read_jsonl


def labels(split, bank):
    refs = read_jsonl(DATA / f'gsm8k_{split}.jsonl')
    if len(refs) != len(bank):
        raise ValueError('Reference length differs')
    result = []
    for row, ref in zip(bank, refs):
        assert row['id'] == ref['id'] and row['question'] == ref['question']
        gold = parse_answer(ref['answer'])
        assert gold is not None
        result.append([int((answer := parse_answer(c['text'])) is not None and answer == gold)
                       for c in row['candidates']])
    result = np.asarray(result, dtype=np.float32)
    assert (result.sum(axis=1) >= 1).all()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('runs/vector_logistic'))
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2026)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    train_bank, train_arrays = load_inputs('train')
    val_bank, val_arrays = load_inputs('validation')
    y = labels('train', train_bank)
    vy = labels('validation', val_bank)
    raw = train_arrays['embeddings'].reshape(-1, 1024)
    mean = raw.mean(axis=0, dtype=np.float64).astype(np.float32)
    scale = raw.std(axis=0, dtype=np.float64).astype(np.float32)
    scale = np.maximum(scale, 1e-6)
    x = torch.from_numpy((raw - mean) / scale)
    target = torch.from_numpy(y.reshape(-1))
    vx = ((val_arrays['embeddings'] - mean) / scale).reshape(-1, 1024)
    records = []
    best = None
    for regularization in (0.0001, 0.001, 0.01):
        weight = torch.zeros(1024, requires_grad=True)
        bias = torch.tensor(float(np.log(y.mean() / (1-y.mean()))), requires_grad=True)
        optimizer = torch.optim.Adam([weight, bias], lr=0.03)
        tick = time.perf_counter()
        for epoch in range(1, 121):
            optimizer.zero_grad(set_to_none=True)
            logits = x @ weight + bias
            loss = F.binary_cross_entropy_with_logits(logits, target) + 0.5*regularization*weight.square().sum()
            loss.backward()
            optimizer.step()
            if epoch not in (40, 80, 120):
                continue
            w = weight.detach().numpy().copy()
            b = float(bias.detach())
            scores = (vx @ w + b).reshape(-1, 4)
            choices = scores.argmax(axis=1)
            correct = int(vy[np.arange(len(vy)), choices].sum())
            flat = scores.reshape(-1).astype(np.float64)
            nll = float(np.mean(np.logaddexp(0, flat) - vy.reshape(-1)*flat))
            record = {'l2': regularization, 'epoch': epoch, 'validation_correct': correct,
                      'validation_n': len(vy), 'validation_accuracy': 100*correct/len(vy),
                      'validation_candidate_nll': nll, 'elapsed_for_l2_seconds': time.perf_counter()-tick}
            records.append(record)
            print(json.dumps(record), flush=True)
            # Accuracy first, candidate NLL second; never inspect test to choose.
            rank = (correct, -nll)
            if best is None or rank > best['rank']:
                best = {'rank': rank, 'record': record.copy(), 'weight': w, 'bias': b}
    output = args.output
    bundle = output / 'model_bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    folded_weight = best['weight'].astype(np.float64) / scale.astype(np.float64)
    folded_bias = best['bias'] - np.dot(mean.astype(np.float64), folded_weight)
    # Export float64 to minimize cancellation; no training dependency at inference.
    np.savez(bundle/'model.npz', weight=folded_weight, bias=np.asarray(folded_bias))
    exported = (val_arrays['embeddings'] @ folded_weight + folded_bias).argmax(axis=1)
    assert int(vy[np.arange(len(vy)), exported].sum()) == best['record']['validation_correct']
    config = {'method': 'independent_embedding_logistic_regression', 'seed': 2026,
              'training_device': 'cpu', 'threads': 4, 'optimizer': 'Adam', 'learning_rate': 0.03,
              'loss': 'candidate BCE + 0.5*l2*sum(weight**2)', 'positive_label': 'official parsed numeric answer matches gold',
              'standardization': 'train-only mean/std, folded into exported coefficients',
              'selected_by': 'validation selection accuracy; ties by candidate NLL',
              'selected': best['record'], 'grid': {'l2': [0.0001,0.001,0.01], 'epochs': [40,80,120]},
              'train_questions': len(y), 'train_positive_fraction': float(y.mean()),
              'dependencies': {'numpy': np.__version__, 'torch': torch.__version__}}
    (bundle/'config.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    elapsed = time.perf_counter()-started
    (output/'training-results.json').write_text(json.dumps({'config': config, 'experiments': records,
                    'training_search_seconds': elapsed}, indent=2)+'\n', encoding='utf-8')
    freeze = {'selection': config['selected'], 'selection_source': 'validation only',
              'assets': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(bundle.iterdir()) if p.is_file()},
              'source_sha256': {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                                for name in ('train_vector.py','vector_logistic.py')},
              'asset_bytes': sum(p.stat().st_size for p in bundle.iterdir() if p.is_file())}
    (output/'freeze.json').write_text(json.dumps(freeze, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'selected': config['selected'], 'training_search_seconds': elapsed,
                      'asset_bytes': freeze['asset_bytes']}), flush=True)


if __name__ == '__main__':
    main()
