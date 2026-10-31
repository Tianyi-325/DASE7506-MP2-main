# 第二轮：固定向量模型与答案投票融合

## 设计与数据使用

本轮沿用上一轮逻辑回归的全部权重，不重新训练、不增加外部数据或预训练参数。所有三种策略共用同一个 model.npz，其 SHA256 记录在 freeze.json。只依据验证集选择加权系数，并保存配置和源文件哈希后，才对固定的三个变体进行测试评分。测试结果不参与本轮系数或推荐方法选择。

1. valid_only：只屏蔽官方解析器无法解析最终答案的候选，再按原始向量 logit 选择。
2. vote_first：先保留最高票答案对应的候选，再选择向量 logit 最高的候选。
3. weighted：屏蔽不可解析候选；最终分数 = 原始向量 logit + alpha ×（同答案候选数 − 1）。这属于候选级软融合，不是概率相加；同答案候选之间仍按向量分数选择。

分数并列选择较早候选；全部不可解析时返回候选0。数值等价性完全沿用 common.parse_answer，例如0.5与1/2共享票数。未改动官方数据、解析器或评分器。

## 验证集参数搜索

预先固定8个系数，按验证题级准确率选择，相同则优先较小系数。alpha=0等价于有效性屏蔽实验。没有对其他系数进行测试集搜索。

| alpha | 验证正确数 | 验证准确率 |
|---:|---:|---:|
| 0.0 | 720/798 | 90.2256% |
| 0.125 | 721/798 | 90.3509% |
| 0.25 | 723/798 | 90.6015% |
| 0.5 | 722/798 | 90.4762% |
| 1.0 | 721/798 | 90.3509% |
| 2.0 | 712/798 | 89.2231% |
| 4.0 | 708/798 | 88.7218% |
| 8.0 | 708/798 | 88.7218% |

选定 alpha=0.25；参数搜索内部用时 0.358 秒，包含验证输入加载、原模型打分、8组规则评测与导出；不含解释器启动和导入。没有新增训练。

## 官方评测结果

| 方法 | 验证集 | 测试集 |
|---|---:|---:|
| 多数投票 | 688/798（86.2155%） | 323/467（69.1649%） |
| 纯向量 | 716/798（89.7243%） | 358/467（76.6595%） |
| 向量+有效性屏蔽 | 720/798（90.2256%） | 361/467（77.3019%） |
| 投票优先+向量解平票 | 708/798（88.7218%） | 353/467（75.5889%） |
| 向量与票数加权融合 | 723/798（90.6015%） | 369/467（79.0150%） |

本轮按验证集推荐：向量与票数加权融合。测试成绩仅描述这些已冻结变体。

## 验证集错误变化

| 新方法 | 相对纯向量修正/破坏 | 相对屏蔽后向量修正/破坏 | 相对投票修正/破坏 |
|---|---:|---:|---:|
| 向量+有效性屏蔽 | 4 / 0 | 0 / 0 | 68 / 36 |
| 投票优先+向量解平票 | 24 / 32 | 20 / 32 | 36 / 16 |
| 向量与票数加权融合 | 16 / 9 | 12 / 9 | 59 / 24 |

屏蔽规则相对纯向量修正4题且未破坏原有正确选择；这是评分协议层面的改进，不能算作向量推理能力增强。加权融合相对屏蔽后的向量修正12题、破坏9题，净增3题；收益较小，尚不能声称稳定显著。投票优先相对屏蔽向量净减12题，说明强制相信最高票会丢掉模型识别少数正确答案的能力。

