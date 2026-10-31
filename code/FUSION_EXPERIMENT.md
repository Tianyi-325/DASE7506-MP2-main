# 向量与投票融合：运行说明

实现与依赖：vector_vote_fusion.py 复用 vector_logistic.py 和官方 common.py；只依赖 NumPy。无需安装新包。本轮无新增训练，沿用上一轮权重。

## 环境

在 Anaconda Prompt 中：

~~~bat
conda activate mp1
cd /d E:\DASE7506-MP2-main\code
set OMP_NUM_THREADS=4
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
~~~

## 直接复现本轮推荐方法，不进行参数搜索

~~~bat
python predict.py --method vector_vote_fusion.py --checkpoint runs/vector_vote_fusion/weighted/model_bundle --split validation --output runs/vector_vote_fusion/weighted/validation-predictions.json
python score_predictions.py --split validation --predictions runs/vector_vote_fusion/weighted/validation-predictions.json --output runs/vector_vote_fusion/weighted/validation-score.json
~~~

测试集将 split 和文件名中的 validation 改为 test。三个互斥变体的模型目录分别为 valid_only/model_bundle、vote_first/model_bundle、weighted/model_bundle。

未知 audit 输入可以使用同一资产，无须重训：

~~~bat
python predict.py --method vector_vote_fusion.py --checkpoint runs/vector_vote_fusion/weighted/model_bundle --split audit --data-dir PATH_TO_AUDIT_INPUTS --output runs/audit-fusion-predictions.json
~~~

PATH_TO_AUDIT_INPUTS 需替换为实际目录。

## 重新开展完整实验并保留原记录

~~~bat
python run_fusion_experiments.py --output runs/fusion_reproduction
python report_fusion.py --output runs/fusion_reproduction
~~~

默认沿用 runs/vector_logistic/model_bundle。也可使用 --source-bundle 指定兼容的上一轮模型，但其父目录必须有上一轮 freeze.json 以校验资产。

完整流程：关键语义检查 → 只读验证集搜索8个预设系数 → 导出三种策略并冻结源码/资产哈希 → 对基线、纯向量和三种策略各自运行官方验证及测试评分 → 保存四线程CPU完整外部耗时 → 验证集分组诊断。

若只想先看验证结果，暂停在固定版本：

~~~bat
python run_fusion_experiments.py --stage select --output runs/fusion_reproduction_2
~~~

之后继续评测、报告：

~~~bat
python run_fusion_experiments.py --stage evaluate --output runs/fusion_reproduction_2
python report_fusion.py --output runs/fusion_reproduction_2
~~~

已有 freeze.json 的目录不会被参数搜索覆盖。对当前冻结版本重复评测使用 --stage evaluate，会覆盖该目录中的评测文件和计时；报告需重新运行 report_fusion.py 生成。单独预测命令也会覆盖指定输出文件。

## 文件与记录

- check_fusion.py：测试无效候选屏蔽、票数奖励、最高票限制、分数并列、分数/小数等价、全部无效及空输入。
- run_fusion_experiments.py：参数选择、固定资产、官方评测、硬件/时间、分组诊断与逐题记录。
- report_fusion.py：根据记录生成可复现中文 Markdown 报告。
- runs/vector_vote_fusion/REPORT.md：本轮报告。
- freeze.json：系数消融、固定配置、源码与资产SHA256。
- validation-selected-method.json：仅按验证结果推荐的策略。
- experiment-results.json：所有官方结果、外部计时、置信度和分组统计。
- validation-case-comparisons.json：798题逐题预测与正确性变化。
- 各策略目录下：model_bundle/、官方预测JSON、官方评分JSON、进程日志。

