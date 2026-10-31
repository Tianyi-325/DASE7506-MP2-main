"""Meaningful semantic checks for arithmetic and permutation-equivariant scoring."""
import numpy as np
import torch
from reasoning_features import safe_arithmetic,arithmetic_features,relations
from remaining_models import scores_with_assets
from train_remaining import Scorer,export


def main():
    assert safe_arithmetic('(1/2)+0.5')==1.
    for expr in ["__import__('os').system('echo BAD')",'2**100','[1][0]','True']:
        try: safe_arithmetic(expr)
        except (ValueError,SyntaxError): pass
        else: raise AssertionError('Unsafe expression accepted')
    assert arithmetic_features('2+3=5','5')[1]>0
    assert arithmetic_features('0.6/9=2/15','8')[2]>0
    assert arithmetic_features(r'\frac{1}{2}=0.5','1/2')[1]>0
    assert arithmetic_features('There is no checkable equation.',None)[6]==1
    bank=[{'id':'synthetic','question':'How many?','candidates':[{'index':i,'text':'#### '+str(a)} for i,a in enumerate([1,1,2,3])]}]
    rng=np.random.default_rng(2026);x=rng.normal(size=(1,4,1024)).astype(np.float32)
    for architecture in ('linear','mlp','context'):
        torch.manual_seed(2026);model=Scorer(1024,architecture,8).eval()
        same,votes=relations(bank)
        with torch.no_grad(): expected=model(torch.from_numpy(x),torch.from_numpy(same),torch.from_numpy(votes)).numpy()
        assets={'embedding_mean':np.zeros(1024,np.float32),'embedding_scale':np.ones(1024,np.float32),**export(model)}
        config={'architecture':architecture,'features':'none'}
        actual=scores_with_assets(bank,{'embeddings':x},config,assets)
        assert np.allclose(expected,actual,atol=2e-6),(architecture,expected,actual)
        perm=[2,0,3,1];pb=[{**bank[0],'candidates':[dict(bank[0]['candidates'][j],index=i) for i,j in enumerate(perm)]}]
        reordered=scores_with_assets(pb,{'embeddings':x[:,perm]},config,assets)
        assert np.allclose(reordered,actual[:,perm],atol=2e-6),architecture
    print('Safe arithmetic, numeric equations, NumPy/Torch parity and permutation checks passed')


if __name__=='__main__': main()
