"""Training-free baseline: vote over answers parsed by the official parser.

Ignore unparseable answers. Break ties by earliest candidate index.
If every candidate is unparseable, select candidate zero.
"""
from collections import Counter

from common import parse_answer


def predict(bank, arrays, checkpoint):
    choices = []
    for row in bank:
        answers = [parse_answer(c['text']) for c in row['candidates']]
        counts = Counter(answer for answer in answers if answer is not None)
        if not counts:
            choices.append(0)
            continue
        best = max(counts.values())
        choices.append(next(i for i, answer in enumerate(answers)
                            if answer is not None and counts[answer] == best))
    return choices
