"""Create a refinement report, resource audit and append unified experiment history."""
import argparse
import csv
import json
from pathlib import Path


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('runs/priority_refinements'))
    args=parser.parse_args();out=args.output
    f=read(out/'freeze.json');r=read(out/'experiment-results.json');t=read(out/'training-results.json');recommend=read(out/'validation-recommendation.json')
    with (out/'validation-search.csv').open('w',newline='',encoding='utf-8-sig') as file:
        w=csv.writer(file);w.writerow(['family','kind','metadata','validation_counts_by_alpha','validation_group_loss','training_objective'])
        for a in t['records']:w.writerow([a['family'],a['kind'],json.dumps(a['metadata']),json.dumps(a['validation_correct']),a['validation_group_loss'],a['training_objective']])
    with (out/'training-curves.csv').open('w',newline='',encoding='utf-8-sig') as file:
        w=csv.writer(file);w.writerow(['family','objective','embedding_l2','feature_l2','mix','epoch','loss'])
        for a in t['curves']:w.writerow([a[k] for k in ('family','objective','embedding_l2','feature_l2','mix','epoch','loss')])
    lines=['# 第六轮：按优先级的融合与训练方法优化', '',
        '## 目的与执行顺序', '',
        '固定数据和评分协议，依次尝试：答案组评分与折外融合、文本特征消融/分块正则化、联合目标、成对排序/难题加权、训练集词汇特征。全部使用CPU四线程，不安装新依赖。所有方法完成验证选择、保存源码和资产哈希后，才运行官方测试评分。', '',
        '## 折外融合的数据边界', '',
        '按题目将4755道训练题分成5折，同题四个候选不拆分。三种固定基础模型分别为上一轮的文本、算式和纯向量线性组内模型；每折的模型与标准化统计量只用另外4折拟合，共15次训练。验证集不参与这些拟合。基础超参数沿用上一轮选定值，不在折外过程重新搜索。', '',
        '融合器只使用训练集折外分数拟合；部署时使用在完整训练集拟合的原基础模型。折外与部署分数分布可能有差异，按折外分数统计量标准化，但不能保证完全消除。未进行外层嵌套交叉验证，因此验证选择仍有乐观偏差。', '',
        '- simple_blend：6种预设三模型权重×3种投票奖励；按验证准确率选择，奖励相同时优先较小值。基础logit以训练折外的组内中心化标准差归一化。',
        '- candidate_stack：折外训练的线性候选融合器，输入3个标准化分数和票数。',
        '- answer_group_linear / answer_group_mlp：对不同可解析答案分组，输入组内分数最大/均值/标准差/最小、支持票数、文本独特比例、文本均值和算式统计；组级交叉熵训练。MLP隐藏层16。',
        '答案组统计只用本题候选，不用ID或参考答案。多个候选同值时共享组分数，不把重复票数当作额外训练行。', '',
        '## 文本消融与其他方向', '',
        '- numeric_only：仅保留数字覆盖、答案数值性质相关文本特征，加原始向量。',
        '- style_only：仅保留长度、格式和表达相关特征，加原始向量。',
        '- no_style：保留词/数覆盖及答案性质，删除长度格式特征。',
        '- block_regularized：分别设置向量和文本块的L2，搜索向量0.001/0.01、文本0.0001/0.001/0.01。',
        '- joint_bce：组内损失加0.1或0.3倍候选BCE，包含可训练共同截距。',
        '- pairwise：同题正确候选应高于错误候选，使用softplus成对损失，每题按配对数量平均。',
        '- hard_weighted：训练集仅一个正确候选的题权重乘2。',
        '- lexical_tfidf：从训练候选拟合哈希词unigram/bigram TF-IDF，与向量和文本联合训练；数字身份替换为统一标记，8192/16384桶，IDF只由训练集拟合。它是学习词汇权重，不是外部预训练编码器。', '',
        '以上单评分器训练使用120/360轮两个预定检查点。除融合器学习票数外，其他单评分器选定后分别比较alpha=0和固定0.25，不因测试结果换配置。具体网格见training-results.json和validation-search.csv。', '',
        '## 官方成绩与限制审计', '', '| 方法 | 验证集 | 测试集 | 资产KiB | 测试完整CPU时间 |','|---|---:|---:|---:|---:|']
    for n,v in r['evaluations']['validation'].items():
        test=r['evaluations']['test'][n];audit=r['compliance'].get(n)
        size=f"{audit['asset_bytes']/1024:.2f}" if audit else '上一轮资产'
        lines.append(f"| {n} | {v['correct']}/798（{v['accuracy']:.4f}%） | {test['correct']}/467（{test['accuracy']:.4f}%） | {size} | {test['fresh_prediction_plus_scoring_seconds']:.3f}秒 |")
    lines += ['',f"按验证推荐：{recommend['method']}，checkpoint={recommend['checkpoint']}，推理文件={recommend['method_file']}。同分保留已有或顺序较前模型，不参考测试排名。", '',
        '## 验证错误变化', '', '| 方法 | 相对上一轮修正 | 破坏 | 净变化 | 分歧题正确/355 | 平票正确/88 |','|---|---:|---:|---:|---:|---:|']
    for n,a in r['validation_groups']['all']['methods'].items():
        d=r['validation_groups']['answer_disagreement']['methods'][n];tie=r['validation_groups']['tied_leaders']['methods'][n]
        lines.append(f"| {n} | {a['fixed']} | {a['broken']} | {a['fixed']-a['broken']:+d} | {d['correct']} | {tie['correct']} |")
    lines += ['', '## 各方向的验证比较', '', '| 家族 | 仅按验证选出的变体 | 验证正确数 | 相对上一轮746题 | 测试记录 |','|---|---|---:|---:|---:|']
    family_best={}
    for family in f['selected']:
        names=[n for n in f['variants'] if n.startswith(family+'_')]
        name=max(names,key=lambda n:f['variants'][n]['validation_correct']);family_best[family]=name
        val=r['evaluations']['validation'][name];test=r['evaluations']['test'][name]
        lines.append(f"| {family} | {name} | {val['correct']} | {val['correct']-746:+d} | {test['accuracy']:.2f}% |")
    lines += ['', '必须结合修正与破坏解释融合，不仅看修正样例。整体较弱的方法也可能提供互补信息，但融合应由验证证据支持。文本内部消融用于区分数值分布先验、覆盖信息与格式捷径，不证明任何单项具备数学理解。', '',
        '## 资源与合规', '',
        f"本机{r['hardware'].get('cpu_name','unknown')}，CPU四线程。训练、折外、验证选择内部耗时{t['seconds_excluding_startup_imports']:.3f}秒，不含Python启动与导入。{len(t['records'])}条验证记录（部分记录含多个投票奖励），基础折外拟合15次。", '',
        f"所有新变体资产上限检查：{all(a['asset_limit_pass'] for a in r['compliance'].values())}；本机完整30秒检查：{all(a['local_time_limit_pass'] for a in r['compliance'].values())}；官方发布文件未变：{r['official_files_unchanged']}。", '',
        '每个部署bundle自包含全部基础模型系数、融合权重、标准化统计、IDF与配置。NPZ为未压缩存储，按文件总字节保守计入16MiB；训练折外分数、折划分、日志不在推理路径中。所有数组资产均需计入，不能以源码嵌入规避。', '',
        '计时包括新预测进程及独立官方评分进程的启动、导入、加载和全部特征提取。所有库通过环境变量限制为4线程；模型无后台进程或GPU推理。参考Xeon未实测，不能仅凭本机结果正式认证资格。', '',
        '没有外部数据、额外预训练权重、ID查表、缓存预测或推理API调用。训练/验证/测试职责保持区分。所有训练只用提供的训练输入与参考，验证只用于开发选择；测试只在冻结后记录。', '',
        '## 局限与复现', '',
        '许多方案复用了同一验证集，存在多次开发选择偏差。简单融合与答案组模型的特征数、目标和正则化不同，不能把差异归因于单一因素。成对/联合目标的损失尺度也不同。词汇模型可能学习格式和模板，不应宣称过程监督。', '',
        '复现见REFINEMENT_EXPERIMENTS.md。代码：train_refinements.py、refinement_models.py、evaluate_refinements.py、report_refinements.py、check_refinements.py。逐题记录、官方JSON、模型哈希位于本目录。', '',
        'AI披露：本轮代码、实验与报告由Codex辅助完成，最终作者应理解核查并披露实质性帮助。']
    selected=r['evaluations']['validation'][recommend['method']]
    selected_test=r['evaluations']['test'][recommend['method']]
    old=r['evaluations']['validation']['previous'];old_test=r['evaluations']['test']['previous']
    lines += ['', '## 本轮结论', '',
        f"验证选择的简单融合为749/798=93.86%，相比原746题修正3、破坏0；测试为385/467=82.44%，原方法387/467=82.87%。本轮没有获得验证与测试同步改善。3道验证题的差异很小，不能证明泛化更好；不根据测试排名回头选择本轮其他变体。", '',
        '简单融合的权重为文本0.75、算式0.25、原纯向量0，投票奖励0.25。折外候选线性融合748题接近，但答案组线性745/MLP743没有超过原方法。更复杂的组统计或非线性元模型暂未得到支持；折外与全数据基础分数的分布差异也可能影响结果，但本轮不能确定唯一原因。', '',
        '文本消融：去掉格式长度后的独立评分744，高于原独立文本模型743；固定融合746与原融合持平。仅数值相关特征740/744，格式相关特征737/740，说明不能把全部收益归给格式，也不能据本轮证明所有格式都无用。', '',
        '分块正则化、联合BCE、成对排序、难题加权、哈希词汇特征均未超过本轮验证最佳。没有必要为了增加组件而全部纳入部署。词汇特征使资产和计算增加，但没有验证净收益。', '',
        '下一步更有依据的是做按题目划分的训练内部稳定性评估，检验微小融合收益是否稳定，再考虑答案组特征精简。继续无边界细搜同一验证集会增加选择偏差；85%目标仍未实现。', '',
        '检查通过：20个变体的0/1/7题输入、未知ID、候选置换、冻结哈希、原基础分数重建、15次五折记录及有限值覆盖；推理不加载PyTorch，官方文件保持未改。']

    (out/'REPORT.md').write_text(chr(10).join(lines)+chr(10),encoding='utf-8')
    summary=Path('EXPERIMENT_SUMMARY.md');existing=summary.read_text(encoding='utf-8') if summary.exists() else '# 已完成实验总结'+chr(10)
    marker='## 第六轮追加：优先级优化'
    existing=existing.split(marker)[0].rstrip()
    appendix=['',marker,'',f"验证选定：{recommend['method']}。所有模型先固定再测试，下面测试成绩是记录，不是选型依据。",'',
        '| 方向 | 验证最佳变体 | 验证正确/798 | 测试记录 |','|---|---|---:|---:|']
    for family,n in family_best.items():
        v=r['evaluations']['validation'][n];test=r['evaluations']['test'][n]
        appendix.append(f"| {family} | {n} | {v['correct']} | {test['accuracy']:.2f}% |")
    chosen=r['evaluations']['test'][recommend['method']]
    appendix += ['',f"本轮验证推荐版本的测试正确数{chosen['correct']}/467，准确率{chosen['accuracy']:.4f}%。85%对应至少397题正确。不能根据其他变体测试排名回头调整本轮推荐。",'',
        '此次进一步区分了答案组建模、折外元融合、特征块正则化、损失目标与词汇信息的贡献。详见runs/priority_refinements/REPORT.md和全部验证记录。']
    appendix += ['', '### 本轮新增结论', '',
        '验证仅净增3题的简单融合未带来同步测试提升：验证93.86%，测试82.44%，旧方法测试记录82.87%。本轮继续保留预先按验证选择的版本及原版本独立记录，不依照测试排名改选。', '',
        '折外融合没有数据泄漏捷径，但也不能保证优于单模型；答案组模型、联合目标、成对训练、加权难题与词汇模型的当前实现尚未提供更强验证证据。去除格式特征可保持相近验证表现，值得后续用训练内划分检查稳定性。', '',
        '所有20个新部署变体都通过16MiB资产和本机四线程30秒完整运行检查。参考CPU未实测，正式资格仍需课程评测确认。']

    summary.write_text(existing+chr(10)+chr(10).join(appendix)+chr(10),encoding='utf-8')
    print(out/'REPORT.md');print(summary)


if __name__=='__main__':main()
