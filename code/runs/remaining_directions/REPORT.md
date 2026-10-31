# 第五轮：MLP、候选比较、文本与计算特征

## 实验问题与设计

完成三个此前未充分评估的方向：独立非线性评分器、利用候选集合及同答案组的上下文评分器、文本/算式信息。另设置联合上下文+文本算式模型，检验组合是否互补。所有模型只在训练集拟合，标准化统计量也只由训练集产生。

- linear_control：无额外特征的线性组内模型，作为本轮匹配控制。
- linear_text / linear_calc / linear_textcalc：分别在原始向量外加入22维文本/数字/格式特征、8维算式特征、全部30维特征，从头联合训练线性组内模型，不使用训练内模型预测训练融合器。
- mlp：候选独立共享的一层ReLU网络，神经元32或64。
- context：共享候选编码后拼接自身编码、整组均值、自身减整组均值、同答案组均值、自身减同答案组均值、答案票数比例，再通过非线性网络评分。无位置编码，候选重排时评分随候选重排。
- context_textcalc：上下文模型的输入同时包含文本与算式特征。

文本特征包括长度、格式、题目词汇/数字覆盖率、答案数值性质等，不等同于理解推理。算式特征用白名单AST检查有限的显式数值等式；支持简单分数/小数和四则运算，容许1e-3相对误差。无法识别的表达式是未知，不判错；不能用它证明整份推理有效。

所有推理策略先屏蔽官方不能解析的候选。每个家族按独立评分的验证正确数选择一个模型，相同则比较组内损失；再对同一模型比较alpha=0和固定alpha=0.25。票数系数没有为新模型重新调节。测试在所有家族配置与哈希固定后才评分。

## 训练与选择

线性模型：全批量Adam、显式L2、学习率0.03，检查120/360/720轮；控制组L2固定0.001，其他线性模型比较0.001/0.01。神经网络：AdamW、Dropout=0.1、每批256题、学习率0.001，预设两个组合配置（32隐藏单元/0.001权重衰减，64隐藏单元/0.01权重衰减），检查20/40/80轮。不同容量与正则化一起改变，不能将二者贡献完全拆开。

主实验种子2026。每个神经网络家族的选定配置额外用2027复核一次，只诊断稳定性，不事后换种子、不加入集成。不同训练方法的训练损失数值不能直接横向比较。

| 家族 | 架构 | 特征 | 选定配置 | 轮次 | 独立验证正确 | 固定融合验证正确 |
|---|---|---|---|---:|---:|---:|
| linear_control | linear | none | {'hidden': 0, 'regularization': 0.001, 'lr': 0.03} | 360 | 733 | 734 |
| linear_text | linear | text | {'hidden': 0, 'regularization': 0.01, 'lr': 0.03} | 120 | 743 | 746 |
| linear_calc | linear | calc | {'hidden': 0, 'regularization': 0.01, 'lr': 0.03} | 120 | 735 | 741 |
| linear_textcalc | linear | textcalc | {'hidden': 0, 'regularization': 0.01, 'lr': 0.03} | 360 | 742 | 742 |
| mlp | mlp | none | {'hidden': 32, 'regularization': 0.001, 'lr': 0.001} | 20 | 731 | 732 |
| context | context | none | {'hidden': 64, 'regularization': 0.01, 'lr': 0.001} | 20 | 729 | 732 |
| context_textcalc | context | textcalc | {'hidden': 64, 'regularization': 0.01, 'lr': 0.001} | 80 | 737 | 738 |

### 第二种子诊断

| 家族 | 主种子独立/融合 | 复核种子独立/融合 |
|---|---:|---:|
| mlp | 731/732 | 724/730 |
| context | 729/732 | 729/727 |
| context_textcalc | 737/738 | 726/726 |

总搜索及复核内部耗时165.074秒；主搜索记录39个预定检查点。CPU四线程，无GPU或新依赖。内部时间含数据/特征准备、训练、验证和导出，不含解释器启动与导入。

## 官方评测与资源

