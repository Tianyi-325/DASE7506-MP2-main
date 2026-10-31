# 第十轮：数学证据与旧模型融合

41主配置、两套三折+全量287次主配置拟合、21次基础拟合、13组合，共54冻结版本，均独立官方评分。

预定规则选择：no_style_evidence_90。验证751/798；固定测试389/467=83.2976%。
旧参照：no_style；晋级=True；通过门槛=['no_style_refit_semantic_r3', 'no_style_refit_semantic_r10', 'no_style_refit_verify_r3', 'no_style_refit_verify_r10', 'no_style_refit_both_r3', 'no_style_refit_both_r10', 'no_style_refit_relative_r10', 'no_style_residual_semantic_r3', 'no_style_residual_semantic_r10', 'no_style_residual_verify_r3', 'no_style_residual_verify_r10', 'no_style_residual_both_r3', 'no_style_residual_both_r10', 'no_style_residual_relative_r3', 'no_style_residual_relative_r10', 'joint_refit_both_r3', 'joint_refit_relative_r3', 'joint_refit_relative_r10', 'joint_residual_relative_r3', 'no_style_gated_5', 'no_style_gated_10', 'joint_newNS_50', 'NS_newjoint_50', 'NS_newjoint_75', 'new_pair_50', 'new_pair_75', 'no_style_evidence_90', 'new_triple']。测试在选模、权重和源码冻结后运行，不回流选型。

训练OOF选定组件：{"enhanced_no_style": "no_style_residual_relative_r3", "enhanced_joint": "joint_residual_relative_r3", "evidence_only": "evidence_only_relative"}。

## 核心对照

| 方法 | 两套OOF正确数/4755 | 相对参照种子增益 | 验证/798 | 固定测试/467 |
|---|---|---|---:|---:|
| no_style | [4379, 4367] | [0, 0] | 747 | 390 (83.5118%) |
| joint | [4364, 4353] | [-15, -14] | 746 | 391 (83.7259%) |
| feature_selection | [4376, 4367] | [-3, 0] | 746 | 390 (83.5118%) |
| old_pair | [4377, 4357] | [-2, -10] | 745 | 389 (83.2976%) |
| old_triple | [4381, 4353] | [2, -14] | 746 | 388 (83.0835%) |
| no_style_refit_semantic_r3 | [4393, 4380] | [14, 13] | 750 | 385 (82.4411%) |
| no_style_refit_verify_r3 | [4389, 4384] | [10, 17] | 749 | 392 (83.9400%) |
| no_style_residual_both_r3 | [4393, 4388] | [14, 21] | 748 | 390 (83.5118%) |
| no_style_residual_relative_r3 | [4401, 4394] | [22, 27] | 750 | 398 (85.2248%) |
| joint_residual_relative_r3 | [4388, 4393] | [9, 26] | 751 | 401 (85.8672%) |
| no_style_evidence_90 | [4404, 4399] | [25, 32] | 751 | 389 (83.2976%) |
| joint_newNS_50 | [4391, 4373] | [12, 6] | 748 | 395 (84.5824%) |
| joint_newNS_75 | [4382, 4365] | [3, -2] | 742 | 392 (83.9400%) |
| NS_newjoint_50 | [4392, 4383] | [13, 16] | 749 | 396 (84.7966%) |
| NS_newjoint_75 | [4387, 4378] | [8, 11] | 749 | 392 (83.9400%) |
| new_pair_50 | [4394, 4396] | [15, 29] | 750 | 397 (85.0107%) |
| new_pair_75 | [4393, 4395] | [14, 28] | 750 | 399 (85.4390%) |
| joint_evidence_90 | [4383, 4365] | [4, -2] | 745 | 393 (84.1542%) |
| joint_evidence_75 | [4383, 4388] | [4, 21] | 745 | 391 (83.7259%) |
| no_style_evidence_75 | [4392, 4399] | [13, 32] | 746 | 389 (83.2976%) |
| new_triple | [4391, 4393] | [12, 26] | 749 | 395 (84.5824%) |