| 验证分组 | 题数 | 多数投票 | 纯向量 | 有效性屏蔽 | 投票优先 | 加权融合 |
|---|---:|---:|---:|---:|---:|---:|
| all | 798 | 688（86.22%） | 716（89.72%） | 720（90.23%） | 708（88.72%） | 723（90.60%） |
| answer_disagreement | 355 | 245（69.01%） | 275（77.46%） | 277（78.03%） | 265（74.65%） | 280（78.87%） |
| tied_leaders | 88 | 38（43.18%） | 56（63.64%） | 58（65.91%） | 58（65.91%） | 58（65.91%） |
| unique_leader | 710 | 650（91.55%） | 660（92.96%） | 662（93.24%） | 650（91.55%） | 665（93.66%） |
| has_unparseable | 126 | 107（84.92%） | 102（80.95%） | 106（84.13%） | 108（85.71%） | 107（84.92%） |

最高票平票组中，三个新变体均为58/88；本轮小权重融合相对有效性屏蔽的净收益出现在唯一最高票组。票数适合作为可被模型推翻的辅助证据，而不宜作为强制决定。

## 置信度分析

本轮改用“不同可解析答案组的最高最终分数之差”，避免上一轮同答案的多个正确候选相互接近而使候选分差难以解释。仅对有至少两个合格答案组的题计算；vote_first仅在最高票答案间比较，因此它的样本为88题，与其他两种355题不同。

| 方法 | 有竞争题数 | 分差最低四分位正确率 | 第二组 | 第三组 | 最高组 |
|---|---:|---:|---:|---:|---:|
| 向量+有效性屏蔽 | 355 | 55.06% | 73.03% | 92.13% | 92.05% |
| 投票优先+向量解平票 | 88 | 45.45% | 54.55% | 81.82% | 81.82% |
| 向量与票数加权融合 | 355 | 52.81% | 77.53% | 91.01% | 94.32% |

加权融合的不同答案组分差在此验证集中与正确率呈递增关系。这是描述性证据，不是校准概率或独立泛化证明；每组约89题，且方法已用同一验证集选择。尚未据此拟合置信度阈值。

## 投票模式消融

| 可解析答案票型与有效候选数 | 题数 | 多数投票正确 | 纯向量正确 | 屏蔽正确 | 投票优先正确 | 加权融合正确 |
|---|---:|---:|---:|---:|---:|---:|
| 2-1-1;valid=4 | 88 | 54 | 62 | 62 | 54 | 66 |
| 4;valid=4 | 379 | 379 | 379 | 379 | 379 | 379 |
| 1-1-1-1;valid=4 | 20 | 5 | 11 | 11 | 11 | 11 |
| 2-1;valid=3 | 28 | 24 | 22 | 22 | 24 | 23 |
| 3;valid=3 | 50 | 50 | 49 | 50 | 50 | 50 |
| 2-2;valid=4 | 34 | 14 | 27 | 27 | 27 | 27 |
| 3-1;valid=4 | 151 | 129 | 135 | 135 | 129 | 133 |
| 1-1-1;valid=3 | 20 | 11 | 11 | 11 | 11 | 11 |
| 1-1;valid=2 | 14 | 8 | 7 | 9 | 9 | 9 |
| 1;valid=1 | 3 | 3 | 2 | 3 | 3 | 3 |
| 2;valid=2 | 11 | 11 | 11 | 11 | 11 | 11 |

## 资源

CPU：12th Gen Intel(R) Core(TM) i9-12900H；四线程，Python与NumPy版本详见 experiment-results.json。每个策略只部署自己的 model_bundle，三个目录是互斥实验变体，不是三模型集成。

| 方法 | 资产字节 | 资产MiB | 验证完整耗时 | 测试完整耗时 |
|---|---:|---:|---:|---:|
| 向量+有效性屏蔽 | 9140 | 0.008717 | 0.562 秒 | 0.434 秒 |
| 投票优先+向量解平票 | 9140 | 0.008717 | 0.502 秒 | 0.464 秒 |
| 向量与票数加权融合 | 9139 | 0.008716 | 0.515 秒 | 0.456 秒 |

计时包含新进程预测及另一个独立评分进程的启动、导入、加载、解析和官方校验；每项一次。细小时间差不能解释为稳定速度差。尚未在课程参考Xeon上验证。

