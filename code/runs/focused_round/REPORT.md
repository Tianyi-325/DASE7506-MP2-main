# 严格对照优化实验报告

本轮围绕三个优先方向，完成43个主配置、两套新三折划分（种子101/307，共258次折内拟合）、43次全量训练重训、11个组合、2个投票单位对照，共56个冻结部署变体。
预先规则选定 **base_all_linear_l210**：验证747/798，固定测试385/467=82.4411%。
本轮匹配的归一化基线：验证747/798，测试385/467=82.4411%；原始单位投票基线：验证746/798，测试385/467=82.4411%。
所有冻结版本最高测试记录为390/467=83.5118%；此项只描述，不用于回头选模。

## 实验控制与边界

- 所有拟合只用课程训练数据。验证只在完整训练集重训后使用。全部模型、组合、选择和哈希固定后才开始测试评分。旧轮次资产和脚本保持不变。
- 两套三折评估复用了同一4755题，不是9510道独立题。OOF是开发选择数据，不宣称完整嵌套、无偏的家族选择估计；已有验证集也有多轮使用历史。
- 所有配置均使用float64全批量L-BFGS，最多100迭代/140函数评估；初始零权重，L2仅按显式对照变化。多正例组内目标不一定全局凸，不能保证全局最优。
- 所有主配置和组合的分数均除以相应拟合训练题的题内中心化标准差，再固定加0.25票数奖励。归一化基线是匹配参照，原始单位基线单独记录，消除先前缺少投票单位对照的问题。
- 预先晋级要求：两套OOF平均至少净增8题、每套非负、6折至少4折净增、最差折不低于-6题，验证不低于匹配基线。合格者优先按平均OOF、最差种子、验证、较少参数排名；否则保留基线。
- 这些是工程筛选门槛，不是显著性检验。bootstrap按题重采样、合并同题两次正确性的平均差，区间为未校正多重搜索的探索结果。
- 基础特征是1024维向量+22项原文本；完整特征是向量+50项标量。窄格式块移除9项，宽块移除13项；宽块还包含数字与运算符计数，不能都称作纯格式。
- 加性模型均包含同样保留的线性项，之后分别加训练分位点hinge、6个指定交互或两者。派生特征也用训练统计标准化。本轮不是前轮未标准化GAM的直接复刻。
- 首批训练后、测试前追加8个orth_hinges/orth_both对照：在每个源标量上合并重复结点，减去hinge对该源标量的仿射拟合，删除残差近零的列，再标准化。此举排除二值hinge仅重复线性项的情况；不宣称对所有其他变量全局正交。追加原因与已见数据记录在plan-amendment.json，原计划保留。

## 损失分母负对照

全训练题4755；非全对题2513；至少两个可解析答案的分歧题2114。除明确的hard_prep_mean外，预处理都共享对应训练折的所有输入，以隔离损失变化。
解析损失和梯度检查确认：保持原分母时，删去全对题完全不改变目标；屏蔽不可解析候选后，只保留分歧题并保持分母也完全等价。若改成仅对保留题取均值，就改变了数据项相对L2的强度。
理论等价不要求有限预算优化结果逐比特相同；解析检查见objective-controls.json，数值解差异见numerical-equivalence.json。

## 43个主配置：统一归一化单位＋0.25投票

