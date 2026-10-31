"""Frozen vector/vote fusion. Only NumPy and official parser at inference."""
from collections import Counter
import json
from pathlib import Path
import numpy as np
from common import parse_answer
from vector_logistic import candidate_scores


def answer_information(bank):
    answers = [[parse_answer(c['text']) for c in row['candidates']] for row in bank]
    counts = [Counter(a for a in row if a is not None) for row in answers]
    votes = np.asarray([[count.get(a, 0) if a is not None else 0 for a in row]
                        for row, count in zip(answers, counts)], dtype=np.float64).reshape(-1, 4)
    return answers, counts, votes


def select_from_scores(bank, scores, mode, alpha=0.0):
    if mode not in ('valid_only', 'vote_first', 'weighted'):
        raise ValueError('Unknown fusion mode')
    if not np.isfinite(alpha) or alpha < 0:
        raise ValueError('alpha must be finite and nonnegative')
    scores = np.asarray(scores, dtype=np.float64)
    if scores.shape != (len(bank), 4) or not np.isfinite(scores).all():
        raise ValueError('Expected finite [N,4] logits')
    _, _, votes = answer_information(bank)
    valid = votes > 0
    final = scores.copy()
    if mode == 'vote_first':
        valid &= votes == votes.max(axis=1, keepdims=True)
    elif mode == 'weighted':
        # Each extra same-answer candidate contributes alpha logit units.
        final += alpha * (votes-1)
    final[~valid] = -np.inf
    # All unparseable: deterministic candidate zero. Empty banks are supported.
    choices = final.argmax(axis=1).tolist()
    return choices


def predict(bank, arrays, checkpoint):
    if checkpoint is None:
        raise ValueError('Supply a fusion bundle')
    bundle = Path(checkpoint)
    config = json.loads((bundle/'config.json').read_text(encoding='utf-8'))
    return select_from_scores(bank, candidate_scores(bank, arrays, bundle),
                              config['mode'], config.get('alpha', 0.0))