| 方法 | 验证集 | 测试集 | 资产KiB | 测试完整CPU耗时 |
|---|---:|---:|---:|---:|
| previous_valid_only | 733/798（91.8546%） | 369/467（79.0150%） | 上轮资产 | 0.475秒 |
| previous_weighted | 734/798（91.9799%） | 371/467（79.4433%） | 上轮资产 | 0.463秒 |
| linear_control_valid_only | 733/798（91.8546%） | 369/467（79.0150%） | 14.30 | 0.483秒 |
| linear_control_weighted | 734/798（91.9799%） | 371/467（79.4433%） | 14.29 | 0.498秒 |
| linear_text_valid_only | 743/798（93.1078%） | 386/467（82.6552%） | 15.04 | 0.730秒 |
| linear_text_weighted | 746/798（93.4837%） | 387/467（82.8694%） | 15.04 | 0.766秒 |
| linear_calc_valid_only | 735/798（92.1053%） | 375/467（80.2998%） | 14.62 | 0.960秒 |
| linear_calc_weighted | 741/798（92.8571%） | 379/467（81.1563%） | 14.62 | 0.916秒 |
| linear_textcalc_valid_only | 742/798（92.9825%） | 385/467（82.4411%） | 15.39 | 0.946秒 |
| linear_textcalc_weighted | 742/798（92.9825%） | 385/467（82.4411%） | 15.38 | 0.923秒 |
| mlp_valid_only | 731/798（91.6040%） | 371/467（79.4433%） | 139.03 | 0.464秒 |
| mlp_weighted | 732/798（91.7293%） | 372/467（79.6574%） | 139.02 | 0.470秒 |
| context_valid_only | 729/798（91.3534%） | 353/467（75.5889%） | 348.29 | 0.500秒 |
| context_weighted | 732/798（91.7293%） | 354/467（75.8030%） | 348.29 | 0.510秒 |
| context_textcalc_valid_only | 737/798（92.3559%） | 372/467（79.6574%） | 356.78 | 1.011秒 |
| context_textcalc_weighted | 738/798（92.4812%） | 374/467（80.0857%） | 356.78 | 1.013秒 |

本轮按验证结果推荐：linear_text_weighted。同分优先保留顺序较前的简单或已有模型。测试结果不参与本轮推荐。

计时包括新预测进程和独立官方评分进程的启动、导入、加载、特征提取和预测，每项一次；微小差异不能视为稳定速度差。尚未在参考Xeon上验证。资产按每个互斥模型分别统计，不包括诊断种子文件；这些文件不在推理路径中。

## 错误变化与分组

| 方法 | 对上轮融合修正 | 破坏 | 对MLP独立修正 | 破坏 |
|---|---:|---:|---:|---:|
| previous_valid_only | 2 | 3 | 23 | 21 |
| previous_weighted | 0 | 0 | 22 | 19 |
| linear_control_valid_only | 2 | 3 | 23 | 21 |
| linear_control_weighted | 0 | 0 | 22 | 19 |
| linear_text_valid_only | 22 | 13 | 24 | 12 |
| linear_text_weighted | 22 | 10 | 24 | 9 |
| linear_calc_valid_only | 14 | 13 | 16 | 12 |
| linear_calc_weighted | 14 | 7 | 21 | 11 |
| linear_textcalc_valid_only | 22 | 14 | 26 | 15 |
| linear_textcalc_weighted | 21 | 13 | 26 | 15 |
| mlp_valid_only | 19 | 22 | 0 | 0 |
| mlp_weighted | 19 | 21 | 1 | 0 |
| context_valid_only | 21 | 26 | 13 | 15 |
| context_weighted | 21 | 23 | 13 | 12 |
| context_textcalc_valid_only | 26 | 23 | 22 | 16 |
| context_textcalc_weighted | 26 | 22 | 22 | 15 |

| 方法 | 分歧题正确/355 | 平票正确/88 | 唯一最高票正确/710 |
|---|---:|---:|---:|
| previous_valid_only | 290 | 65 | 668 |
| previous_weighted | 291 | 65 | 669 |
| linear_control_valid_only | 290 | 65 | 668 |
| linear_control_weighted | 291 | 65 | 669 |
| linear_text_valid_only | 300 | 70 | 673 |
| linear_text_weighted | 303 | 70 | 676 |
| linear_calc_valid_only | 292 | 67 | 668 |
| linear_calc_weighted | 298 | 67 | 674 |
| linear_textcalc_valid_only | 299 | 68 | 674 |
| linear_textcalc_weighted | 299 | 68 | 674 |
| mlp_valid_only | 288 | 61 | 670 |
| mlp_weighted | 289 | 61 | 671 |
| context_valid_only | 286 | 63 | 666 |
| context_weighted | 289 | 63 | 669 |
| context_textcalc_valid_only | 294 | 65 | 672 |
| context_textcalc_weighted | 295 | 65 | 673 |

## 算式覆盖与特征解释

{
  "total_candidates": 3192,
  "candidates_with_checked_equations": 2057,
  "questions_with_checked_equations": 714,
  "candidates_with_detected_wrong_equations": 419,
  "note": "Limited arithmetic patterns; unrecognized is unknown, not wrong. This is not full reasoning verification."
}

以下为线性模型中标准化后绝对系数最大的额外特征，仅描述关联，不证明因果或推理能力。