| 配置 | 两套OOF正确/4755 | 相对基线净增 | 验证/798 | 固定测试/467 | 测试acc | 晋级 |
|---|---|---|---:|---:|---:|---|
| full_all_linear_l210 | [4362, 4356] | [7, 0] | 745 | 388 | 83.08% | 否 |
| full_all_linear_l220 | [4354, 4364] | [-1, 8] | 744 | 381 | 81.58% | 否 |
| full_all_hinges_l210 | [4358, 4367] | [3, 11] | 743 | 383 | 82.01% | 否 |
| full_all_hinges_l220 | [4352, 4368] | [-3, 12] | 745 | 381 | 81.58% | 否 |
| full_all_interactions_l210 | [4360, 4357] | [5, 1] | 746 | 387 | 82.87% | 否 |
| full_all_interactions_l220 | [4357, 4358] | [2, 2] | 745 | 381 | 81.58% | 否 |
| full_all_both_l210 | [4363, 4368] | [8, 12] | 745 | 386 | 82.66% | 否 |
| full_all_both_l220 | [4349, 4368] | [-6, 12] | 746 | 382 | 81.80% | 否 |
| full_broad_linear_l210 | [4360, 4357] | [5, 1] | 745 | 389 | 83.30% | 否 |
| full_broad_linear_l220 | [4356, 4362] | [1, 6] | 744 | 382 | 81.80% | 否 |
| full_broad_hinges_l210 | [4361, 4368] | [6, 12] | 744 | 383 | 82.01% | 否 |
| full_broad_hinges_l220 | [4355, 4368] | [0, 12] | 745 | 385 | 82.44% | 否 |
| full_broad_interactions_l210 | [4355, 4358] | [0, 2] | 745 | 387 | 82.87% | 否 |
| full_broad_interactions_l220 | [4359, 4364] | [4, 8] | 745 | 382 | 81.80% | 否 |
| full_broad_both_l210 | [4353, 4363] | [-2, 7] | 747 | 386 | 82.66% | 否 |
| full_broad_both_l220 | [4355, 4364] | [0, 8] | 746 | 383 | 82.01% | 否 |
| base_all_linear_l210 | [4355, 4356] | [0, 0] | 747 | 385 | 82.44% | 否 |
| base_narrow_linear_l210 | [4355, 4360] | [0, 4] | 749 | 383 | 82.01% | 否 |
| base_broad_linear_l210 | [4352, 4365] | [-3, 9] | 748 | 384 | 82.23% | 否 |
| base_all_linear_l220 | [4347, 4352] | [-8, -4] | 745 | 380 | 81.37% | 否 |
| full_narrow_linear_l210 | [4357, 4363] | [2, 7] | 747 | 390 | 83.51% | 否 |
| base_all_informative_full | [4355, 4356] | [0, 0] | 747 | 385 | 82.44% | 否 |
| base_all_informative_mean | [4344, 4361] | [-11, 5] | 748 | 386 | 82.66% | 否 |
| base_all_hard_full | [4354, 4355] | [-1, -1] | 747 | 388 | 83.08% | 否 |
| base_all_hard_mean | [4341, 4361] | [-14, 5] | 746 | 385 | 82.44% | 否 |
| base_all_hard_mask_full | [4352, 4354] | [-3, -2] | 749 | 386 | 82.66% | 否 |
| base_all_all_mask_full | [4352, 4354] | [-3, -2] | 749 | 386 | 82.66% | 否 |
| base_all_hard_prep_mean | [4343, 4358] | [-12, 2] | 747 | 386 | 82.66% | 否 |
| full_broad_informative_full | [4360, 4357] | [5, 1] | 745 | 389 | 83.30% | 否 |
| full_broad_informative_mean | [4368, 4358] | [13, 2] | 746 | 387 | 82.87% | 否 |
| full_broad_hard_full | [4362, 4362] | [7, 6] | 747 | 390 | 83.51% | 否 |
| full_broad_hard_mean | [4365, 4352] | [10, -4] | 745 | 387 | 82.87% | 否 |
| full_broad_hard_mask_full | [4364, 4355] | [9, -1] | 746 | 390 | 83.51% | 否 |
| full_broad_all_mask_full | [4364, 4355] | [9, -1] | 746 | 390 | 83.51% | 否 |
| full_broad_hard_prep_mean | [4367, 4356] | [12, 0] | 745 | 387 | 82.87% | 否 |
| full_all_orth_hinges_l210 | [4350, 4366] | [-5, 10] | 744 | 382 | 81.80% | 否 |
| full_all_orth_hinges_l220 | [4347, 4360] | [-8, 4] | 742 | 382 | 81.80% | 否 |
| full_all_orth_both_l210 | [4350, 4361] | [-5, 5] | 743 | 383 | 82.01% | 否 |
| full_all_orth_both_l220 | [4347, 4366] | [-8, 10] | 741 | 381 | 81.58% | 否 |
| full_broad_orth_hinges_l210 | [4353, 4371] | [-2, 15] | 744 | 385 | 82.44% | 否 |
| full_broad_orth_hinges_l220 | [4345, 4358] | [-10, 2] | 744 | 383 | 82.01% | 否 |
| full_broad_orth_both_l210 | [4353, 4362] | [-2, 6] | 744 | 385 | 82.44% | 否 |
| full_broad_orth_both_l220 | [4347, 4369] | [-8, 13] | 744 | 384 | 82.23% | 否 |

## 匹配消融：改变相对控制的净变化

