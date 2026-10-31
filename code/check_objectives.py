"""Numerical and semantic checks for multi-positive group likelihood."""
import torch
from train_objectives import group_loss


def main():
    z=torch.tensor([[1.,2.,3.,4.]],requires_grad=True)
    assert abs(float(group_loss(z,torch.ones_like(z)).detach()))<1e-6
    pos=torch.tensor([[0.,1.,0.,1.]])
    actual=group_loss(z,pos)
    expected=-torch.log(torch.softmax(z,1)[0,[1,3]].sum())
    assert torch.allclose(actual,expected)
    assert torch.allclose(actual,group_loss(z+100,pos),atol=1e-5)
    actual.backward()
    assert z.grad[0,0]>0 and z.grad[0,2]>0
    assert z.grad[0,1]<0 and z.grad[0,3]<0
    single=torch.tensor([[0.,0.,0.,1.]])
    assert torch.allclose(group_loss(z,single),torch.nn.functional.cross_entropy(z,torch.tensor([3])))
    assert torch.isfinite(group_loss(torch.tensor([[1000.,-1000.,999.,998.]]),single))
    print('Multi-positive objective checks passed')


if __name__=='__main__':
    main()