模块代表按训练OOF选择，semantic=条件/目标，verify=局部检验，both=合并，relative=合并加相对证据。重训、固定主干残差和低分差限幅门控均有匹配参照。

## 结论的证据边界

晋级预设：平均OOF增益>=5题，两种子非负，六折至少四折正增益，最差折>=-6，验证不退步。所有逐折增益、匹配参照和修复/破坏见selection.json。此门槛不能视为显著性证明；OOF反复选模、复用验证集仍有选择偏差。
描述性bootstrap按题重采样并保留同题两套预测，见descriptive-bootstrap.json；没有校正搜索选择，不作正式置信区间解释。
本轮最高验证记录joint_refit_relative_r10：755/798；最高固定测试记录joint_residual_relative_r3：401/467。

## 原验证错题修复

| 方法 | 修复原51题 | 修复原36共同错题 | 语义类/41 | 算术类/7 |
|---|---:|---:|---:|---:|
| no_style_evidence_90 | 8 | 1 | 3 | 5 |
| no_style_refit_semantic_r3 | 8 | 1 | 6 | 2 |
| no_style_refit_verify_r3 | 6 | 0 | 3 | 3 |
| no_style_residual_both_r3 | 7 | 2 | 3 | 4 |
| no_style_residual_relative_r3 | 9 | 3 | 5 | 4 |

修复统计属于已有开发集分析；也必须考虑破坏原正确题。全部类别与方法见residual-validation-results.json，原文与切换证据见validation-case-studies.json。人工类别边界有重叠，仍以官方最终数值计分。

覆盖率是可计算特征的覆盖，不是逻辑检测准确率；最终答案标签不能验证每一步推理。有限语义规则不能解决所有对象、时间线、单位与指代问题。未知不等于正确，告警不等于最终错误。

覆盖记录：
{
  "train": {
    "questions": 4755,
    "candidates": 19020,
    "candidate_numeric_checked": 16541,
    "candidate_numeric_wrong_flagged": 2029,
    "candidate_unit_checked": 782,
    "candidate_unit_wrong_flagged": 290,
    "candidate_box_official_mismatch": 32,
    "candidate_terminal_official_mismatch": 677,
    "question_target_unit_known": 2446,
    "question_salient_factor_known": 3603,
    "nonconstant_features": [
      28,
      21,
      20
    ],
    "no_style_gates": {
      "0.5": 488,
      "1.0": 910
    },
    "joint_gates": {
      "0.5": 330,
      "1.0": 624
    }
  },
  "validation": {
    "questions": 798,
    "candidates": 3192,
    "candidate_numeric_checked": 2791,
    "candidate_numeric_wrong_flagged": 361,
    "candidate_unit_checked": 130,
    "candidate_unit_wrong_flagged": 43,
    "candidate_box_official_mismatch": 8,
    "candidate_terminal_official_mismatch": 111,
    "question_target_unit_known": 415,
    "question_salient_factor_known": 567,
    "nonconstant_features": [
      26,
      21,
      20
    ]
  }
}

## 资源与完整性

环境：Python 3.12.14，NumPy 2.5.3，PyTorch 2.7.1+cu126，Windows i9-12900H，CPU四线程，无GPU。
训练/冻结墙钟471.14秒；拟合计时合计395.94秒（含基础拟合与控制导出，并非完整搜索墙钟）。
最大推理资产56176字节；最慢完整测试新预测+独立评分3.418秒；参考Xeon未实测。
所选模型资产18385字节，完整测试时间3.140秒。
原数据hash、冻结源码/资产、三旧参照逐题复现、0/1/7题、候选重排、未知ID、无效候选fallback、NumPy推理和Torch导出一致性均通过。另验证混合尺度与跨货币表达式跳过。

## 全部固定版本

