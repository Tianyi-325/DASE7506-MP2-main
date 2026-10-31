"""Descriptive validation error analysis; never reads test references."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from common import DATA, load_bank, parse_answer, read_jsonl, validate_choices


def main():
    output = Path('runs/baseline_majority')
    predictions = json.loads((output / 'validation-predictions.json').read_text())
    bank = load_bank('validation')
    references = read_jsonl(DATA / 'gsm8k_validation.jsonl')
    assert predictions['split'] == 'validation'
    validate_choices(bank, predictions['ids'], predictions['selected'])
    groups = defaultdict(lambda: {'n': 0, 'correct': 0})
    categories = Counter()
    errors = []
    all_cases = []
    total_candidate_correct = 0
    total_unparsed = 0
    random_tie_expected = 0.0
    first_correct = 0
    for position, (row, ref, selected) in enumerate(zip(bank, references, predictions['selected'])):
        assert row['id'] == ref['id'] and row['question'] == ref['question']
        gold = parse_answer(ref['answer'])
        assert gold is not None
        answers = [parse_answer(c['text']) for c in row['candidates']]
        counts = Counter(a for a in answers if a is not None)
        maximum = max(counts.values(), default=0)
        leaders = [a for a, n in counts.items() if n == maximum]
        gold_votes = counts[gold]
        correct = answers[selected] is not None and answers[selected] == gold
        valid = sum(a is not None for a in answers)
        pattern = '-'.join(map(str, sorted(counts.values(), reverse=True))) or 'none'
        total_candidate_correct += gold_votes
        total_unparsed += 4-valid
        first_correct += answers[0] == gold
        random_tie_expected += (1 / len(leaders) if gold in leaders else 0) if leaders else (answers[0] == gold)
        for key in [f'pattern={pattern};valid={valid}', f'gold_votes={gold_votes}', f'valid={valid}', f'leaders={len(leaders)}', f'disagreement={len(counts) >= 2}']:
            groups[key]['n'] += 1
            groups[key]['correct'] += int(correct)
        category = 'correct'
        if not correct:
            if not counts:
                category = 'all_unparseable'
            elif gold in leaders:
                category = 'tie_break_lost_correct_answer'
            elif len(leaders) == 1:
                category = 'unique_wrong_plurality'
            else:
                category = 'tied_wrong_leaders_gold_below'
            categories[category] += 1
        case = {'position': position, 'id': row['id'], 'question': row['question'],
                'gold': gold, 'answers': answers, 'selected': selected,
                'correct_indices': [i for i,a in enumerate(answers) if a is not None and a == gold],
                'vote_pattern': pattern, 'valid_candidates': valid, 'gold_votes': gold_votes,
                'leaders': leaders, 'category': category,
                'candidates': row['candidates'], 'reference_solution': ref['answer']}
        all_cases.append(case)
        if not correct:
            errors.append(case)
    summary = {'split': 'validation', 'n': len(bank), 'correct': len(bank)-len(errors),
               'errors': len(errors), 'error_categories': dict(categories),
               'unparseable_candidates': total_unparsed,
               'total_candidates': 4*len(bank),
               'uniform_random_candidate_expected_accuracy': 100*total_candidate_correct/(4*len(bank)),
               'first_candidate_accuracy': 100*first_correct/len(bank),
               'random_answer_tie_break_expected_accuracy': 100*random_tie_expected/len(bank),
               'groups': dict(sorted(groups.items()))}
    (output/'validation-error-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'validation-errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'validation-analysis-all.json').write_text(json.dumps(all_cases, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
