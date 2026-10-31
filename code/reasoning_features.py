"""Deterministic text and limited arithmetic features, with no reference access."""
import ast
from fractions import Fraction
import math
import re
import numpy as np
from common import parse_answer

TEXT_NAMES=['log_chars','log_words','log_lines','log_numbers','log_question_words','word_overlap','number_coverage',
            'new_number_fraction','hash_marker','boxed_marker','log_equal_signs','log_math_operators','log_steps',
            'confidence_words','revision_words','has_valid_answer','answer_signed_log','answer_integer','answer_negative',
            'answer_zero','answer_in_question','log_sentence_count']
CALC_NAMES=['log_checked_equations','log_correct_equations','log_wrong_equations','wrong_ratio','max_relative_error_log',
            'log_unrecognized_equations','no_checked_equations','answer_matches_checked_value']
NUMBER=re.compile(r'(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:/\d+)?(?![\w.])')
EQUATION=re.compile(r'([-+\d.()*/ \t]{1,120})=([-+\d.()*/ \t]{1,120})')


def numeric_tokens(text):
    values=set()
    for match in NUMBER.finditer(text):
        try:
            values.add(str(Fraction(match.group().replace(',',''))))
        except (ValueError,ZeroDivisionError):
            pass
    return values


def safe_arithmetic(expression):
    # AST whitelist, bounded expression size: never execute candidate code.
    if len(expression)>120:
        raise ValueError('Too long')
    tree=ast.parse(expression.strip(),mode='eval')
    if len(list(ast.walk(tree)))>40:
        raise ValueError('Too complex')
    def visit(node,depth=0):
        if depth>10:
            raise ValueError('Too deep')
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            value=Fraction(str(node.value))
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=visit(node.operand,depth+1)*(1 if isinstance(node.op,ast.UAdd) else -1)
        elif isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a=visit(node.left,depth+1);b=visit(node.right,depth+1)
            if isinstance(node.op,ast.Add): value=a+b
            elif isinstance(node.op,ast.Sub): value=a-b
            elif isinstance(node.op,ast.Mult): value=a*b
            else: value=a/b
        else:
            raise ValueError('Not plain arithmetic')
        if abs(value)>10**15:
            raise ValueError('Out of bounds')
        return value
    return float(visit(tree.body))


def arithmetic_features(text,answer):
    normalized=text.replace('×','*').replace('÷','/').replace('−','-')
    for old,new in [(r'\times','*'),(r'\cdot','*'),(r'\div','/')]:
        normalized=normalized.replace(old,new)
    for _ in range(3):
        normalized=re.sub(r'\\frac\{([-+\d.]+)\}\{([-+\d.]+)\}',r'(\1/\2)',normalized)
    normalized=normalized.replace(',','').replace('$','')
    errors=[];values=[];unknown=0
    for match in EQUATION.finditer(normalized):
        try:
            left=safe_arithmetic(match.group(1));right=safe_arithmetic(match.group(2))
            err=abs(left-right)/max(1.,abs(left),abs(right))
            errors.append(err);values.extend([left,right])
        except (ValueError,SyntaxError,ZeroDivisionError,OverflowError,RecursionError):
            unknown+=1
    wrong=sum(e>1e-3 for e in errors)
    av=float(Fraction(answer)) if answer is not None else None
    match_answer=av is not None and any(abs(v-av)<=1e-3*max(1.,abs(av),abs(v)) for v in values)
    return [math.log1p(len(errors)),math.log1p(len(errors)-wrong),math.log1p(wrong),wrong/max(1,len(errors)),
            math.log1p(max(errors,default=0)),math.log1p(unknown),float(not errors),float(match_answer)]


def extract_features(bank,kind):
    if kind=='none':
        return np.zeros((len(bank),4,0),dtype=np.float32)
    if kind not in ('text','calc','textcalc'):
        raise ValueError('Unknown feature set')
    rows=[]
    for row in bank:
        qwords=set(re.findall(r'[a-z]+',row['question'].lower()))
        qnums=numeric_tokens(row['question'])
        candidates=[]
        for candidate in row['candidates']:
            text=candidate['text'];lower=text.lower()
            words=re.findall(r'[a-z]+',lower);wordset=set(words);nums=numeric_tokens(text)
            answer=parse_answer(text)
            av=float(Fraction(answer)) if answer is not None else 0.
            av=max(-1e15,min(1e15,av))
            tf=[math.log1p(len(text)),math.log1p(len(words)),math.log1p(text.count(chr(10))+1),math.log1p(len(NUMBER.findall(text))),
                math.log1p(len(qwords)),len(qwords&wordset)/max(1,len(qwords)),len(qnums&nums)/max(1,len(qnums)),
                len(nums-qnums)/max(1,len(nums)),float('####' in text),float(r'\boxed' in text),
                math.log1p(text.count('=')),math.log1p(sum(text.count(c) for c in '+−-*/×÷')),
                math.log1p(len(re.findall(r'\bstep\b',lower))),float(sum(lower.count(w) for w in ('clearly','therefore','certainly','correct'))),
                float(sum(lower.count(w) for w in ('wait','recheck','mistake','revised'))),float(answer is not None),
                math.copysign(math.log1p(abs(av)),av),float(answer is not None and Fraction(answer).denominator==1),
                float(av<0),float(answer is not None and av==0),float(answer in qnums),math.log1p(len(re.findall(r'[.!?]',text)))]
            cf=arithmetic_features(text,answer) if kind in ('calc','textcalc') else []
            candidates.append(tf if kind=='text' else cf if kind=='calc' else tf+cf)
        rows.append(candidates)
    dims=len(TEXT_NAMES) if kind=='text' else len(CALC_NAMES) if kind=='calc' else len(TEXT_NAMES)+len(CALC_NAMES)
    result=np.asarray(rows,dtype=np.float32).reshape(len(bank),4,dims)
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite engineered features')
    return result


def relations(bank):
    same=np.zeros((len(bank),4,4),dtype=np.float32)
    votes=np.zeros((len(bank),4,1),dtype=np.float32)
    for k,row in enumerate(bank):
        answers=[parse_answer(c['text']) for c in row['candidates']]
        for i,a in enumerate(answers):
            indices=[j for j,b in enumerate(answers) if a is not None and a==b] if a is not None else [i]
            same[k,i,indices]=1/len(indices)
            votes[k,i,0]=(len(indices) if a is not None else 0)/4
    return same,votes
