"""Check group normalization and NumPy/Torch pooling equivalence."""
import numpy as np
import torch
from direct_group_models import membership,pool_numpy,inputs


def main():
    def bank(a):return [{'id':'x','question':'','candidates':[{'index':i,'text':'#### '+v if v is not None else 'unknown'} for i,v in enumerate(a)]}]
    b=bank(['1/2','0.5','2','3']);m,mask,mapping=membership(b)
    assert mapping[0,0]==mapping[0,1] and mask.sum()==3
    s=np.array([[2.,2.,1.,0.]])
    for mode in ('mean','max','logmeanexp'):
        assert abs(pool_numpy(s,m,mask,mode)[0,0]-2.)<1e-10
        dm,dk,_=membership(bank(['1/2',None,'2','3']))
        assert abs(pool_numpy(s,dm,dk,mode)[0,0]-2.)<1e-10
    mixed=np.array([[3.,1.,2.,0.]])
    expected=float(torch.logsumexp(torch.tensor([3.,1.]),0)-np.log(2))
    assert np.isclose(pool_numpy(mixed,m,mask,'logmeanexp')[0,0],expected,atol=1e-6)
    assert pool_numpy(np.zeros((0,4)),*membership([])[:2],'mean').shape==(0,4)
    for kind in ('base','joint','relations'):
        for n,rows in [(1,b),(0,[])]:
            values=inputs(rows,{'embeddings':np.zeros((n,4,1024),np.float32)},kind)
            assert values.dtype==np.float32 and np.isfinite(values).all()
    from train_direct_groups import pool_torch
    for mode in ('mean','max','logmeanexp'):
        actual=pool_torch(torch.from_numpy(mixed),torch.from_numpy(m),torch.from_numpy(mask),mode).numpy()
        assert np.allclose(actual[mask],pool_numpy(mixed,m,mask,mode)[mask])
    print('Answer equivalence and duplicate-normalized mean/max/logmeanexp checks passed')


if __name__=='__main__':main()