| 对照项 | 控制 | 改变 | OOF两套净增 | 验证净增 | 固定测试净变化 |
|---|---|---|---|---:|---:|
| style_base_narrow | base_all_linear_l210 | base_narrow_linear_l210 | [0, 4] | +2 | -2 |
| style_base_broad | base_all_linear_l210 | base_broad_linear_l210 | [-3, 9] | +1 | -1 |
| style_full_narrow | full_all_linear_l210 | full_narrow_linear_l210 | [-5, 7] | +2 | +2 |
| style_full_broad | full_all_linear_l210 | full_broad_linear_l210 | [-2, 1] | +0 | +1 |
| basis_all_10_hinges | full_all_linear_l210 | full_all_hinges_l210 | [-4, 11] | -2 | -5 |
| basis_all_10_interactions | full_all_linear_l210 | full_all_interactions_l210 | [-2, 1] | +1 | -1 |
| basis_all_10_both | full_all_linear_l210 | full_all_both_l210 | [1, 12] | +0 | -2 |
| basis_all_10_orth_hinges | full_all_linear_l210 | full_all_orth_hinges_l210 | [-12, 10] | -1 | -6 |
| basis_all_10_orth_both | full_all_linear_l210 | full_all_orth_both_l210 | [-12, 5] | -2 | -5 |
| basis_all_20_hinges | full_all_linear_l220 | full_all_hinges_l220 | [-2, 4] | +1 | +0 |
| basis_all_20_interactions | full_all_linear_l220 | full_all_interactions_l220 | [3, -6] | +1 | +0 |
| basis_all_20_both | full_all_linear_l220 | full_all_both_l220 | [-5, 4] | +2 | +1 |
| basis_all_20_orth_hinges | full_all_linear_l220 | full_all_orth_hinges_l220 | [-7, -4] | -2 | +1 |
| basis_all_20_orth_both | full_all_linear_l220 | full_all_orth_both_l220 | [-7, 2] | -3 | +0 |
| basis_broad_10_hinges | full_broad_linear_l210 | full_broad_hinges_l210 | [1, 11] | -1 | -6 |
| basis_broad_10_interactions | full_broad_linear_l210 | full_broad_interactions_l210 | [-5, 1] | +0 | -2 |
| basis_broad_10_both | full_broad_linear_l210 | full_broad_both_l210 | [-7, 6] | +2 | -3 |
| basis_broad_10_orth_hinges | full_broad_linear_l210 | full_broad_orth_hinges_l210 | [-7, 14] | -1 | -4 |
| basis_broad_10_orth_both | full_broad_linear_l210 | full_broad_orth_both_l210 | [-7, 5] | -1 | -4 |
| basis_broad_20_hinges | full_broad_linear_l220 | full_broad_hinges_l220 | [-1, 6] | +1 | +3 |
| basis_broad_20_interactions | full_broad_linear_l220 | full_broad_interactions_l220 | [3, 2] | +1 | +0 |
| basis_broad_20_both | full_broad_linear_l220 | full_broad_both_l220 | [-1, 2] | +2 | +1 |
| basis_broad_20_orth_hinges | full_broad_linear_l220 | full_broad_orth_hinges_l220 | [-11, -4] | +0 | +1 |
| basis_broad_20_orth_both | full_broad_linear_l220 | full_broad_orth_both_l220 | [-9, 7] | +0 | +2 |
| supervision_base_informative_full | base_all_linear_l210 | base_all_informative_full | [0, 0] | +0 | +0 |
| supervision_base_informative_mean | base_all_linear_l210 | base_all_informative_mean | [-11, 5] | +1 | +1 |
| supervision_base_hard_full | base_all_linear_l210 | base_all_hard_full | [-1, -1] | +0 | +3 |
| supervision_base_hard_mean | base_all_linear_l210 | base_all_hard_mean | [-14, 5] | -1 | +0 |
| supervision_base_hard_mask_full | base_all_linear_l210 | base_all_hard_mask_full | [-3, -2] | +2 | +1 |
| supervision_base_all_mask_full | base_all_linear_l210 | base_all_all_mask_full | [-3, -2] | +2 | +1 |
| supervision_base_hard_prep_mean | base_all_linear_l210 | base_all_hard_prep_mean | [-12, 2] | +0 | +1 |
| supervision_full_informative_full | full_broad_linear_l210 | full_broad_informative_full | [0, 0] | +0 | +0 |
| supervision_full_informative_mean | full_broad_linear_l210 | full_broad_informative_mean | [8, 1] | +1 | -2 |
| supervision_full_hard_full | full_broad_linear_l210 | full_broad_hard_full | [2, 5] | +2 | +1 |
| supervision_full_hard_mean | full_broad_linear_l210 | full_broad_hard_mean | [5, -5] | +0 | -2 |
| supervision_full_hard_mask_full | full_broad_linear_l210 | full_broad_hard_mask_full | [4, -2] | +1 | +1 |
| supervision_full_all_mask_full | full_broad_linear_l210 | full_broad_all_mask_full | [4, -2] | +1 | +1 |
| supervision_full_hard_prep_mean | full_broad_linear_l210 | full_broad_hard_prep_mean | [7, -1] | +0 | -2 |

