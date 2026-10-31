"""Render the recorded fusion experiment into a Chinese Markdown report."""
import argparse
import json
from pathlib import Path

NAMES={'baseline':'多数投票','vector':'纯向量','valid_only':'向量+有效性屏蔽','vote_first':'投票优先+向量解平票','weighted':'向量与票数加权融合'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/vector_vote_fusion'))
    args=parser.parse_args()
    out=args.output
    results=json.loads((out/'experiment-results.json').read_text(encoding='utf-8'))
    freeze=json.loads((out/'freeze.json').read_text(encoding='utf-8'))
    resources=json.loads((out/'selection-resources.json').read_text(encoding='utf-8'))
    chosen=json.loads((out/'validation-selected-method.json').read_text(encoding='utf-8'))
    cases=json.loads((out/'validation-case-comparisons.json').read_text(encoding='utf-8'))
    lines=['# 第二轮：固定向量模型与答案投票融合', '',
           '## 设计与数据使用', '',
           '本轮沿用上一轮逻辑回归的全部权重，不重新训练、不增加外部数据或预训练参数。所有三种策略共用同一个 model.npz，其 SHA256 记录在 freeze.json。只依据验证集选择加权系数，并保存配置和源文件哈希后，才对固定的三个变体进行测试评分。测试结果不参与本轮系数或推荐方法选择。', '',
           '1. valid_only：只屏蔽官方解析器无法解析最终答案的候选，再按原始向量 logit 选择。',
           '2. vote_first：先保留最高票答案对应的候选，再选择向量 logit 最高的候选。',
           '3. weighted：屏蔽不可解析候选；最终分数 = 原始向量 logit + alpha ×（同答案候选数 − 1）。这属于候选级软融合，不是概率相加；同答案候选之间仍按向量分数选择。', '',
           '分数并列选择较早候选；全部不可解析时返回候选0。数值等价性完全沿用 common.parse_answer，例如0.5与1/2共享票数。未改动官方数据、解析器或评分器。', '',
           '## 验证集参数搜索', '',
           '预先固定8个系数，按验证题级准确率选择，相同则优先较小系数。alpha=0等价于有效性屏蔽实验。没有对其他系数进行测试集搜索。', '',
           '| alpha | 验证正确数 | 验证准确率 |','|---:|---:|---:|']
    for r in freeze['alpha_grid']:
        lines.append(f"| {r['alpha']} | {r['correct']}/{r['n']} | {r['accuracy']:.4f}% |")
    lines += ['',f"选定 alpha={freeze['selected_alpha']}；参数搜索内部用时 {resources['selection_seconds']:.3f} 秒，包含验证输入加载、原模型打分、8组规则评测与导出；不含解释器启动和导入。没有新增训练。", '',
              '## 官方评测结果', '', '| 方法 | 验证集 | 测试集 |','|---|---:|---:|']
    for name in NAMES:
        v=results['evaluations']['validation'][name]
        t=results['evaluations']['test'][name]
        lines.append(f"| {NAMES[name]} | {v['correct']}/{v['n']}（{v['accuracy']:.4f}%） | {t['correct']}/{t['n']}（{t['accuracy']:.4f}%） |")
    lines += ['', f"本轮按验证集推荐：{NAMES[chosen['method']]}。测试成绩仅描述这些已冻结变体。", '',
              '## 验证集错误变化', '', '| 新方法 | 相对纯向量修正/破坏 | 相对屏蔽后向量修正/破坏 | 相对投票修正/破坏 |', '|---|---:|---:|---:|']
    for name in ('valid_only','vote_first','weighted'):
        r=results['validation_diagnostics']['groups']['all']['methods'][name]
        deltas=[f"{r['vs_'+ref]['fixed']} / {r['vs_'+ref]['broken']}" for ref in ('vector','valid_only','baseline')]
        lines.append('| '+NAMES[name]+' | '+' | '.join(deltas)+' |')
    lines += ['', '屏蔽规则相对纯向量修正4题且未破坏原有正确选择；这是评分协议层面的改进，不能算作向量推理能力增强。加权融合相对屏蔽后的向量修正12题、破坏9题，净增3题；收益较小，尚不能声称稳定显著。投票优先相对屏蔽向量净减12题，说明强制相信最高票会丢掉模型识别少数正确答案的能力。', '',
              '| 验证分组 | 题数 | 多数投票 | 纯向量 | 有效性屏蔽 | 投票优先 | 加权融合 |','|---|---:|---:|---:|---:|---:|---:|']
    for group,r in results['validation_diagnostics']['groups'].items():
        scores=[f"{r['methods'][name]['correct']}（{r['methods'][name]['accuracy']:.2f}%）" for name in NAMES]
        lines.append(f"| {group} | {r['n']} | "+' | '.join(scores)+' |')
    lines += ['', '最高票平票组中，三个新变体均为58/88；本轮小权重融合相对有效性屏蔽的净收益出现在唯一最高票组。票数适合作为可被模型推翻的辅助证据，而不宜作为强制决定。', '',
              '## 置信度分析', '',
              '本轮改用“不同可解析答案组的最高最终分数之差”，避免上一轮同答案的多个正确候选相互接近而使候选分差难以解释。仅对有至少两个合格答案组的题计算；vote_first仅在最高票答案间比较，因此它的样本为88题，与其他两种355题不同。', '',
              '| 方法 | 有竞争题数 | 分差最低四分位正确率 | 第二组 | 第三组 | 最高组 |','|---|---:|---:|---:|---:|---:|']
    for name,r in results['validation_diagnostics']['answer_group_margin'].items():
        vals=[f"{q['accuracy']:.2f}%" for q in r['quartiles_low_to_high']]
        lines.append(f"| {NAMES[name]} | {r['competitive_questions']} | "+' | '.join(vals)+' |')
    lines += ['', '加权融合的不同答案组分差在此验证集中与正确率呈递增关系。这是描述性证据，不是校准概率或独立泛化证明；每组约89题，且方法已用同一验证集选择。尚未据此拟合置信度阈值。', '',
              '## 投票模式消融', '', '| 可解析答案票型与有效候选数 | 题数 | 多数投票正确 | 纯向量正确 | 屏蔽正确 | 投票优先正确 | 加权融合正确 |','|---|---:|---:|---:|---:|---:|---:|']
    for pattern,r in results['validation_diagnostics']['vote_patterns'].items():
        lines.append(f"| {pattern} | {r['n']} | "+' | '.join(str(r['correct'][n]) for n in NAMES)+' |')
    lines += ['', '## 资源', '', f"CPU：{results['hardware'].get('cpu_name','unknown')}；四线程，Python与NumPy版本详见 experiment-results.json。每个策略只部署自己的 model_bundle，三个目录是互斥实验变体，不是三模型集成。", '',
              '| 方法 | 资产字节 | 资产MiB | 验证完整耗时 | 测试完整耗时 |','|---|---:|---:|---:|---:|']
    for name,asset in results['inference_assets'].items():
        v=results['evaluations']['validation'][name]['fresh_prediction_plus_scoring_seconds']
        t=results['evaluations']['test'][name]['fresh_prediction_plus_scoring_seconds']
        lines.append(f"| {NAMES[name]} | {asset['bytes']} | {asset['MiB']:.6f} | {v:.3f} 秒 | {t:.3f} 秒 |")
    lines += ['', '计时包含新进程预测及另一个独立评分进程的启动、导入、加载、解析和官方校验；每项一次。细小时间差不能解释为稳定速度差。尚未在课程参考Xeon上验证。', '',
              '## 局限与下一步', '',
              '- 单一验证划分；本轮融合仅一个标量，未开展交叉验证或统计显著性检验。',
              '- 验证集被持续用于开发，后续应控制搜索规模；若增加可训练融合器，采用训练集内交叉验证预测拟合，不用验证标签训练。',
              '- 当前仍是手工线性票数奖励，不会识别题目语义或检查算术。下一步按原规划先研究评分器训练目标，再研究候选间比较。',
              '- 原始logit的尺度来自固定的上一轮模型。若将来更换向量模型，alpha不能直接视为通用参数。',
              '- AI披露：本轮代码、实验运行及分析由Codex辅助完成，最终提交需披露实质性帮助并理解实现。', '',
              '## 代表性验证变化（自动列举，非人工语义归因）', '']
    for title,ref,new,before,after in [('屏蔽修正','vector','valid_only',False,True),('融合修正','valid_only','weighted',False,True),('融合破坏','valid_only','weighted',True,False)]:
        lines += [f'### {title}', '']
        selected=[c for c in cases if c['correct'][ref]==before and c['correct'][new]==after][:3]
        for c in selected:
            lines += [f"- 验证第{c['position']+1}题：{c['question']}",
                      f"  候选解析答案：{c['answers']}；正确候选：{c['correct_indices']}；{ref}选择{c['choices'][ref]}，{new}选择{c['choices'][new]}。", '']
    lines += ['完整逐题变化见 validation-case-comparisons.json；全部机器可读统计见 experiment-results.json；参数、资产及源码哈希见 freeze.json。']
    (out/'REPORT.md').write_text(chr(10).join(lines)+chr(10),encoding='utf-8')
    print(out/'REPORT.md')


if __name__=='__main__':
    main()
