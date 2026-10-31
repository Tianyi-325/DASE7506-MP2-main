"""Manual residual taxonomy and existing-checker diagnostics; no training or test access."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import json,re,math
from pathlib import Path
from collections import Counter
from common import parse_answer
from reasoning_features import arithmetic_features
from broad_models import strict_equations
from run_fusion_experiments import save
OUT=Path('runs/residual_error_audit')
def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def main():
    rows=read('validation-errors.json');ann=read('manual-annotations.json');stats=read('stats.json')
    assert set(ann)==set(str(r['position']) for r in rows)
    for r in rows:
        category,subtype,evidence=ann[str(r['position'])]
        t=r['candidates'][r['selected']]['text'];a=r['answers'][r['selected']]
        cf=arithmetic_features(t,a);sf=strict_equations(t,a)
        boxes=re.findall(r'\\boxed\{([^{}]+)\}',t)
        box=parse_answer(r'\boxed{'+boxes[-1]+'}') if boxes else None
        r['annotation']={'primary':category,'subtype':subtype,'evidence':evidence,
          'caveat':'Manual visible-primary taxonomy, not gold step labels; counting errors may cross categories.'}
        r['checks']={'old_checked':round(math.expm1(cf[0])),'old_wrong':round(math.expm1(cf[2])),
          'strict_checked':round(math.expm1(sf[0])),'strict_wrong_fraction':sf[1],
          'last_boxed_answer':box,'boxed_disagrees_with_official':box is not None and box!=a}
    save(OUT/'annotated-errors.json',rows)
    primary=dict(Counter(r['annotation']['primary'] for r in rows))
    arith=[r for r in rows if r['annotation']['primary']=='arithmetic']
    diagnostic={'primary_manual_counts':primary,'arithmetic_cases':[r['position'] for r in arith],
      'old_checker_flags_arithmetic_primary':sum(r['checks']['old_wrong']>0 for r in arith),
      'strict_checker_flags_arithmetic_primary':sum(r['checks']['strict_wrong_fraction']>0 for r in arith),
      'selected_boxed_official_disagreement_cases':[r['position'] for r in rows if r['checks']['boxed_disagrees_with_official']],
      'all_focused_wrong_by_manual_primary':dict(Counter(r['annotation']['primary'] for r in rows if r['all_focused_models_wrong']))}
    save(OUT/'taxonomy-and-checks.json',diagnostic)
    lines=['# 剩余错题审计与三个优化方向','',
      '本轮仅分析训练内折外预测和验证错题，没有读取测试题或测试参考答案，没有训练/修改任何模型。官方输入、解析器、评分器与既有冻结资产保持不变。',
      '分析基准是最新一轮按规则保留的base_all_linear_l210，而非根据测试成绩重新挑选模型。其验证747/798，剩余51题。',
      '',
      '## 主要统计','',
      '- 51道错题中，42道只有一个正确候选，9道有两个；不能将错误候选多数当作正确证据。',
      '- 选中的错误答案在41题位于最高票组，其中23题为唯一最高票、18题为并列最高票。只有5题正确答案票数严格更多。这是错题条件下的统计，不意味着多数票在全数据上没有价值。',
      '- 最新56个冻结变体，在这51题中的36题全部选错；其余15题至少一个变体选对。按真实标签逐题选现有方法的理想上界为762/798，此oracle不能部署，也不是新评分器的上限。纯粹在56个既有预测答案间切换无法修复共同错题；新评分器仍可选中现成正确候选。',
      '- 历史联合组模型能修复当前51题中的4题，但也在其他位置破坏正确选择，总验证746题，不能只统计修复而不统计破坏。',
      '- 训练内两套OOF分别错400/399题，339题两套都错。随机种子2026从这339题抽取12题阅读，亦反复出现每件与总量、单位、关系对象、前后状态错误；抽样规模小，不能推断全体类别比例。',
      '',
      '## 人工主因分类','',
      '逐题阅读了全部51题的题目、被选候选、一个最终数值正确的候选和官方参考解。以下为人工可见主因归类，不是数据提供的步骤标签；一个解答可有多个问题。31、328、497的实体计数也可归为算术；359、739除语义问题外还存在算错。','',
      '| 主因 | 数量 | 含义 |','|---|---:|---|']
    meanings={'semantic':'条件遗漏、实体/数量作用域、关系方向、状态更新、问答目标不一致',
      'arithmetic':'求和、乘法、分数或符号代数出现局部明确错误',
      'parser':'数学结论正确，但正文标题触发固定解析器得到另一数字',
      'ambiguous':'题目措辞与官方参考解释存在明显歧义或不一致'}
    for k,v in primary.items():lines.append(f'| {k} | {v} | {meanings[k]} |')
    lines+=['','## 优先方向1：数量角色、条件覆盖和答案目标对齐','',
      '优先建立带实体/单位/时间状态的数量记录，识别每件/每人/每盘与总量、已有/新增/剩余、收入/成本/利润、比较双方和目标对象。特征应检查条件是否进入最终计算，而非仅在文本中出现。',
      '例77：一位保镖一周1120，漏乘两人；例133：只算一遍油漆而遗漏第二遍；例203：剩余45本书，却把书本数当成可服务学生数9；例397：税750已算出，却最终输出税前3750。',
      '实现应先覆盖少量高精度通用模式；不能按题目ID或本次答案建立查找表。覆盖失败输出未知，而非错误。',
      '',
      '## 优先方向2：局部算式、单位及终值一致性的软验证','',
      f'人工主因为算术的{len(arith)}题，旧检查器标出其中{diagnostic["old_checker_flags_arithmetic_primary"]}题，严格整行检查器标出{diagnostic["strict_checker_flags_arithmetic_primary"]}题。标出不等于能正确选择：前者可能不够精确，后者覆盖很低。',
      '应重点处理小数/分数、LaTeX、链式等号、明示求和、变量的一步等价变换，以及最后计算值与官方解析答案是否一致；不能只增加等号计数。',
      '例52：0.6/9=1/15小时，不是2/15；例65：3+5+7+9+11=35，不是36；例757：58940*15=884100，不是883100。',
      '例733尤其说明解析问题：选中候选正文求得250，但最后一个####是“Job 3”小标题，固定解析器返回3。可增加“官方解析值与明确结论不一致”的输入特征，并选择其他候选；不能修改官方解析器。',
      '所有验证证据应作为软特征，保留未知状态。最终数值正确候选也可能有错误推理（如44、206、338、497），所以不能把发现一步问题当成必然选错的硬标签。',
      '',
      '## 优先方向3：基于具体矛盾的候选相对评分与受约束共识','',
      '在答案组之间比较真正的差异：哪条多/少乘一次、哪条使用了目标单位、哪条漏税或重复合计、哪条不满足题目关系。用这些差异辅助唯一正确候选战胜错误共识，而非直接给所有少数答案加分。',
      '例77的1120与2240、例133的90与180，可追踪差异是否恰好来自题目指定的两人/两遍；例175的2与14，需要定位两倍关系的对象和方向。',
      '此前已尝试通用上下文网络、成对损失和全局融合；本方向的新内容是可核查的差异证据，而非再换同类网络。其前提是方向1/2先提供可信信号。',
      '训练只利用训练题的官方最终答案标签，允许多个正确候选。按训练内分歧题比较修复与破坏，保留全部题的评估，避免只看错题子集而忽略新错误。',
      '',
      '## 歧义与局限','',
      '例32：“1/4 more than”按通常读法得到17，官方参考为9；例661题面写“20% of”，参考按“20% off”得到480。例661选中720本身也不合理，歧义并不能为该预测辩护。',
      '不能修改官方标签，也不应为这两道题写特殊规则；报告中单独说明其对可靠性解释的影响。这些现象也表明完全正确的语言/数学验证不一定与题库参考逐题一致。',
      '这里提出的是基于人工错因的假设，不是已证明能修复41题或7题的模型，也不承诺达到85%。验证集已有开发历史，后续应先在训练内复现信号。',
      '',
      '## 51道逐题索引（位置为从0开始）','',
      '| 位置 | 官方答案 | 选中解析答案 | 主因 | 证据 | 56个变体全错 |','|---|---|---|---|---|']
    for r in rows:lines.append(f'| {r["position"]} | {r["gold"]} | {r["answers"][r["selected"]]} | {r["annotation"]["subtype"]} | {r["annotation"]["evidence"].replace("|","/")} | {r["all_focused_models_wrong"]} |')
    lines+=['','## 复现与披露','',
      '从code/运行：','',
      '~~~bat','conda activate mp1','python -X utf8 -B analyze_residual_errors.py','python -X utf8 -B report_residual_errors.py','~~~','',
      'manual-annotations.json为本次AI辅助逐题阅读的人工注释，不是自动生成的真实步骤标签。报告生成时会校验51条注释与错题索引完全对应。',
      '原始错题、完整推理与参考解在validation-errors.json；带诊断信息的逐题记录在annotated-errors.json；统计与12题训练内抽样分别在stats.json和train-oof-sample.json。']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(diagnostic,ensure_ascii=False))
if __name__=='__main__':main()
