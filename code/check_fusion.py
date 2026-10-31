"""Check voting, parser exclusion and fallback semantics on synthetic banks."""
import numpy as np
from vector_vote_fusion import select_from_scores


def row(answers):
    return {'id': 'synthetic', 'question': '', 'candidates': [
        {'index': i, 'text': 'unparseable' if a is None else f'#### {a}'} for i,a in enumerate(answers)]}


def main():
    bank = [row([1,1,2,None])]
    scores = np.array([[0.,1.,2.,100.]])
    assert select_from_scores(bank,scores,'valid_only') == [2]
    assert select_from_scores(bank,scores,'vote_first') == [1]
    assert select_from_scores(bank,scores,'weighted',0.5) == [2]
    assert select_from_scores(bank,scores,'weighted',2.) == [1]
    # Equivalent fraction/decimal answers share votes using the official parser.
    assert select_from_scores([row(['1/2','0.5',3,4])],np.array([[0.,1.,2.,3.]]),'vote_first') == [1]
    assert select_from_scores([row([None]*4)],np.zeros((1,4)),'weighted',1.) == [0]
    assert select_from_scores([],np.zeros((0,4)),'valid_only') == []
    print('Fusion semantic checks passed')


if __name__ == '__main__':
    main()