## 11个组合与单位控制

代表成员只按训练OOF选出：{'hard': 'full_broad_hard_full', 'nostyle': 'full_broad_linear_l220', 'additive': 'full_all_both_l210'}。测试不参与选择。

| 名称 | 组成 | 两套OOF净增 | 六折净增 | 验证/798 | 测试/467 | 晋级 |
|---|---|---|---|---:|---:|---|
| mix1_50 | [('base_all_linear_l210', 0.5), ('full_broad_hard_full', 0.5)] | [0, 9] | [0, 4, -4, 3, -1, 7] | 748 | 388 | 否 |
| mix1_75 | [('base_all_linear_l210', 0.75), ('full_broad_hard_full', 0.25)] | [1, 2] | [2, 3, -4, 2, -2, 2] | 747 | 386 | 否 |
| mix2_50 | [('base_all_linear_l210', 0.5), ('full_broad_linear_l220', 0.5)] | [-4, 2] | [-6, 4, -2, 2, -3, 3] | 746 | 383 | 否 |
| mix2_75 | [('base_all_linear_l210', 0.75), ('full_broad_linear_l220', 0.25)] | [-2, 3] | [1, -1, -2, 1, 0, 2] | 748 | 383 | 否 |
| mix3_50 | [('base_all_linear_l210', 0.5), ('full_all_both_l210', 0.5)] | [0, 9] | [3, 2, -5, 1, 0, 8] | 749 | 386 | 否 |
| mix3_75 | [('base_all_linear_l210', 0.75), ('full_all_both_l210', 0.25)] | [6, 5] | [2, 5, -1, 0, 2, 3] | 749 | 383 | 否 |
| mix4_50 | [('full_broad_hard_full', 0.5), ('full_all_both_l210', 0.5)] | [3, 7] | [-1, 7, -3, 2, -4, 9] | 745 | 386 | 否 |
| mix4_75 | [('full_broad_hard_full', 0.75), ('full_all_both_l210', 0.25)] | [2, 5] | [0, 2, 0, 3, -3, 5] | 747 | 387 | 否 |
| mix5_50 | [('full_broad_linear_l220', 0.5), ('full_all_both_l210', 0.5)] | [-3, 9] | [-3, 3, -3, 2, -3, 10] | 746 | 382 | 否 |
| mix5_75 | [('full_broad_linear_l220', 0.75), ('full_all_both_l210', 0.25)] | [0, 3] | [-1, 2, -1, 3, -7, 7] | 743 | 380 | 否 |
| triple | [('base_all_linear_l210', 0.5), ('full_broad_hard_full', 0.25), ('full_all_both_l210', 0.25)] | [-3, 7] | [1, 1, -5, 1, -1, 7] | 749 | 387 | 否 |
| baseline_native_vote | [('base_all_linear_l210', 1.0)] | [-5, -4] | [-3, -1, -1, 1, -4, -1] | 746 | 385 | 否 |
| baseline_normalized_plain | [('base_all_linear_l210', 1.0)] | [-21, -25] | [-7, -6, -8, -12, -5, -8] | 742 | 385 | 否 |

## 去重与去线性成分的分段特征审计

| 配置 | 原始分位点列 | 保留非线性列 | 其中二值源列 |
|---|---:|---:|---:|
| full_all_orth_hinges_l210 | 200 | 64 | 0 |
| full_all_orth_hinges_l220 | 200 | 64 | 0 |
| full_all_orth_both_l210 | 200 | 64 | 0 |
| full_all_orth_both_l220 | 200 | 64 | 0 |
| full_broad_orth_hinges_l210 | 148 | 30 | 0 |
| full_broad_orth_hinges_l220 | 148 | 30 | 0 |
| full_broad_orth_both_l210 | 148 | 30 | 0 |
| full_broad_orth_both_l220 | 148 | 30 | 0 |

## 选定模型的证据与分歧题

选定模型的完整比较记录：