| 变体 | 两套OOF正确数 | 增益 | 验证/798 | 固定测试/467 |
|---|---|---|---:|---:|
| no_style | [4379, 4367] | [0, 0] | 747 | 390 (83.5118%) |
| joint | [4364, 4353] | [-15, -14] | 746 | 391 (83.7259%) |
| feature_selection | [4376, 4367] | [-3, 0] | 746 | 390 (83.5118%) |
| no_style_refit_semantic_r3 | [4393, 4380] | [14, 13] | 750 | 385 (82.4411%) |
| no_style_refit_semantic_r10 | [4393, 4380] | [14, 13] | 749 | 389 (83.2976%) |
| no_style_refit_verify_r3 | [4389, 4384] | [10, 17] | 749 | 392 (83.9400%) |
| no_style_refit_verify_r10 | [4387, 4377] | [8, 10] | 747 | 389 (83.2976%) |
| no_style_refit_both_r3 | [4394, 4387] | [15, 20] | 748 | 389 (83.2976%) |
| no_style_refit_both_r10 | [4392, 4387] | [13, 20] | 750 | 386 (82.6552%) |
| no_style_refit_relative_r3 | [4390, 4393] | [11, 26] | 749 | 393 (84.1542%) |
| no_style_refit_relative_r10 | [4391, 4390] | [12, 23] | 752 | 392 (83.9400%) |
| no_style_residual_semantic_r3 | [4387, 4383] | [8, 16] | 748 | 388 (83.0835%) |
| no_style_residual_semantic_r10 | [4386, 4382] | [7, 15] | 747 | 388 (83.0835%) |
| no_style_residual_verify_r3 | [4386, 4378] | [7, 11] | 748 | 390 (83.5118%) |
| no_style_residual_verify_r10 | [4385, 4376] | [6, 9] | 747 | 390 (83.5118%) |
| no_style_residual_both_r3 | [4393, 4388] | [14, 21] | 748 | 390 (83.5118%) |
| no_style_residual_both_r10 | [4390, 4387] | [11, 20] | 747 | 388 (83.0835%) |
| no_style_residual_relative_r3 | [4401, 4394] | [22, 27] | 750 | 398 (85.2248%) |
| no_style_residual_relative_r10 | [4397, 4391] | [18, 24] | 749 | 395 (84.5824%) |
| joint_refit_semantic_r3 | [4384, 4361] | [5, -6] | 746 | 391 (83.7259%) |
| joint_refit_semantic_r10 | [4381, 4366] | [2, -1] | 746 | 390 (83.5118%) |
| joint_refit_verify_r3 | [4376, 4371] | [-3, 4] | 745 | 394 (84.3683%) |
| joint_refit_verify_r10 | [4376, 4362] | [-3, -5] | 745 | 392 (83.9400%) |
| joint_refit_both_r3 | [4387, 4382] | [8, 15] | 748 | 391 (83.7259%) |
| joint_refit_both_r10 | [4382, 4369] | [3, 2] | 748 | 391 (83.7259%) |
| joint_refit_relative_r3 | [4389, 4392] | [10, 25] | 751 | 396 (84.7966%) |
| joint_refit_relative_r10 | [4392, 4384] | [13, 17] | 755 | 394 (84.3683%) |
| joint_residual_semantic_r3 | [4378, 4375] | [-1, 8] | 748 | 394 (84.3683%) |
| joint_residual_semantic_r10 | [4381, 4367] | [2, 0] | 747 | 394 (84.3683%) |
| joint_residual_verify_r3 | [4380, 4364] | [1, -3] | 745 | 392 (83.9400%) |
| joint_residual_verify_r10 | [4377, 4362] | [-2, -5] | 746 | 391 (83.7259%) |
| joint_residual_both_r3 | [4382, 4373] | [3, 6] | 747 | 394 (84.3683%) |
| joint_residual_both_r10 | [4387, 4373] | [8, 6] | 744 | 393 (84.1542%) |
| joint_residual_relative_r3 | [4388, 4393] | [9, 26] | 751 | 401 (85.8672%) |
| joint_residual_relative_r10 | [4382, 4385] | [3, 18] | 749 | 397 (85.0107%) |
| no_style_gated_5 | [4394, 4375] | [15, 8] | 750 | 390 (83.5118%) |
| no_style_gated_10 | [4396, 4380] | [17, 13] | 749 | 393 (84.1542%) |
| joint_gated_5 | [4378, 4358] | [-1, -9] | 747 | 392 (83.9400%) |
| joint_gated_10 | [4374, 4369] | [-5, 2] | 746 | 395 (84.5824%) |
| evidence_only_both | [4161, 4163] | [-218, -204] | 703 | 337 (72.1627%) |
| evidence_only_relative | [4189, 4193] | [-190, -174] | 703 | 348 (74.5182%) |
| old_pair | [4377, 4357] | [-2, -10] | 745 | 389 (83.2976%) |
| old_triple | [4381, 4353] | [2, -14] | 746 | 388 (83.0835%) |
| joint_newNS_50 | [4391, 4373] | [12, 6] | 748 | 395 (84.5824%) |
| joint_newNS_75 | [4382, 4365] | [3, -2] | 742 | 392 (83.9400%) |
| NS_newjoint_50 | [4392, 4383] | [13, 16] | 749 | 396 (84.7966%) |
| NS_newjoint_75 | [4387, 4378] | [8, 11] | 749 | 392 (83.9400%) |
| new_pair_50 | [4394, 4396] | [15, 29] | 750 | 397 (85.0107%) |
| new_pair_75 | [4393, 4395] | [14, 28] | 750 | 399 (85.4390%) |
| joint_evidence_90 | [4383, 4365] | [4, -2] | 745 | 393 (84.1542%) |
| joint_evidence_75 | [4383, 4388] | [4, 21] | 745 | 391 (83.7259%) |
| no_style_evidence_90 | [4404, 4399] | [25, 32] | 751 | 389 (83.2976%) |
| no_style_evidence_75 | [4392, 4399] | [13, 32] | 746 | 389 (83.2976%) |
| new_triple | [4391, 4393] | [12, 26] | 749 | 395 (84.5824%) |