## 局限与下一步

- 单一验证划分；本轮融合仅一个标量，未开展交叉验证或统计显著性检验。
- 验证集被持续用于开发，后续应控制搜索规模；若增加可训练融合器，采用训练集内交叉验证预测拟合，不用验证标签训练。
- 当前仍是手工线性票数奖励，不会识别题目语义或检查算术。下一步按原规划先研究评分器训练目标，再研究候选间比较。
- 原始logit的尺度来自固定的上一轮模型。若将来更换向量模型，alpha不能直接视为通用参数。

## 代表性验证变化（自动列举，非人工语义归因）

### 屏蔽修正

- 验证第166题：In a 50-question test with two marks for each question, Meghan learned that she scored 20 marks less than her friend Jose, who scored 40 more marks than their friend Alisson. Calculate the total score for the three in the test combined if Jose got 5 questions wrong?
  候选解析答案：[None, '210', '100', None]；正确候选：[1]；vector选择0，valid_only选择1。

- 验证第205题：In 5 years, Raven will be 4 times as old as Phoebe. If Phoebe is currently 10 years old, how old is Raven?
  候选解析答案：['55', '55', None, '55']；正确候选：[0, 1, 3]；vector选择2，valid_only选择3。

- 验证第253题：Jenny leaves her house at 8:00 with some cupcakes for her daughter's birthday party at school. She jogs to the school at 15 miles per hour. Half an hour later, her wife Anna realizes that Jenny used peanut butter frosting because she forgot one of the kids in the class had a severe peanut allergy. Jenny doesn't have her cell phone, so Anna leaves the house driving at 45 miles her hour to catch Jenny and warn her. How long does Anna spend traveling in minutes?
  候选解析答案：[None, None, '10', None]；正确候选：[2]；vector选择3，valid_only选择2。

### 融合修正

- 验证第197题：A tank contains 6000 liters of water, 2000 liters evaporated, and then 3500 liters were drained by Bob. How many liters are in the tank if it now rains for 30 minutes and every 10 minutes 350 liters of rain are added to the tank?
  候选解析答案：['1550', '500', '3550', '1550']；正确候选：[0, 3]；valid_only选择2，weighted选择0。

- 验证第225题：Caprice is taking piano lessons. Her mother pays the teacher $10 for every half-hour of teaching her daughter. If Caprice is taking one lesson per week, and the lesson lasts 1 hour, how much money would the teacher earn in 5 weeks?
  候选解析答案：['100', '150', '100', '100']；正确候选：[0, 2, 3]；valid_only选择1，weighted选择3。

- 验证第232题：Ral is twice as old as Suri. In 3 years, Suri's current age will be 16. What is Ral's current age?
  候选解析答案：['26', '26', '3', '26']；正确候选：[0, 1, 3]；valid_only选择2，weighted选择1。

### 融合破坏

- 验证第98题：A football club has a balance of $100 million. The club then sells 2 of its players at $10 million each, and buys 4 more at $15 million each. How much money is left in the club register in millions of dollars?
  候选解析答案：['20', '60', '20', '20']；正确候选：[1]；valid_only选择1，weighted选择2。

- 验证第116题：My cat's empty bowl weighs 420 grams. If I give my cat 60 grams per day and I always fill her bowl every 3 days, how much does her bowl weigh if after I ended up refilling her empty bowl she only ate 14 grams?
  候选解析答案：['434', '406', '406', '586']；正确候选：[3]；valid_only选择3，weighted选择1。

- 验证第267题：Jennifer wants to go to a museum. There is one 5 miles away from her home and one 15 miles away. If Jennifer goes to both museums on two separate days, how many miles total will she travel?
  候选解析答案：['40', '20', '20', '20']；正确候选：[0]；valid_only选择0，weighted选择1。

完整逐题变化见 validation-case-comparisons.json；全部机器可读统计见 experiment-results.json；参数、资产及源码哈希见 freeze.json。