- linear_text：answer_integer=+0.7099；has_valid_answer=+0.3990；new_number_fraction=+0.3735；number_coverage=+0.2506；answer_zero=-0.2338；answer_negative=-0.2058
- linear_calc：wrong_ratio=-0.1767；answer_matches_checked_value=+0.1591；log_unrecognized_equations=+0.1489；max_relative_error_log=+0.1185；log_wrong_equations=-0.1049；log_correct_equations=+0.0932
- linear_textcalc：answer_integer=+0.7514；new_number_fraction=+0.3641；has_valid_answer=+0.3639；number_coverage=+0.2456；answer_zero=-0.2381；wrong_ratio=-0.2138

## 不同答案分差的可靠性诊断

只分析355道答案分歧题，分差按不同答案组最高分计算；各模型独立分四组。不是校准概率，同一开发验证集上的结果不能当独立泛化证明。

| 方法 | 最低分差组 | 第二组 | 第三组 | 最高分差组 |
|---|---:|---:|---:|---:|
| linear_control_valid_only | 66.29% | 76.40% | 85.39% | 98.86% |
| linear_control_weighted | 67.42% | 74.16% | 87.64% | 98.86% |
| linear_text_valid_only | 66.29% | 82.02% | 91.01% | 98.86% |
| linear_text_weighted | 66.29% | 85.39% | 91.01% | 98.86% |
| linear_calc_valid_only | 59.55% | 84.27% | 88.76% | 96.59% |
| linear_calc_weighted | 67.42% | 80.90% | 92.13% | 95.45% |
| linear_textcalc_valid_only | 65.17% | 79.78% | 93.26% | 98.86% |
| linear_textcalc_weighted | 66.29% | 79.78% | 92.13% | 98.86% |
| mlp_valid_only | 60.67% | 80.90% | 89.89% | 93.18% |
| mlp_weighted | 61.80% | 78.65% | 92.13% | 93.18% |
| context_valid_only | 61.80% | 74.16% | 89.89% | 96.59% |
| context_weighted | 64.04% | 74.16% | 92.13% | 95.45% |
| context_textcalc_valid_only | 62.92% | 77.53% | 94.38% | 96.59% |
| context_textcalc_weighted | 65.17% | 75.28% | 95.51% | 96.59% |

## 解释边界

- context相对mlp同时增加集合结构、同答案关系、票数输入和网络参数；收益不能全部归因于某一个组件，需后续更细消融。
- 文本表面特征不等于语义推理；算式正确也不等于建模正确，算式检查还可能因表达式抽取而出现噪声。
- 单一验证划分、有限种子和持续开发选择会造成不确定性；本轮保留失败家族，不据测试成绩回头改模型。
- 一部分同题所有候选都正确，组内目标对它们没有区分梯度；本轮保持目标不变，未额外引入联合BCE。
- 本轮不引入外部数据或预训练参数，不通过ID查答案，不缓存新bank预测，推理离线且仅用输入材料。

完整训练曲线、搜索、逐题变化和哈希位于本目录。总历史分析见code/EXPERIMENT_SUMMARY.md，复现见REMAINING_EXPERIMENTS.md。

## 本轮结果分析

独立MLP的验证独立正确数731，低于线性控制733；第二种子为724。当前配置未支持用MLP替换线性模型。上下文模型729也未超过MLP，测试下降且种子复核没有提供稳定优势；这只能否定本轮实现和搜索范围，不代表所有候选比较方法无效。

线性文本特征独立评分743，较线性控制净增10题；固定融合746，较旧融合净增12题（修正22、破坏10）。收益同时覆盖平票组（65→70）和唯一最高票组（669→676）。答案分歧子集291→303，即81.97%→85.35%。

线性算式特征独立评分735，固定融合741，提供较小收益；但文本+算式全部合并只有742，低于仅文本746。特征更多不保证效果更好，抽取噪声、特征关联和正则化均可能影响结果，本轮未进一步区分原因。

文本最强系数包含答案是否整数、题目数字覆盖、新数字比例等，提示模型利用了数据分布与表达线索；不能据此宣称学会数学推理。has_valid_answer在屏蔽后的可选候选间取值相同，不能直接解释为其在这些候选中决定了选择，它还可能影响训练期间其他权重。

context_textcalc相对纯context改善，但未超过线性文本方法，第二种子独立正确从737降到726，显示当前神经联合模型存在不稳定性。

当前保留简单线性文本融合方法，完整测试正确387/467；它仍未达到85%。上述具体结论对应本次固定记录，若重跑出现数值差异应以新记录核查，不根据测试成绩调整模型。