~~~json
{
  "definition": {
    "members": [
      "base_all_linear_l210"
    ],
    "weights": [
      1.0
    ],
    "normalized": true,
    "alpha": 0.25,
    "selectable": true
  },
  "oof_correct_by_seed": {
    "101": 4355,
    "307": 4356
  },
  "mean_oof_correct": 4355.5,
  "seed_gains": [
    0,
    0
  ],
  "fold_gains": [
    0,
    0,
    0,
    0,
    0,
    0
  ],
  "cv_gate": false,
  "eligible": false,
  "validation_correct": 747,
  "validation_gain": 0,
  "oof_vs_baseline": {
    "mean_delta_questions": 0.0,
    "delta_pp": 0.0,
    "bootstrap_95_pp": [
      0.0,
      0.0
    ],
    "note": "question-paired exploratory interval; unadjusted model search and overlapping CV fits"
  },
  "validation_vs_baseline": {
    "mean_delta_questions": 0.0,
    "delta_pp": 0.0,
    "bootstrap_95_pp": [
      0.0,
      0.0
    ],
    "note": "question-paired exploratory interval; unadjusted model search and overlapping CV fits"
  },
  "parameters": 1046
}
~~~

| 子集 | 题数 | 匹配基线正确 | 选定模型正确 |
|---|---:|---:|---:|
| all | 798 | 747 | 747 |
| disagreement | 355 | 304 | 304 |
| one_correct | 117 | 75 | 75 |

只有一种可解析答案的题，在屏蔽无效候选后必选中正确数值。因此只改为报告分歧题准确率，不会改变这些方法的全体验证排名；它改善解释而不是凭空提升模型。

## 本轮主要结论

- 本轮训练内平均OOF最高主配置是full_all_both_l210；与匹配基线相比，两套净变化[8, 12]。验证745题；测试仅作冻结版本记录。
- 按规则选定版本的固定测试较归一化基线净变化+0题，较原始单位基线+0题。
- 本轮没有新配置通过全部晋级门槛，因此保留匹配基线；最高固定测试记录390/467，没有超过历史391/467，也未达到85%。门槛是事先设定的保守规则，本轮结果不能证明门槛本身最优。
- 去格式的独立贡献较弱：完整特征移除窄块相对同特征基线的两套OOF净变化为[-5,+7]，移除宽块为[-2,+1]。不能把此前相对基础模型的提升全部归因于去格式，也不能断言格式一概有害。
- 完整特征＋宽格式移除＋仅分歧题损失（保留原分母）相对基础匹配基线两套OOF净增[7,6]，验证747题持平；相对同特征的全部题训练仅净增[2,5]。这是小幅候选信号，未达到平均8题门槛，不因测试390题事后晋级。
- 基础特征仅改为分歧题训练，OOF反而为[-1,-1]。监督组织的效果依赖特征表示，不能将只训练难题当作通用提升。
- 非线性并未给出可靠改进：加性组合的OOF领先未迁移到验证；去掉仿射/重复列后，完整标量分段列由200降至64，宽去格式由148降至30，保留列中没有二值源。收益可能部分涉及重参数化/正则化，不能据此声称数学推理能力增强。
- 删除全对题并对保留题取均值，等价于在原全题数据项下把L2从0.01降到0.01*(2513/4755)≈0.005285（折内比例相应变化）；其变化不是新监督信息。固定分母版本数值权重最大差约6.2e-12，验证与测试计数均相同。
- 11个组合没有获得足够训练内与验证联合证据。后续更值得引入题目条件/目标量对齐及候选差异信息，而非继续扩大轮数或权重网格。
- 逐项对照应同时检查两套OOF和外部验证；测试行不可用于重新选择正则化、训练题型、特征或融合权重。
- 本轮每个方法只是有限预算验证，不能将未获提升等同于整个方法家族无效。旧版最高测试391/467是历史固定版本记录，不是本轮选择目标。

## 成本、合规与复现

- 首批与追加训练墙钟合计476.2秒，记录的301次主拟合合计426.4秒。
- 硬件：12th Gen Intel(R) Core(TM) i9-12900H；四线程CPU训练与推理。最大单部署资产92946字节，最大完整测试预测＋独立评分1.442秒。
- 56个部署变体通过NumPy推理、空/单/七题输入、任意ID、候选重排分数等变性、不可解析回退检查；全部本机限额通过：True。
- 官方数据、解析器、评分器未修改，无外部数据、预训练权重、新LLM生成或API。参考Xeon未实测，不能宣称官方CPU资格已认证。
- 推理资产没有训练ID、标签或预测缓存。实验目录含训练记录，不是一个部署包；提交时只提供对应的完整model_bundle。