## 投票单位匹配的补充控制

两个控制在主选模已冻结之后声明，仅用于归因诊断，不回流选模。保留旧单模型权重，把训练分数标准差与alpha=.125对齐新组合。没有新增拟合。

| 控制 | 两套OOF正确数 | 验证/798 | 固定测试/467 |
|---|---|---:|---:|
| normalized_no_style_control | [4381, 4370] | 747 | 389 |
| normalized_joint_control | [4372, 4346] | 744 | 389 |

主选定组合相对匹配去格式控制的OOF增益为[23, 29]；这可排查单纯分数单位/投票变化，但仍是同一开发搜索中的结果。

所选版本是否达到85%：False；本轮最高固定测试记录85.8672%，是否达到85%：True。最高记录不替代预先冻结的选择。

## 各版本完整资源记录

| 变体 | 推理资产字节 | 新测试预测+评分秒 |
|---|---:|---:|
| no_style | 15678 | 3.092 |
| joint | 19953 | 3.244 |
| feature_selection | 15695 | 2.979 |
| no_style_refit_semantic_r3 | 17001 | 2.931 |
| no_style_refit_semantic_r10 | 17000 | 3.193 |
| no_style_refit_verify_r3 | 16879 | 2.854 |
| no_style_refit_verify_r10 | 16878 | 3.331 |
| no_style_refit_both_r3 | 17437 | 3.165 |
| no_style_refit_both_r10 | 17436 | 3.373 |
| no_style_refit_relative_r3 | 17841 | 2.987 |
| no_style_refit_relative_r10 | 17840 | 3.418 |
| no_style_residual_semantic_r3 | 17116 | 2.877 |
| no_style_residual_semantic_r10 | 17115 | 3.194 |
| no_style_residual_verify_r3 | 16970 | 3.241 |
| no_style_residual_verify_r10 | 16969 | 3.111 |
| no_style_residual_both_r3 | 17640 | 2.917 |
| no_style_residual_both_r10 | 17639 | 3.052 |
| no_style_residual_relative_r3 | 18124 | 2.839 |
| no_style_residual_relative_r10 | 18123 | 3.094 |
| joint_refit_semantic_r3 | 21276 | 2.806 |
| joint_refit_semantic_r10 | 21275 | 2.911 |
| joint_refit_verify_r3 | 21154 | 2.793 |
| joint_refit_verify_r10 | 21153 | 2.921 |
| joint_refit_both_r3 | 21712 | 3.115 |
| joint_refit_both_r10 | 21711 | 2.820 |
| joint_refit_relative_r3 | 22116 | 3.235 |
| joint_refit_relative_r10 | 22115 | 2.900 |
| joint_residual_semantic_r3 | 21391 | 3.182 |
| joint_residual_semantic_r10 | 21390 | 2.833 |
| joint_residual_verify_r3 | 21245 | 3.140 |
| joint_residual_verify_r10 | 21244 | 2.977 |
| joint_residual_both_r3 | 21915 | 3.183 |
| joint_residual_both_r10 | 21914 | 2.930 |
| joint_residual_relative_r3 | 22399 | 3.047 |
| joint_residual_relative_r10 | 22398 | 2.790 |
| no_style_gated_5 | 18172 | 2.827 |
| no_style_gated_10 | 18172 | 3.074 |
| joint_gated_5 | 22447 | 2.877 |
| joint_gated_10 | 22447 | 2.856 |
| evidence_only_both | 2220 | 2.904 |
| evidence_only_relative | 2704 | 3.048 |
| old_pair | 35619 | 2.884 |
| old_triple | 51344 | 3.147 |
| joint_newNS_50 | 38065 | 2.889 |
| joint_newNS_75 | 38067 | 3.223 |
| NS_newjoint_50 | 38065 | 3.076 |
| NS_newjoint_75 | 38067 | 3.413 |
| new_pair_50 | 40511 | 3.368 |
| new_pair_75 | 40513 | 3.172 |
| joint_evidence_90 | 22661 | 3.190 |
| joint_evidence_75 | 22647 | 3.085 |
| no_style_evidence_90 | 18385 | 3.140 |
| no_style_evidence_75 | 18371 | 2.944 |
| new_triple | 56176 | 3.160 |

