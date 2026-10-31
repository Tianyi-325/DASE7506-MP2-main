"""Frozen independent logistic scorer. Inference requires only NumPy."""
from pathlib import Path
import numpy as np


def candidate_scores(bank, arrays, checkpoint):
    if checkpoint is None:
        raise ValueError('Supply the trained model bundle with --checkpoint')
    features = np.asarray(arrays['embeddings'], dtype=np.float32)
    if features.shape != (len(bank), 4, 1024):
        raise ValueError('Expected [N,4,1024] embeddings')
    with np.load(Path(checkpoint) / 'model.npz', allow_pickle=False) as asset:
        # Standardization is folded into the coefficients at export time.
        return features @ asset['weight'] + float(asset['bias'].item())


def predict(bank, arrays, checkpoint):
    return candidate_scores(bank, arrays, checkpoint).argmax(axis=1).tolist()