## 完整资源表

| 方法 | 测试acc | 完整测试秒 | 资产字节 |
|---|---:|---:|---:|
| full_all_linear_l210 | 83.0835% | 1.077 | 28852 |
| full_all_linear_l220 | 81.5846% | 1.079 | 28852 |
| full_all_hinges_l210 | 82.0128% | 1.169 | 36008 |
| full_all_hinges_l220 | 81.5846% | 1.133 | 36008 |
| full_all_interactions_l210 | 82.8694% | 1.241 | 29516 |
| full_all_interactions_l220 | 81.5846% | 1.350 | 29515 |
| full_all_both_l210 | 82.6552% | 1.150 | 36150 |
| full_all_both_l220 | 81.7987% | 1.122 | 36149 |
| full_broad_linear_l210 | 83.2976% | 1.189 | 28646 |
| full_broad_linear_l220 | 81.7987% | 1.114 | 28646 |
| full_broad_hinges_l210 | 82.0128% | 1.152 | 34138 |
| full_broad_hinges_l220 | 82.4411% | 1.349 | 34138 |
| full_broad_interactions_l210 | 82.8694% | 1.222 | 29310 |
| full_broad_interactions_l220 | 81.7987% | 1.097 | 29309 |
| full_broad_both_l210 | 82.6552% | 1.137 | 34280 |
| full_broad_both_l220 | 82.0128% | 1.167 | 34280 |
| base_all_linear_l210 | 82.4411% | 1.221 | 28404 |
| base_narrow_linear_l210 | 82.0128% | 1.302 | 28262 |
| base_broad_linear_l210 | 82.2270% | 1.196 | 28198 |
| base_all_linear_l220 | 81.3704% | 1.314 | 28403 |
| full_narrow_linear_l210 | 83.5118% | 1.273 | 28711 |
| base_all_informative_full | 82.4411% | 1.096 | 28417 |
| base_all_informative_mean | 82.6552% | 1.326 | 28417 |
| base_all_hard_full | 83.0835% | 1.098 | 28410 |
| base_all_hard_mean | 82.4411% | 1.157 | 28410 |
| base_all_hard_mask_full | 82.6552% | 1.061 | 28415 |
| base_all_all_mask_full | 82.6552% | 1.155 | 28414 |
| base_all_hard_prep_mean | 82.6552% | 1.122 | 28415 |
| full_broad_informative_full | 83.2976% | 1.267 | 28659 |
| full_broad_informative_mean | 82.8694% | 1.108 | 28659 |
| full_broad_hard_full | 83.5118% | 1.167 | 28652 |
| full_broad_hard_mean | 82.8694% | 1.099 | 28652 |
| full_broad_hard_mask_full | 83.5118% | 1.121 | 28656 |
| full_broad_all_mask_full | 83.5118% | 1.120 | 28656 |
| full_broad_hard_prep_mean | 82.8694% | 1.258 | 28657 |
| full_all_orth_hinges_l210 | 81.7987% | 1.237 | 33975 |
| full_all_orth_hinges_l220 | 81.7987% | 1.166 | 33975 |
| full_all_orth_both_l210 | 82.0128% | 1.275 | 34117 |
| full_all_orth_both_l220 | 81.5846% | 1.194 | 34116 |
| full_broad_orth_hinges_l210 | 82.4411% | 1.369 | 31865 |
| full_broad_orth_hinges_l220 | 82.0128% | 1.157 | 31865 |
| full_broad_orth_both_l210 | 82.4411% | 1.188 | 32007 |
| full_broad_orth_both_l220 | 82.2270% | 1.124 | 32007 |
| mix1_50 | 83.0835% | 1.160 | 56925 |
| mix1_75 | 82.6552% | 1.134 | 56927 |
| mix2_50 | 82.0128% | 1.327 | 56919 |
| mix2_75 | 82.0128% | 1.139 | 56921 |
| mix3_50 | 82.6552% | 1.141 | 64423 |
| mix3_75 | 82.0128% | 1.258 | 64425 |
| mix4_50 | 82.6552% | 1.247 | 64671 |
| mix4_75 | 82.8694% | 1.117 | 64673 |
| mix5_50 | 81.7987% | 1.442 | 64665 |
| mix5_75 | 81.3704% | 1.144 | 64667 |
| triple | 82.8694% | 1.157 | 92946 |
| baseline_native_vote | 82.4411% | 1.104 | 28389 |
| baseline_normalized_plain | 82.4411% | 1.119 | 28403 |
