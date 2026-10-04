# 第三轮 LightGBM 树模型实施计划

最后更新：2026-10-04（Asia/Shanghai）

## 目标与依赖

- **目标**：在不改变现货模拟资金（100 USDT）、风控底线（50 USDT）与12项特征（含资金费率）的前提下，实现梯度提升树（LightGBM）模型训练与2025年盲考验证回测，通过多特征非线性条件组合提升高胜率交易机会，争取突破 $\ge 30$ 笔闭合交易周期与扣费绝对正收益。
- **依赖**：已归档的 `EXP-003` 基础数据、`EXP-021` 12特征训练样本集；虚拟环境 `.venv/Scripts/python.exe`。
- **约束**：遵循 [D-022](file:///d:/量化/DECISIONS.md) 偏好，仅编写关键行为检查，不写冗余测试；遵循 [D-025](file:///d:/量化/DECISIONS.md) 升级模型架构；2026保留测试集坚决封存。

---

## 任务清单

- [x] **任务 1：安装依赖与配置环境**
  - 在虚拟环境安装 `lightgbm` 依赖（4.7.0）；
  - 更新 `pyproject.toml` 依赖清单；
  - 运行 `pip check` 确认无版本冲突。

- [x] **任务 2：扩展模型训练模块支持 LightGBM**
  - 在 `src/cryptoquant/models/training.py` 中引入 LightGBM 分类器构建逻辑；
  - 支持超参数预设：`candidate_1`（保守浅树）、`candidate_2`（均衡适中树）、`candidate_3`（多层表达树）；
  - 输出特征重要性（feature_importances_）并保存至模型元数据 JSON；
  - 扩展 CLI 与配置支持 `model_family = "lightgbm"`；
  - 编写并运行针对 LightGBM 训练与预测稳定性的针对性检查（`tests/test_lightgbm_training.py` 3 passed）。

- [x] **任务 3：拟合与登记第三轮模型训练（EXP-035）**
  - 配置 `configs/third_experiment.toml`；
  - 登记并运行正式实验 `EXP-035`，使用 2022—2024 开发集（来自 `EXP-021` 样本）；
  - 拟合三币各3组超参数共 9 个 LightGBM 模型，保存至 `artifacts/experiments/EXP-035/models/`；
  - 核验模型重载预测完全一致，生成训练报告与 manifest。

- [x] **任务 4：2025 全年盲考验证回测与多轮对比筛选（EXP-036—EXP-045）**
  - 运行 9 组模型在 2025 全年的独立验证回测（测试阈值 0.55, 0.60, 0.65，EXP-036—044）；
  - 运行综合筛选对比实验（EXP-045），生成多轮对比矩阵（对比 EXP-020 纯K线、EXP-034 资金费率逻辑回归与本轮 LightGBM）；
  - 严格依据 4 项门槛（正收益、回撤 $\le 25\%$、底线 0、交易周期 $\ge 30$）评估是否过线；
  - 结论：树模型在训练集高拟合（62%），但在2025样本外呈现高方差与摩擦过度磨损，全部未过线（`validation_failed_do_not_open_test`）；
  - 坚决维持封存 2026 测试集，同步所有状态与文档。
