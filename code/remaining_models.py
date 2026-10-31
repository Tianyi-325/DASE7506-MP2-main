"""NumPy-only linear/MLP/set-context scorer with train-only preprocessing."""
import json
from pathlib import Path
import numpy as np
from reasoning_features import extract_features,relations
from vector_vote_fusion import select_from_scores


def scores_with_assets(bank,arrays,config,asset):
    embedding=np.asarray(arrays['embeddings'],dtype=np.float32)
    if embedding.shape!=(len(bank),4,1024):
        raise ValueError('Expected [N,4,1024] embeddings')
    x=(embedding-asset['embedding_mean'])/asset['embedding_scale']
    if config['features']!='none':
        extra=(extract_features(bank,config['features'])-asset['feature_mean'])/asset['feature_scale']
        x=np.concatenate([x,extra],axis=-1)
    if config['architecture']=='linear':
        return (x@asset['linear_weight']+asset['linear_bias']).reshape(len(bank),4).astype(np.float64)
    h=np.maximum(x@asset['encoder_weight']+asset['encoder_bias'],0)
    if config['architecture']=='context':
        same,votes=relations(bank)
        group=np.broadcast_to(h.mean(axis=1,keepdims=True),h.shape)
        own=same@h
        context=np.concatenate([h,group,h-group,own,h-own,votes],axis=-1)
        h=np.maximum(context@asset['context_weight']+asset['context_bias'],0)
    return (h@asset['output_weight']+asset['output_bias']).reshape(len(bank),4).astype(np.float64)


def candidate_scores(bank,arrays,checkpoint):
    if checkpoint is None:
        raise ValueError('Supply a checkpoint bundle')
    bundle=Path(checkpoint)
    config=json.loads((bundle/'config.json').read_text(encoding='utf-8'))
    with np.load(bundle/'model.npz',allow_pickle=False) as asset:
        return scores_with_assets(bank,arrays,config,asset)


def predict(bank,arrays,checkpoint):
    config=json.loads((Path(checkpoint)/'config.json').read_text(encoding='utf-8'))
    return select_from_scores(bank,candidate_scores(bank,arrays,checkpoint),config['mode'],config['alpha'])
