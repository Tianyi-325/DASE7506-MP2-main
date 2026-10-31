"""Semantic checks for answer-group construction and lexical safety."""
import numpy as np
from refinement_models import raw_features,stack_features,lexical_counts,score_assets,DIMS


def main():
    bank=[{'id':'synthetic','question':'2 apples','candidates':[{'index':i,'text':'#### '+a} for i,a in enumerate(['1/2','0.5','2','3'])]}]
    arrays={'embeddings':np.zeros((1,4,1024),dtype=np.float32)};x=raw_features(bank,arrays)
    base=np.arange(12,dtype=float).reshape(1,4,3);features,mask,mapping=stack_features(bank,x,base)
    assert mask.sum()==3 and mapping[0,0]==mapping[0,1] and features.shape==(1,4,53)
    assert np.array_equal(*[lexical_counts(t,8192)[0] for t in ('I have 12 apples','I have 99 apples')])
    rng=np.random.default_rng(2026)
    common={'base_weight':rng.normal(size=(3,DIMS)),'base_bias':np.zeros(3),'base_scale':np.ones(3)}
    config={'kind':'group_linear'};asset={**common,'meta_mean':np.zeros(53),'meta_scale':np.ones(53),'meta_weight':rng.normal(size=53)}
    scores=score_assets(bank,x,config,asset);assert scores[0,0]==scores[0,1]
    perm=[2,0,3,1];pb=[{**bank[0],'candidates':[dict(bank[0]['candidates'][j],index=i) for i,j in enumerate(perm)]}]
    ps=score_assets(pb,raw_features(pb,arrays),config,asset)
    assert np.allclose(ps,scores[:,perm])
    assert stack_features([],np.zeros((0,4,DIMS)),np.zeros((0,4,3)))[0].shape==(0,4,53)
    print('Answer equivalence, group permutation, empty input and numeric-normalized lexical checks passed')


if __name__=='__main__':main()