## 模块与自身旧主干的匹配比较

| 方向 | OOF代表 | 旧主干 | 两种子增益 | 验证修复/破坏 |
|---|---|---|---|---|
| semantic | no_style_refit_semantic_r3 | no_style | [14, 13] | 3/0 |
| verify | no_style_refit_verify_r3 | no_style | [10, 17] | 5/3 |
| both | no_style_residual_both_r3 | no_style | [14, 21] | 4/3 |
| relative | no_style_residual_relative_r3 | no_style | [22, 27] | 5/2 |

## 本轮分析结论

1. 相对证据是本轮最有一致支持的新增部分。相同去格式主干、冻结残差、L2=.03下，从both增加20维相对特征，两套OOF分别再多对8题、6题，验证748→750，固定测试390→398。相同joint主干则OOF再增6题、20题，验证747→751，固定测试394→401。这比跨主干挑最高分更能说明新增比较证据的价值。
2. 条件/目标规则有开发集信号，但泛化收益不统一。OOF代表在两套划分增14/13题、验证修复3题且无破坏，固定测试却比自身旧主干少5题。局部检验代表OOF增10/17题，验证净增2题、固定测试增2题；其作用适合软证据，不能据此宣称已实现完整数学验证。
3. 保留强主干并学习残差是有希望的用法。joint_residual_relative_r3保持旧向量主干，学习70维证据修正，验证751、测试401；去格式对应模型验证750、测试398。两者在各自主干内都由训练OOF选为增强组件；最高测试版本并非凭测试另调参数得到。
4. 组合有帮助，但成员更多并不保证更好。新双模型75/25组合固定测试399，三模型395；旧双/三组合为389/388。
5. 本轮选模存在明显不确定性。OOF最优合格组合no_style_evidence_90虽然OOF增25/32、验证751，测试389；匹配投票单位控制也是389，未看到其新增证据带来同步测试提升。最高验证755的版本测试394，也说明单一开发排名不能保证测试排名。
6. 本轮确有冻结候选超过85%，最高401/467，相比旧391净增10题；预先选定版本仍未达到85%。这两个事实应同时报告。后续研究主线可依据训练OOF与验证共同支持，集中检查相对证据残差的稳定性、规则误报和单位/实体覆盖，不应继续无依据堆叠模型。

