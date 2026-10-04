# 首版模型训练代码复查

日期：2026-10-04（Asia/Shanghai）。按requesting-code-review进行一次独立只读静态复查，没有修改源码、运行测试或重跑旧实验。

范围：models/training.py、training_workflow.py、新CLI train、pyproject依赖及test_model_training.py；依据有效首轮方案和模型计划任务3。无Git，以正式训练实验冻结源码和SHA追溯。

结论：未发现Critical／Important必须修复问题。

- 三币分别训练C=0.1／1／10，共9个独立scaler＋模型；阈值没有重复拟合。
- 输入明确只取九历史特征；预测不重新拟合，不消费未来标签。
- 样本SHA、配置、UTC时间、特征顺序和严格标签截止有检查。
- 单类／不收敛保留失败，保存后回读核对概率；旧编号拒绝覆盖。
- scikit-learn1.9.1实际版本已锁，模型、参数、来源和环境随实验保存。

此记录是代码检查，不是实际训练／验证或盈利证明；实际拟合状态与证据看EXPERIMENTS和EXP-007 train_manifest。
