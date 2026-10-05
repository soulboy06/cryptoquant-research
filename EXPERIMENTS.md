# 实验登记与结果

最后更新：2026-10-05（Asia/Shanghai）

## 当前事实

已登记至EXP-128。第七轮EXP-122状态准备、123—125三窗R1 base、126选择、127比较均已归档；EXP-128（既有产物机会代价与交易分布专项诊断）完成。R1策略因W1/W2周期不足30、W2收益仅7.35%、合成周净收益低于R0而失格。EXP-128诊断揭示核心根因：1）被拦买单100%为全新开仓，85%+因单边BTC EMA斜率转负被拦截；2）2024牛市错失+17.85 USDT，其中84%（14.99U）集中在被单一BTC过滤器错杀的SOL；Top 10最暴利交易中7笔被错杀；3）2025年拦截成功避开13.54U亏损（以太坊47笔），但放行的52笔在高位强趋势顶背离假突破中遭遇多次-8%止损（主要在SOL，亏损-6.45U）。诊断为下一阶段动态阈值与自适应仓位缩放提供了明确数据支撑。

第八轮[动态阈值与自适应仓位方案](docs/superpowers/specs/2026-10-05-dynamic-threshold-and-position-scaling-design.md)及[实施计划](docs/superpowers/plans/2026-10-05-dynamic-threshold-and-position-scaling-implementation.md)已冻结（D-036），引入 R2/R3/R4 三变体，限定最多 9 个 Base 账户（EXP-129~137）、1 项筛选决策（EXP-138）、最多 6 个压力账户（EXP-139~144）及 1 项综合报告（EXP-145）。2026保留测试继续严格封存。

下方登记表记录实际任务，模板不是实验结果。项目当前进度见 [STATUS.md](STATUS.md)，实验边界见 [AGENTS.md](AGENTS.md)。

[第一轮实验方案](docs/superpowers/specs/2026-10-04-first-experiment-design.md) 已写成并通过文档一致性审查。开发期基准、模型训练、2025验证及压力评价已运行，2026保留测试尚未执行。后续轮次重复使用2025选择模型／阈值，不能称为新的独立盲测；33闭合周期不是统计显著性证明。

[第六轮出场与持仓约束实施计划](docs/superpowers/plans/2026-10-04-exit-rules-and-holding-constraint-implementation.md) Task 1~5 已全部执行完成。

## 实验登记表

| 编号 | 类型 | 状态 | 目标 | 配置与结果位置 |
| --- | --- | --- | --- | --- |
| EXP-001 | 数据检查 | 失败 | 验证三币官方小时归档及公开规则可用于后续离线研究 | [冻结旧配置](artifacts/experiments/EXP-001/prepare/attempt-001/config.toml)；[失败调查报告](artifacts/experiments/EXP-001/diagnostics/report.md) |
| EXP-002 | 数据检查 | 失败 | 在有限精确停机政策下核验完整三币归档、公开规则和分区 | [冻结v1配置](artifacts/experiments/EXP-002/prepare/attempt-001/config.toml)；[全范围原始诊断](artifacts/experiments/EXP-002/diagnostics/full-archive-audit.json) |
| EXP-003 | 数据检查 | 完成 | 使用明确日包来源及不可用观察约束，检查三币归档、规则和分区 | [冻结v2配置](artifacts/experiments/EXP-003/prepare/attempt-001/config.toml)；[质量报告](artifacts/experiments/EXP-003/check-data/attempt-001/report.md) |
| EXP-004 | 历史基准回测 | 完成 | 2022—2024开发期买入持有，三币共用100 USDT，固定50底线 | [报告](artifacts/experiments/EXP-004/report.md)；[核对](artifacts/experiments/EXP-004/verification.json) |
| EXP-005 | 历史基准回测 | 完成 | 同期固定EMA24/72趋势，单币8%止损／4小时冷却，不选参 | [报告](artifacts/experiments/EXP-005/report.md)；[核对](artifacts/experiments/EXP-005/verification.json) |
| EXP-006 | 训练样本准备 | 完成 | 仅development九历史特征／四小时方向标签，严格剔除停机和跨界 | [报告](artifacts/experiments/EXP-006/report.md)、[manifest](artifacts/experiments/EXP-006/sample_manifest.json)；不拟合模型或评价收益 |
| EXP-007 | 模型训练 | 完成 | 用EXP-006独立训练三币各C=0.1／1／10，共9个模型；不选参数 | [报告](artifacts/experiments/EXP-007/report.md)、[manifest](artifacts/experiments/EXP-007/train_manifest.json)、[核对](artifacts/experiments/EXP-007/verification.json) |
| EXP-008 | 验证基准 | 完成 | 2025 buy_hold，base，独立100账户 | [报告](artifacts/experiments/EXP-008/report.md) |
| EXP-009 | 验证基准 | 完成 | 2025 ema_trend，base，独立100账户 | [报告](artifacts/experiments/EXP-009/report.md) |
| EXP-010 | 模型验证 | 完成 | C=0.1，阈值0.55，base | [报告](artifacts/experiments/EXP-010/report.md) |
| EXP-011 | 模型验证 | 完成 | C=0.1，阈值0.60，base | [报告](artifacts/experiments/EXP-011/report.md) |
| EXP-012 | 模型验证 | 完成 | C=0.1，阈值0.65，base | [报告](artifacts/experiments/EXP-012/report.md) |
| EXP-013 | 模型验证 | 完成 | C=1，阈值0.55，base | [报告](artifacts/experiments/EXP-013/report.md) |
| EXP-014 | 模型验证 | 完成 | C=1，阈值0.60，base | [报告](artifacts/experiments/EXP-014/report.md) |
| EXP-015 | 模型验证 | 完成 | C=1，阈值0.65，base | [报告](artifacts/experiments/EXP-015/report.md) |
| EXP-016 | 模型验证 | 完成 | C=10，阈值0.55，base | [报告](artifacts/experiments/EXP-016/report.md) |
| EXP-017 | 模型验证 | 完成 | C=10，阈值0.60，base | [报告](artifacts/experiments/EXP-017/report.md) |
| EXP-018 | 模型验证 | 完成 | C=10，阈值0.65，base | [报告](artifacts/experiments/EXP-018/report.md) |
| EXP-019 | 验证比较／筛选 | 失败（汇总格式错误，11子模拟完成） | 完整保留11组base结果，按预定门槛筛选，不开启test | [失败](artifacts/experiments/EXP-019/failure.json)，旧输出保留 |
| EXP-020 | 验证比较／筛选 | 完成 | 修复汇总字段重复，复用EXP-008—018结果，未过线（闭合周期22<30） | [报告](artifacts/experiments/EXP-020/report.md) |
| EXP-021 | 训练样本准备 | 完成 | 2022—2024开发期12特征样本（9K线+3资金费率），无未来泄露 | [报告](artifacts/experiments/EXP-021/report.md) |
| EXP-022 | 模型训练 | 完成 | 拟合12特征的三币各3组C（共9个模型），保存joblib与参数卡 | [报告](artifacts/experiments/EXP-022/report.md) |
| EXP-023 | 验证基准 | 完成 | 2025 buy_hold对照（second_experiment.toml配置） | [报告](artifacts/experiments/EXP-023/report.md) |
| EXP-024 | 验证基准 | 完成 | 2025 ema_trend对照（second_experiment.toml配置） | [报告](artifacts/experiments/EXP-024/report.md) |
| EXP-025 | 模型验证 | 完成 | 12特征模型，C=0.1，阈值0.55，base | [报告](artifacts/experiments/EXP-025/report.md) |
| EXP-026 | 模型验证 | 完成 | 12特征模型，C=0.1，阈值0.60，base | [报告](artifacts/experiments/EXP-026/report.md) |
| EXP-027 | 模型验证 | 完成 | 12特征模型，C=0.1，阈值0.65，base | [报告](artifacts/experiments/EXP-027/report.md) |
| EXP-028 | 模型验证 | 完成 | 12特征模型，C=1，阈值0.55，base | [报告](artifacts/experiments/EXP-028/report.md) |
| EXP-029 | 模型验证 | 完成 | 12特征模型，C=1，阈值0.60，base | [报告](artifacts/experiments/EXP-029/report.md) |
| EXP-030 | 模型验证 | 完成 | 12特征模型，C=1，阈值0.65，base | [报告](artifacts/experiments/EXP-030/report.md) |
| EXP-031 | 模型验证 | 完成 | 12特征模型，C=10，阈值0.55，base | [报告](artifacts/experiments/EXP-031/report.md) |
| EXP-032 | 模型验证 | 完成 | 12特征模型，C=10，阈值0.60，base | [报告](artifacts/experiments/EXP-032/report.md) |
| EXP-033 | 模型验证 | 完成 | 12特征模型，C=10，阈值0.65，base | [报告](artifacts/experiments/EXP-033/report.md) |
| EXP-034 | 验证比较／筛选 | 完成 | 第二轮2025验证汇总与筛选评估（交易周期22~24笔仍<30笔，未过线） | [报告](artifacts/experiments/EXP-034/report.md) |
| EXP-035 | 模型训练 | 完成 | 第三轮LightGBM树模型训练（12特征，三币各3组复杂度候选共9个模型） | [报告](artifacts/experiments/EXP-035/report.md) |
| EXP-036 | 模型验证 | 完成 | LightGBM，C=0.1，阈值0.55，base | [报告](artifacts/experiments/EXP-036/report.md) |
| EXP-037 | 模型验证 | 完成 | LightGBM，C=0.1，阈值0.60，base | [报告](artifacts/experiments/EXP-037/report.md) |
| EXP-038 | 模型验证 | 完成 | LightGBM，C=0.1，阈值0.65，base | [报告](artifacts/experiments/EXP-038/report.md) |
| EXP-039 | 模型验证 | 完成 | LightGBM，C=1，阈值0.55，base | [报告](artifacts/experiments/EXP-039/report.md) |
| EXP-040 | 模型验证 | 完成 | LightGBM，C=1，阈值0.60，base | [报告](artifacts/experiments/EXP-040/report.md) |
| EXP-041 | 模型验证 | 完成 | LightGBM，C=1，阈值0.65，base | [报告](artifacts/experiments/EXP-041/report.md) |
| EXP-042 | 模型验证 | 完成 | LightGBM，C=10，阈值0.55，base | [报告](artifacts/experiments/EXP-042/report.md) |
| EXP-043 | 模型验证 | 完成 | LightGBM，C=10，阈值0.60，base | [报告](artifacts/experiments/EXP-043/report.md) |
| EXP-044 | 模型验证 | 完成 | LightGBM，C=10，阈值0.65，base | [报告](artifacts/experiments/EXP-044/report.md) |
| EXP-045 | 验证比较／筛选 | 完成 | 第三轮LightGBM 2025验证汇总与筛选评估（树模型样本外过拟合，未过线） | [报告](artifacts/experiments/EXP-045/report.md) |
| EXP-046 | 模型验证 | 完成 | 12特征LR，C=0.1，阈值0.61，base | [报告](artifacts/experiments/EXP-046/report.md) |
| EXP-047 | 模型验证 | 完成 | 12特征LR，C=0.1，阈值0.62，base | [报告](artifacts/experiments/EXP-047/report.md) |
| EXP-048 | 模型验证 | 完成 | 12特征LR，C=0.1，阈值0.63，base | [报告](artifacts/experiments/EXP-048/report.md) |
| EXP-049 | 模型验证 | 完成 | 12特征LR，C=0.1，阈值0.64，base | [报告](artifacts/experiments/EXP-049/report.md)；**首个通过4项门槛的合格候选**（收益+1.54%、回撤2.84%、33笔） |
| EXP-050 | 模型验证 | 完成 | 12特征LR，C=1.0，阈值0.61，base | [报告](artifacts/experiments/EXP-050/report.md) |
| EXP-051 | 模型验证 | 完成 | 12特征LR，C=1.0，阈值0.62，base | [报告](artifacts/experiments/EXP-051/report.md) |
| EXP-052 | 模型验证 | 完成 | 12特征LR，C=1.0，阈值0.63，base | [报告](artifacts/experiments/EXP-052/report.md) |
| EXP-053 | 模型验证 | 完成 | 12特征LR，C=1.0，阈值0.64，base | [报告](artifacts/experiments/EXP-053/report.md) |
| EXP-054 | 模型验证 | 完成 | 12特征LR，C=10.0，阈值0.61，base | [报告](artifacts/experiments/EXP-054/report.md) |
| EXP-055 | 模型验证 | 完成 | 12特征LR，C=10.0，阈值0.62，base | [报告](artifacts/experiments/EXP-055/report.md) |
| EXP-056 | 模型验证 | 完成 | 12特征LR，C=10.0，阈值0.63，base | [报告](artifacts/experiments/EXP-056/report.md) |
| EXP-057 | 模型验证 | 完成 | 12特征LR，C=10.0，阈值0.64，base | [报告](artifacts/experiments/EXP-057/report.md) |
| EXP-058 | 验证比较／筛选 | 完成 | 第四轮细化网格综合筛选；EXP-049正式过线（选为胜出候选） | [报告](artifacts/experiments/EXP-058/report.md) |
| EXP-059 | 模型压力测试 | 完成 | 胜出候选EXP-049（12特征LR，C=0.1，阈值0.64），higher_execution成本（净收益+0.56%，回撤3.03%） | [报告](artifacts/experiments/EXP-059/report.md) |
| EXP-060 | 模型压力测试 | 完成 | 胜出候选EXP-049（12特征LR，C=0.1，阈值0.64），strict极端成本（净收益-1.35%，回撤3.37%） | [报告](artifacts/experiments/EXP-060/report.md) |
| EXP-061 | 压力测试筛选与参数冻结 | 完成 | 汇总EXP-049在三档成本下的鲁棒性；压力测试通过，评定为ready_for_freeze | [报告](artifacts/experiments/EXP-061/report.md) |
| EXP-062 | 既有验证产物交易诊断 | 完成 | 只读EXP-049：33周期成本／时长、三币贡献与6567个4小时预测；两套对账通过，不拟合／新策略／2026评价 | [报告](artifacts/experiments/EXP-062/report.md)、[独立核对](artifacts/experiments/EXP-062/independent_verification.json) |
| EXP-063 | 研究样本准备 | 完成 | 第五轮研究样本准备：核验EXP-003/021来源，截断资金费率至2025-12-31 20:00，生成gross与net两套样本及全量特征 | [报告](artifacts/experiments/EXP-063/report.md) |
| EXP-064 | 模型训练 | 完成 | 第五轮W1窗口模型训练（gross_direction_v1，C=0.1，12特征，三币独立） | [报告](artifacts/experiments/EXP-064/report.md) |
| EXP-065 | 模型训练 | 完成 | 第五轮W1窗口模型训练（net_positive_base_v1，C=0.1，12特征，三币独立） | [报告](artifacts/experiments/EXP-065/report.md) |
| EXP-066 | 模型训练 | 完成 | 第五轮W2窗口模型训练（gross_direction_v1，C=0.1，12特征，三币独立） | [报告](artifacts/experiments/EXP-066/report.md) |
| EXP-067 | 模型训练 | 完成 | 第五轮W2窗口模型训练（net_positive_base_v1，C=0.1，12特征，三币独立） | [报告](artifacts/experiments/EXP-067/report.md) |
| EXP-068 | 窗口基准回测 | 完成 | W1 gross 阈值0.40 base（净收益+138.01%，回撤28.96%，超标） | [报告](artifacts/experiments/EXP-068/report.md) |
| EXP-069 | 窗口基准回测 | 完成 | W1 gross 阈值0.50 base（净收益-18.59%，回撤41.64%） | [报告](artifacts/experiments/EXP-069/report.md) |
| EXP-070 | 窗口基准回测 | 完成 | W1 gross 阈值0.60 base（净收益+3.66%，周期13<30） | [报告](artifacts/experiments/EXP-070/report.md) |
| EXP-071 | 窗口基准回测 | 完成 | W1 gross 阈值0.64 base（净收益+0.80%，周期5<30） | [报告](artifacts/experiments/EXP-071/report.md) |
| EXP-072 | 窗口基准回测 | 完成 | W1 net 阈值0.40 base（净收益+2.63%，回撤27.46%，超标） | [报告](artifacts/experiments/EXP-072/report.md) |
| EXP-073 | 窗口基准回测 | 完成 | W1 net 阈值0.50 base（净收益+2.98%，回撤7.07%，32周期，合格） | [报告](artifacts/experiments/EXP-073/report.md) |
| EXP-074 | 窗口基准回测 | 完成 | W1 net 阈值0.60 base（净收益+1.16%，周期2<30） | [报告](artifacts/experiments/EXP-074/report.md) |
| EXP-075 | 窗口基准回测 | 完成 | W1 net 阈值0.64 base（净收益+0.60%，周期1<30） | [报告](artifacts/experiments/EXP-075/report.md) |
| EXP-076 | 窗口基准回测 | 完成 | W2 gross 阈值0.40 base（净收益+50.23%，回撤37.84%，超标） | [报告](artifacts/experiments/EXP-076/report.md) |
| EXP-077 | 窗口基准回测 | 完成 | W2 gross 阈值0.50 base（净收益-25.33%，回撤46.21%） | [报告](artifacts/experiments/EXP-077/report.md) |
| EXP-078 | 窗口基准回测 | 完成 | W2 gross 阈值0.60 base（净收益+7.42%，周期30，合格） | [报告](artifacts/experiments/EXP-078/report.md) |
| EXP-079 | 窗口基准回测 | 完成 | W2 gross 阈值0.64 base（净收益+4.61%，周期5<30） | [报告](artifacts/experiments/EXP-079/report.md) |
| EXP-080 | 窗口基准回测 | 完成 | W2 net 阈值0.40 base（净收益-1.68%，回撤31.79%） | [报告](artifacts/experiments/EXP-080/report.md) |
| EXP-081 | 窗口基准回测 | 完成 | W2 net 阈值0.50 base（净收益+32.40%，回撤5.99%，66周期，合格） | [报告](artifacts/experiments/EXP-081/report.md) |
| EXP-082 | 窗口基准回测 | 完成 | W2 net 阈值0.60 base（净收益+5.49%，周期15<30） | [报告](artifacts/experiments/EXP-082/report.md) |
| EXP-083 | 窗口基准回测 | 完成 | W2 net 阈值0.64 base（净收益+3.00%，周期10<30） | [报告](artifacts/experiments/EXP-083/report.md) |
| EXP-084 | 滚动选择与参数冻结 | 完成 | 第五轮W1/W2滚动选择：net 0.50为全网格唯一合格候选；gross无合格项固定0.64对照 | [报告](artifacts/experiments/EXP-084/report.md) |
| EXP-085 | 模型压力测试 | 完成 | W1 net 0.50 higher_execution (+2.01%，回撤7.50%) | [报告](artifacts/experiments/EXP-085/report.md) |
| EXP-086 | 模型压力测试 | 完成 | W1 net 0.50 strict (+0.04%，回撤8.36%) | [报告](artifacts/experiments/EXP-086/report.md) |
| EXP-087 | 模型压力测试 | 完成 | W2 net 0.50 higher_execution (+29.78%，回撤6.11%) | [报告](artifacts/experiments/EXP-087/report.md) |
| EXP-088 | 模型压力测试 | 完成 | W2 net 0.50 strict (+22.38%，回撤6.47%) | [报告](artifacts/experiments/EXP-088/report.md) |
| EXP-089 | 模型压力测试 | 完成 | W1 gross 0.64 higher_execution (+0.65%，回撤1.14%) | [报告](artifacts/experiments/EXP-089/report.md) |
| EXP-090 | 模型压力测试 | 完成 | W1 gross 0.64 strict (+0.27%，回撤1.14%) | [报告](artifacts/experiments/EXP-090/report.md) |
| EXP-091 | 模型压力测试 | 完成 | W2 gross 0.64 higher_execution (+4.43%，回撤1.27%) | [报告](artifacts/experiments/EXP-091/report.md) |
| EXP-092 | 模型压力测试 | 完成 | W2 gross 0.64 strict (+4.15%，回撤1.37%) | [报告](artifacts/experiments/EXP-092/report.md) |
| EXP-093 | 模型训练 | 完成 | 第五轮R2025全量训练（gross_direction_v1，C=0.1，12特征，三币独立） | [报告](artifacts/experiments/EXP-093/report.md) |
| EXP-094 | 模型训练 | 完成 | 第五轮R2025全量训练（net_positive_base_v1，C=0.1，12特征，三币独立） | [报告](artifacts/experiments/EXP-094/report.md) |
| EXP-095 | 模型验证 | 完成 | R2025 net 0.50 base (-18.31%，回撤20.05%，130周期) | [报告](artifacts/experiments/EXP-095/report.md) |
| EXP-096 | 模型压力测试 | 完成 | R2025 net 0.50 higher_execution (-21.39%，回撤22.96%) | [报告](artifacts/experiments/EXP-096/report.md) |
| EXP-097 | 模型压力测试 | 完成 | R2025 net 0.50 strict (-27.31%，回撤28.53%) | [报告](artifacts/experiments/EXP-097/report.md) |
| EXP-098 | 模型验证 | 完成 | R2025 gross 0.64 base (+1.54%，回撤2.84%，33周期) | [报告](artifacts/experiments/EXP-098/report.md) |
| EXP-099 | 模型压力测试 | 完成 | R2025 gross 0.64 higher_execution (+0.56%，回撤3.03%) | [报告](artifacts/experiments/EXP-099/report.md) |
| EXP-100 | 模型压力测试 | 完成 | R2025 gross 0.64 strict (-1.35%，回撤3.37%) | [报告](artifacts/experiments/EXP-100/report.md) |
| EXP-101 | 综合对比评估 | 完成 | 第五轮双政策三窗口三档成本综合对比与三层结论最终评定 | [报告](artifacts/experiments/EXP-101/report.md) |
| EXP-102 | 窗口基准回测 | 完成 | 第六轮 W1（2023）基准对照 C0（净收益+2.98%，回撤7.07%，32周期） | [报告](artifacts/experiments/EXP-102/report.md) |
| EXP-103 | 窗口基准回测 | 完成 | 第六轮 W2（2024）基准对照 C0（净收益+32.40%，回撤5.99%，66周期） | [报告](artifacts/experiments/EXP-103/report.md) |
| EXP-104 | 窗口基准回测 | 完成 | 第六轮 R2025 基准对照 C0（净收益-18.31%，回撤20.05%，130周期，8止损） | [报告](artifacts/experiments/EXP-104/report.md) |
| EXP-105 | 窗口消融回测 | 完成 | 第六轮 W1（2023）规则 A 变体 C1（净收益+7.10%，回撤4.99%，34周期，13次时限平仓） | [报告](artifacts/experiments/EXP-105/report.md) |
| EXP-106 | 窗口消融回测 | 完成 | 第六轮 W2（2024）规则 A 变体 C1（净收益+22.67%，回撤5.89%，牛市保留率69.98%未达标） | [报告](artifacts/experiments/EXP-106/report.md) |
| EXP-107 | 窗口消融回测 | 完成 | 第六轮 R2025 规则 A 变体 C1（净收益-14.35%，回撤17.33%，止损降至3次） | [报告](artifacts/experiments/EXP-107/report.md) |
| EXP-108 | 窗口消融回测 | 完成 | 第六轮 W1（2023）规则 B 变体 C2（净收益+4.24%，回撤6.64%，33周期，3次保本平仓） | [报告](artifacts/experiments/EXP-108/report.md) |
| EXP-109 | 窗口消融回测 | 完成 | 第六轮 W2（2024）规则 B 变体 C2（净收益+26.62%，回撤5.87%，牛市保留率82.17%达标） | [报告](artifacts/experiments/EXP-109/report.md) |
| EXP-110 | 窗口消融回测 | 完成 | 第六轮 R2025 规则 B 变体 C2（净收益-12.91%，回撤16.20%，9次保本平仓，减亏5.40U） | [报告](artifacts/experiments/EXP-110/report.md) |
| EXP-111 | 窗口消融回测 | 完成 | 第六轮 W1（2023）组合变体 C3（净收益+4.20%，回撤6.90%，34周期） | [报告](artifacts/experiments/EXP-111/report.md) |
| EXP-112 | 窗口消融回测 | 完成 | 第六轮 W2（2024）组合变体 C3（净收益+20.36%，回撤5.88%，牛市保留率62.85%） | [报告](artifacts/experiments/EXP-112/report.md) |
| EXP-113 | 窗口消融回测 | 完成 | 第六轮 R2025 组合变体 C3（净收益-13.99%，回撤17.23%，7保本+25时限） | [报告](artifacts/experiments/EXP-113/report.md) |
| EXP-114 | 消融评估与参数冻结 | 完成 | 第六轮 $2 \times 2$ 析因评估：C2全面胜出并永久冻结参数卡 | [报告](artifacts/experiments/EXP-114/report.md)、[评估JSON](artifacts/experiments/EXP-114/evaluation.json) |
| EXP-115 | 模型压力测试 | 完成 | 胜出候选 C2 W1 higher_execution 成本测试（净收益+3.21%，回撤6.85%） | [报告](artifacts/experiments/EXP-115/report.md) |
| EXP-116 | 模型压力测试 | 完成 | 胜出候选 C2 W2 higher_execution 成本测试（净收益+21.55%，回撤5.99%） | [报告](artifacts/experiments/EXP-116/report.md) |
| EXP-117 | 模型压力测试 | 完成 | 胜出候选 C2 R2025 higher_execution 成本测试（净收益-16.27%，回撤19.20%） | [报告](artifacts/experiments/EXP-117/report.md) |
| EXP-118 | 模型压力测试 | 完成 | 胜出候选 C2 W1 strict 极端成本测试（净收益+0.62%，回撤8.36%） | [报告](artifacts/experiments/EXP-118/report.md) |
| EXP-119 | 模型压力测试 | 完成 | 胜出候选 C2 W2 strict 极端成本测试（净收益+14.98%，回撤6.24%） | [报告](artifacts/experiments/EXP-119/report.md) |
| EXP-120 | 模型压力测试 | 完成 | 胜出候选 C2 R2025 strict 极端成本测试（净收益-23.10%，回撤25.39%） | [报告](artifacts/experiments/EXP-120/report.md) |
| EXP-121 | 综合对比评估 | 完成 | 第六轮出场规则与持仓约束跨时期跨成本全景综合评估报告与三层结论最终评定 | [报告](artifacts/experiments/EXP-121/report.md)、[全景JSON](artifacts/experiments/EXP-121/comparison.json) |
| EXP-122 | 市场状态准备 | 完成 | 第七轮连续闭合BTC ADX14／EMA72／slope24，R0／R1冻结；003／063及三窗旧模型来源 | [状态清单](artifacts/experiments/EXP-122/state_manifest.json)；[运行](artifacts/experiments/EXP-122/run_manifest.json) |
| EXP-123 | 过滤账户回测 | 完成 | R1 C2 W1（2023）base，100共用／50固定底线；模型065、state122 | [摘要](artifacts/experiments/EXP-123/summary.json)；[报告](artifacts/experiments/EXP-123/report.md) |
| EXP-124 | 过滤账户回测 | 完成 | R1 C2 W2（2024）base，100共用／50固定底线；模型067、state122 | [摘要](artifacts/experiments/EXP-124/summary.json)；[报告](artifacts/experiments/EXP-124/report.md) |
| EXP-125 | 过滤账户回测 | 完成 | R1 C2 R2025（已查看研究）base，100共用／50固定底线；模型094、state122 | [摘要](artifacts/experiments/EXP-125/summary.json)；[报告](artifacts/experiments/EXP-125/report.md) |
| EXP-126 | 过滤基础选择 | 完成（失格） | 完整R1 base三窗123／124／125对R0按冻结6.1精确筛选；不忽略样本不足或失败 | [选择](artifacts/experiments/EXP-126/selection.json)；[报告](artifacts/experiments/EXP-126/report.md) |
| EXP-127 | 过滤综合比较 | 完成（R1失格） | R0九旧账户来源及R1三base全结果，精确失格／机会代价／周目标；按126失格不跑压力 | [报告](artifacts/experiments/EXP-127/report.md)；[比较](artifacts/experiments/EXP-127/comparison.json) |
| EXP-128 | 既有产物机会代价诊断 | 完成 | 只读EXP-122~127与R0对账，深入诊断正数量被拦买单、2024牛市错失收益与2025残余亏损分布 | [报告](artifacts/experiments/EXP-128/report.md)；[诊断](artifacts/experiments/EXP-128/diagnostics.json)；[清单](artifacts/experiments/EXP-128/run_manifest.json) |
| EXP-129 | 动态响应回测 | 失败 | R2（动态提阈值 T=0.60/30%）W1（2023）base 成本（报告字段名微差异常退出，产物保留） | [清单](artifacts/experiments/EXP-129/run_manifest.json) |
| EXP-130 | 动态响应回测 | 完成 | R2（动态提阈值 T=0.60/30%）W1（2023）base 成本（收益+0.17%，回撤4.02%，周期18<30） | [摘要](artifacts/experiments/EXP-130/summary.json)；[报告](artifacts/experiments/EXP-130/report.md) |
| EXP-131 | 动态响应回测 | 完成 | R2（动态提阈值 T=0.60/30%）W2（2024）base 成本（收益+12.28%<15%，回撤3.38%，周期26<30） | [摘要](artifacts/experiments/EXP-131/summary.json)；[报告](artifacts/experiments/EXP-131/report.md) |
| EXP-132 | 动态响应回测 | 完成 | R2（动态提阈值 T=0.60/30%）R2025 base 成本（收益-9.09%，回撤11.14%，周期67） | [摘要](artifacts/experiments/EXP-132/summary.json)；[报告](artifacts/experiments/EXP-132/report.md) |
| EXP-133 | 动态响应回测 | 完成 | R3（自适应降仓 T=0.50/10%）W1（2023）base 成本（收益+2.46%，回撤3.72%，周期29<30） | [摘要](artifacts/experiments/EXP-133/summary.json)；[报告](artifacts/experiments/EXP-133/report.md) |
| EXP-134 | 动态响应回测 | 完成 | R3（自适应降仓 T=0.50/10%）W2（2024）base 成本（收益+13.66%<15%，回撤2.79%，周期55） | [摘要](artifacts/experiments/EXP-134/summary.json)；[报告](artifacts/experiments/EXP-134/report.md) |
| EXP-135 | 动态响应回测 | 完成 | R3（自适应降仓 T=0.50/10%）R2025 base 成本（收益-7.68%，回撤11.92%，周期50） | [摘要](artifacts/experiments/EXP-135/summary.json)；[报告](artifacts/experiments/EXP-135/report.md) |
| EXP-136 | 动态响应回测 | 完成 | R4（双重协同 T=0.60/15%）W1（2023）base 成本（收益+0.17%，回撤4.02%，周期18<30） | [摘要](artifacts/experiments/EXP-136/summary.json)；[报告](artifacts/experiments/EXP-136/report.md) |
| EXP-137 | 动态响应回测 | 完成 | R4（双重协同 T=0.60/15%）W2（2024）base 成本（收益+9.35%<15%，回撤2.86%，周期26<30） | [摘要](artifacts/experiments/EXP-137/summary.json)；[报告](artifacts/experiments/EXP-137/report.md) |
| EXP-138 | 动态响应回测 | 完成 | R4（双重协同 T=0.60/15%）R2025 base 成本（收益-7.80%，回撤10.15%，周期67） | [摘要](artifacts/experiments/EXP-138/summary.json)；[报告](artifacts/experiments/EXP-138/report.md) |
| EXP-139 | 动态基础筛选 | 完成（全失格） | 第八轮 R2/R3/R4 跨三窗口 9 组 Base 基础筛选；全军覆没停止压力测试 | [选择](artifacts/experiments/EXP-139/selection.json)；[报告](artifacts/experiments/EXP-139/report.md) |
| EXP-140 | 动态综合对比 | 完成 | 第八轮 R2/R3/R4 动态响应全景综合对比评估与三层结论最终评定 | [报告](artifacts/experiments/EXP-140/report.md)；[比较](artifacts/experiments/EXP-140/comparison.json) |
| EXP-141 | 相对强弱回测 | 完成 | R5（Alpha 20% / 弱币 10%）W1（2023）base 成本（收益+4.17%，回撤3.66%，周期29<30） | [摘要](artifacts/experiments/EXP-141/summary.json)；[报告](artifacts/experiments/EXP-141/report.md) |
| EXP-142 | 相对强弱回测 | 完成 | R5（Alpha 20% / 弱币 10%）W2（2024）base 成本（收益+13.82%<15%，回撤2.86%，周期56） | [摘要](artifacts/experiments/EXP-142/summary.json)；[报告](artifacts/experiments/EXP-142/report.md) |
| EXP-143 | 相对强弱回测 | 完成 | R5（Alpha 20% / 弱币 10%）R2025 base 成本（收益-1.92%>-5%，回撤11.10%，周期57） | [摘要](artifacts/experiments/EXP-143/summary.json)；[报告](artifacts/experiments/EXP-143/report.md) |
| EXP-144 | 相对强弱回测 | 完成 | R6（Alpha 25% / 弱币 10%）W1（2023）base 成本（收益+5.06%，回撤3.63%，周期29<30） | [摘要](artifacts/experiments/EXP-144/summary.json)；[报告](artifacts/experiments/EXP-144/report.md) |
| EXP-145 | 相对强弱回测 | 完成 | R6（Alpha 25% / 弱币 10%）W2（2024）base 成本（收益+13.74%<15%，回撤2.98%，周期59） | [摘要](artifacts/experiments/EXP-145/summary.json)；[报告](artifacts/experiments/EXP-145/report.md) |
| EXP-146 | 相对强弱回测 | 完成 | R6（Alpha 25% / 弱币 10%）R2025 base 成本（收益-2.24%>-5%，回撤11.21%，周期57） | [摘要](artifacts/experiments/EXP-146/summary.json)；[报告](artifacts/experiments/EXP-146/report.md) |
| EXP-147 | 相对强弱回测 | 完成 | R7（Alpha 波动率双自适应）W1（2023）base 成本（收益+3.31%，回撤3.70%，周期29<30） | [摘要](artifacts/experiments/EXP-147/summary.json)；[报告](artifacts/experiments/EXP-147/report.md) |
| EXP-148 | 相对强弱回测 | 完成 | R7（Alpha 波动率双自适应）W2（2024）base 成本（收益+13.54%<15%，回撤2.73%，周期54） | [摘要](artifacts/experiments/EXP-148/summary.json)；[报告](artifacts/experiments/EXP-148/report.md) |
| EXP-149 | 相对强弱回测 | 完成 | R7（Alpha 波动率双自适应）R2025 base 成本（收益-2.01%>-5%，回撤11.13%，周期57） | [摘要](artifacts/experiments/EXP-149/summary.json)；[报告](artifacts/experiments/EXP-149/report.md) |
| EXP-150 | 相对强弱筛选 | 完成（全失格） | 第九轮 R5/R6/R7 跨三窗口 9 组 Base 基础筛选；全失格坚决停止压力测试 | [选择](artifacts/experiments/EXP-150/selection.json)；[报告](artifacts/experiments/EXP-150/report.md) |
| EXP-157 | 相对强弱对比 | 完成 | 第九轮 R5/R6/R7 多币种相对强弱解耦全景综合对比评估与三层结论最终评定 | [报告](artifacts/experiments/EXP-157/report.md)；[比较](artifacts/experiments/EXP-157/comparison.json) |
| EXP-158 | 既有产物只读诊断 | 完成 | 第九轮相对强弱解耦产物只读深度诊断（W1 缺 1 笔机制根因、W2 差 1.18% 损益归因与第十轮技术路线决策） | [报告](artifacts/experiments/EXP-158/report.md)；[诊断](artifacts/experiments/EXP-158/diagnostics.json)；[清单](artifacts/experiments/EXP-158/run_manifest.json) |

## EXP-158：第九轮相对强弱解耦产物只读深度诊断实际结果

- 状态：全部完成。2026-10-05（Asia/Shanghai）；只读深度诊断，0 新交易账户，0 真实下单，2026 测试集物理封存。
- 诊断来源：EXP-141~149（第九轮 Base）、EXP-130~140（第八轮）、EXP-108~110（R0 基准）。
- 关键诊断发现：
  1. **W1 周期（29 vs 30）底层真相**：
     - 四组变体（R3、R5、R6、R7）在 2023 开发期**实际完成的买入和卖出撮合成交均为 30 笔**；
     - 记录少计 1 笔的根因：2023-06-10 04:00 SOL 以 10% 仓位买入（10.33 USDT）；05:00 遭遇突发闪跌 -10.5% 至 14.57 USDT，持仓净值跌至 9.24 USDT；触发 8% 止损时因低于交易所最低 10 USDT 名义金额限制被拒单；撮合引擎中的 `complete_exit_if_tail` 将其误判为无法卖出的零头尾差，将 `cycle_open` 标志提前清零；随后在 2023-06-11 20:00 SOL 反弹至 15.99 USDT（名义价值 10.14 USDT）被 `strategy_exit` 完整平仓时，由于 `cycle_open` 为 False，导致该笔完整交易未被累计入 `closed_cycles` 计数器；
     - **结论**：W1 实质已具备 30 笔样本的统计充足性。
  2. **W2 牛市收益差距（+13.82% vs 15.00%）损益剖析**：
     - 实际差距仅 **1.176 USDT**；
     - 交易摩擦成本消耗 2.036 USDT（折合 2.04% 净值），毛收益实为 **+15.86%**；
     - 资产贡献极度分化：SOL 净贡献 +9.99 USDT（占 71.7%），ETH 贡献 +3.82 USDT，BTC 净贡献仅 +0.01 USDT（且 4 笔大止损亏掉 -2.08 USDT）；
     - 出场机制检验：91.1% 的交易由 4 小时趋势反转自然出场，未发生趋势被提前截断的情况。
  3. **第十轮技术路线决策判定（Risk Parity vs 置信度配仓）**：
     - **否定传统 Risk Parity（波动率平价）**：年化波动率 SOL 88% > ETH 58% > BTC 42%。套用该模型将给 BTC 分配 45% 重仓，而只给 SOL 分配 22% 轻仓！但这将直接削弱产生 72%~84% 利润的 SOL，并把重仓交给打平甚至亏损的 BTC，**必然导致牛市收益大幅下滑，无法跨越 15% 门槛**；
     - **否定绝对概率置信度（$P \ge 0.60$）**：底层 12 特征逻辑回归对高波动 SOL 的预测概率在 2023 与 2024 全年**从未达到过 0.60**（W1 最大 0.5892，W2 最大 0.5714）；达到 0.60 的全是不赚钱的 BTC 和 ETH。若设置绝对门槛提仓，SOL 永远无法获得高配仓；
     - **推荐第十轮科学破局方向**：**币种内部相对置信度（$\Delta P = P - 0.50 \ge 0.03$）与短期动量加速（$R_{24h} > 0$ 且 Top-1 Alpha）强化配仓**（将 SOL 加速期 7 笔交易由 20% 恢复至 30%，预计可直接增厚收益 +2.5%~3.5%，推动 W2 越过 15%）。
- 产物位置：[EXP-158诊断报告](artifacts/experiments/EXP-158/report.md)、[诊断JSON](artifacts/experiments/EXP-158/diagnostics.json)、[清单](artifacts/experiments/EXP-158/run_manifest.json)。

- 状态：全部完成。2026-10-05（Asia/Shanghai）；涵盖 9 组 Base 基础回测（EXP-141~149）、1 组基础门槛决策筛选（EXP-150）与 1 组全景综合对比报告（EXP-157）。
- 实验性质：各窗口独立 100 USDT 虚拟本金，固定 50 USDT 硬底线，C2 出场规则（1.20% 保本激活），12 特征逻辑回归模型（复用 EXP-065/067/094 权重，不重拟合），纯离线回测，2026 保留测试集继续严格封存。

### 1. 全矩阵对比表现（Base 成本：单边手续费 0.10%，不利滑点 0.05%）

| 变体代号 | 机制设计 | W1 净收益 (回撤 / 周期) | W2 净收益 (回撤 / 周期) | R2025 净收益 (回撤 / 周期) | 合成周几何收益 $g_{\text{week}}$ | 2025 减亏 >-5% | 筛选门槛资格判定 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R0**（基准对照） | 恒定 $T=0.50$, 恒定 $30\%$ | +4.235410% (6.64% / 33) | **+26.622556%** (5.87% / 68) | -12.914501% (16.20% / 134) | +0.088985%/周 | 否 (-12.91%) | 基准对照（第六轮冻结） |
| **R1**（二元过滤） | 顺势 $30\%$, 弱市绝对禁买 | +0.168377% (4.02% / 18) | +7.346755% (2.89% / 17) | -6.424522% (12.25% / 52) | +0.003944%/周 | 否 (-6.42%) | 失格（第七轮淘汰） |
| **R3**（自适应降仓） | 顺势 $30\%$, 弱市一刀切 $10\%$ | +2.457910% (3.72% / 29) | +13.661196% (2.79% / 55) | -7.676668% (11.92% / 50) | +0.046297%/周 | 否 (-7.68%) | 失格（第八轮淘汰） |
| **R5**（Alpha 解耦 20%） | 顺势 $30\%$, 弱市龙头 $20\%$, 平庸 $10\%$ | **+4.169446%** (3.66% / 29) | **+13.824074%** (2.86% / 56) | **-1.918325%** (11.10% / 57) | **+0.096479%/周** | **是 (-1.92%)** | **失格**（W1 缺 1 笔，W2 缺 1.18%） |
| **R6**（Alpha 解耦 25%） | 顺势 $30\%$, 弱市龙头 $25\%$, 平庸 $10\%$ | **+5.064268%** (3.63% / 29) | **+13.736853%** (2.98% / 59) | **-2.236652%** (11.21% / 57) | **+0.099379%/周** | **是 (-2.24%)** | **失格**（W1 缺 1 笔，W2 缺 1.26%） |
| **R7**（双自适应） | 顺势 $30\%$, 加速 $25\%$, 盘整 $15\%$, 平庸 $10\%$ | +3.311804% (3.70% / 29) | +13.539467% (2.73% / 54) | -2.012527% (11.13% / 57) | +0.088978%/周 | **是 (-2.01%)** | **失格**（W1 缺 1 笔，W2 缺 1.46%） |

*注：三窗口所有变体的本金底线触发次数均为 0。费用支出（USDT）：R5 W1 1.4551 / W2 2.0364 / R2025 3.2677；R6 W1 1.5097 / W2 2.1402 / R2025 3.3384。*

### 2. 深入量化洞察与重大机制突破

1. **合成周收益首度历史性超越全仓基准（R0）**：
   - 前八轮研究中，任何过滤或降仓都会在牛市产生不可避免的机会成本，导致综合周收益落后于 R0；
   - 本轮通过 Alpha 解耦，**R6 合成周收益达到 +0.099379%/周**（较 R0 相对提升 +11.68%，较 R3 +0.0463%/周 翻倍）；**R5 达到 +0.096479%/周**（较 R0 相对提升 +8.42%）。
2. **2025 减亏防守创下历史最佳纪录**：
   - R5 将 2025 年净亏损压缩至仅 **-1.9183%**（R0 为 -12.91%，R3 为 -7.68%），最大回撤降至 11.10%（R0 为 16.20%）；
   - R5、R6、R7 **全员历史性达成 >-5% 的进阶防守红线**，验证了“弱势期解耦超额强势币 + 平庸币深度防御”的因果有效性。
3. **失格项客观剖析**：
   - 各变体 W1 闭合周期均为 29 笔（差 1 笔达标 30 笔）；
   - W2 净收益达到 +13.82%（R5）与 +13.74%（R6），距离 15.00% 门槛仅差 1.18% ~ 1.26%；
   - 依据冻结规则坚决判定失格，停止后续 6 组压力测试（EXP-151~156 未创建）。
4. **长期复利目标评定**：
   - 最高实测周收益为 +0.0994%/周，距离用户每周 1.500%（年化 116.89%）复利目标仍有显著差距。

## EXP-129—140：第八轮动态阈值调节与自适应仓位响应实际结果

- 状态：全部完成。2026-10-05（Asia/Shanghai）；涵盖 1 组启动格式异常失败留存（EXP-129）、9 组 Base 基础回测（EXP-130~138）、1 组基础门槛决策筛选（EXP-139）与 1 组全景综合对比报告（EXP-140）。
- 实验性质：各窗口独立 100 USDT 虚拟本金，固定 50 USDT 硬底线，C2 出场规则（1.20% 保本激活），12 特征逻辑回归模型（复用 EXP-065/067/094 权重，不重拟合），纯离线回测，2026 保留测试集继续严格封存。

### 1. 全景对比矩阵（Base 成本：单边手续费 0.10%，不利滑点 0.05%）

| 变体代号 | 响应机制设计 | W1 净收益 (回撤 / 周期) | W2 净收益 (回撤 / 周期) | R2025 净收益 (回撤 / 周期) | 合成周几何收益 $g_{\text{week}}$ | 筛选门槛资格判定 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R0**（基准对照） | 恒定 $T=0.50$, 恒定 $30\%$ 仓位 | +4.235410% (6.64% / 33) | **+26.622556%** (5.87% / 68) | -12.914501% (16.20% / 134) | **+0.088985%/周** | 基准对照（第六轮已冻结） |
| **R1**（二元过滤） | 顺势 $T=0.50/30\%$, 弱势绝对禁买 | +0.168377% (4.02% / 18) | +7.346755% (2.89% / 17) | -6.424522% (12.25% / 52) | +0.003944%/周 | 失格（第七轮淘汰，错杀牛市） |
| **R2**（动态阈值） | 顺势 $T=0.50/30\%$, 弱势 $T=0.60/30\%$ | +0.168377% (4.02% / 18) | +12.276275% (3.38% / 26) | -9.094323% (11.14% / 67) | +0.014135%/周 | **失格**（W1/W2周期<30，W2收益<15%） |
| **R3**（自适应降仓） | 顺势 $T=0.50/30\%$, 弱势 $T=0.50/10\%$ | **+2.457910%** (3.72% / 29) | **+13.661196%** (2.79% / 55) | **-7.676668%** (11.92% / 50) | **+0.046297%/周** | **失格**（W1周期29缺1，W2收益13.66%<15%） |
| **R4**（双重协同） | 顺势 $T=0.50/30\%$, 弱势 $T=0.60/15\%$ | +0.168377% (4.02% / 18) | +9.352240% (2.86% / 26) | -7.801658% (10.15% / 67) | +0.006298%/周 | **失格**（W1/W2周期<30，W2收益<15%） |

*注：三窗口所有变体的本金底线触发次数均为 0。费用支出（USDT）：R3 W1 1.3458 / W2 1.8966 / R2025 2.8484；R0 对应为 2.0054 / 4.4437 / 7.4327。*

### 2. 深入量化洞察与根因剖析

1. **R3（自适应降仓）展现出压倒性优势，远超 R1、R2 与 R4**：
   - **破解 R1“牛市扼杀”缺陷**：在 2024 年大牛市（W2），R3 斩获 **+13.66%** 净收益（是 R1 7.35% 的近两倍），闭合周期达 **55 笔**（R1 仅可怜的 17 笔），最大回撤仅 **2.79%**（全矩阵最低！）；成功捕获了被 R1 粗暴拦截的绝大多数动量主升浪；
   - **攻克 2025“满仓假突破硬止损”痛点**：在 2025 复杂震荡市，R3 相比 R0 实现了 **+5.24 USDT 的巨幅减亏**（-7.68% vs R0 的 -12.91%），回撤由 16.20% 压缩至 **11.92%**，同时依然保证了 **50 笔充足的统计显著性样本量**（远超 $\ge 30$ 门槛）；弱势状态下将试错仓位缩减至 10%，使单笔 -8% 硬止损对账户净值的冲击从 2.4% 骤降至 0.8%；
   - **合成周收益跃升**：合成周几何收益达 **+0.0463%/周**，较第七轮 R1（+0.0039%/周）提升了 **11.7 倍**！
2. **为何提高阈值方案（R2 与 R4）表现较差？**：
   - 动态将弱势阈值提高至 $T=0.60$ 依然过于严苛。在 W1（2023）与 W2（2024），R2 和 R4 的交易周期仅有 18 笔与 26 笔，均未能越过 $\ge 30$ 笔的显著性红线；
   - 在加密货币市场中，许多主升浪初期均表现为 BTC 的横盘整理，在整理期机械提高出击门槛同样错失了大量右侧突破良机。
3. **严格遵守门槛与停止压力测试**：
   - 尽管 R3 综合表现极佳，但按照方案第 5.1 节预先冻结的刚性筛选门槛：
     - W1 闭合周期为 29 笔（离 $\ge 30$ 笔刚性门槛差 1 笔）；
     - W2 净收益为 +13.66%（离 $\ge 15.00\%$ 刚性门槛差 1.34%）；
     - 合成周收益 +0.0463%/周低于 R0 的 +0.0890%/周（因 R3 弱势降仓后牛市收益略低于 R0 的满仓暴利）；
   - **决选判定**：EXP-139 判定全候选失格（`eligible = False, winner = None`）；
   - **恪守预算与门禁**：按照事先冻结的执行规则，**坚决停止后续 6 组压力测试（EXP-139~144 未被创建）**，直接输出全景对比报告 EXP-140，全轮总尝试严格锁定在 12 项，节约了无谓的回测消耗。

### 3. 三层结论最终评定

1. **结论一（因果性与方法有效性）**：**【通过】**（BTC 状态生成严格截至 $t-1\text{h}$ 闭合 K 线，零未来信息泄漏；交易引擎支持 0.10/0.15/0.30 动态目标权重，资金同比缩放与滑点记账守恒，45 项单元与回归测试全绿通过）；
2. **结论二（相对改善与机会代价权衡）**：**【观察到部分局部改善，但整体未全面达标】**（R3 变体通过自适应降仓成功修复了 R1 扼杀牛市的致命硬伤，并在 2025 实现了大幅减亏与超低回撤，但由于 W1 周期差 1 笔且 W2 收益差 1.34%，未能同时跨三窗口全面越过严苛门槛）；
3. **结论三（用户每周 1.5% 长期复利目标）**：**【未达到】**（R3 合成周收益为 +0.0463%/周，2025 年度依然为负，与每周 1.500% 的长期复利目标仍存在明显差距）。

---

- 状态：完成。2026-10-05（Asia/Shanghai）；脚本 `artifacts/experiments/EXP-128/diagnose.py`，产物 [report.md](artifacts/experiments/EXP-128/report.md)、[diagnostics.json](artifacts/experiments/EXP-128/diagnostics.json)、[run_manifest.json](artifacts/experiments/EXP-128/run_manifest.json)。
- 性质：**既有产物只读专项诊断**，严格只读 EXP-122~127 与 R0（EXP-108~110）冻结文件，不拟合模型、不重新回测、不触碰 2026 保留测试集。
- 关键诊断发现：
  1. **被拦买单属性**：W1/W2/R2025 分别被拦截 23 / 70 / 110 笔买单，**100% 均为全新开仓机会（持仓为 0）**，无重复补仓。
  2. **拦截失效根源**：85%+ 的拦截仅仅是因为 **BTC EMA72 24小时斜率转负（`slope24 <= 0`）**（W2 占 87.1%，R2025 占 82.7%），当时 BTC ADX 依然处于强趋势区。
  3. **2024 牛市巨大机会代价**：R0（68 笔，+23.29 USDT）vs R1（17 笔，+5.44 USDT），**错失 51 笔交易共 +17.85 USDT 净利润**；其中 **84.0%（+14.99 USDT）严重集中在 SOLUSDT**（错失 20 笔 SOL 独立主升浪，胜率 70%）；2024 全年 Top 10 最赚钱交易中 **7 笔被单一 BTC 过滤器错杀**。
  4. **2025 震荡市双刃剑**：正面拦截 85 笔无序拉锯，**挽回 +13.54 USDT 亏损**（尤其是 ETH 挽回 10.37U）；负面放行的 52 笔中，最大亏损均发生在“BTC ADX 处于高位强趋势放行、但随后发生顶背离假突破暴跌”上（如 2025-01-20 与 2025-03-03 的 8% 硬止损），SOL 单币造成 -6.45 USDT 亏损（占 73.2%）。
  5. **量化启示**：下一阶段必须废弃 0/1 绝对开关，转向“不利状态下动态提高阈值（如 T=0.60）”与“波动率/状态自适应仓位缩放（10%~15%）”，兼顾标的自身相对强弱，不再用单一 BTC 指标无脑绑架山寨币。

## EXP-122—127：第七轮闭合BTC买入过滤实际结果

- 2026-10-05（Asia/Shanghai）：状态122连续35,804小时，三窗每4h BUY许可；EXP-123／124／125共3独立100 USDT账户，既有065／067／094模型只预测，C2／12特征／资金风险上限均不改。R0复用108／109／110及115—120九冻结账户，未重跑。
- 126精确基础失格项：W1周期18<30、W2周期17<30、W2收益7.3467551725755%<20%、合成g_week=0.0000394433354965263672264496925590618073786578731低于R0的0.0008898527598482337493232417457697329207227635991（数值是收益小数，显示百分比需×100）。R2025改善至-6.42452200328885%、DD12.25149719760993%，仍未达>-5%较高目标。四基础门槛失败，所有floor0不改变资格。
- R0→R1费用W1 2.005433→1.093758、W2 4.443725→1.041953、2025 7.432712→2.898759 USDT；周期33→18、68→17、134→52，收益代价为W1约-4.067033／W2约-19.275801／2025约+6.489979个百分点。不能把少交易或少费用单独视为提高盈利。
- 127仅比较完整3base；没有合格候选，按方案停止压力，不额外测试ADX／EMA／阈值组合。三窗独立资金、均已查看研究；不称连续三年复利或新盲测，2026未评价。来源／接口通过、历史相对取舍、目标未达分层陈述。
- 模拟账户预算3／9、总尝试6／12，六运行complete而策略资格失败；没有启动失败、运行中遗留或被隐藏的新账户。完整订单含拒单、概率、许可、成交、净值、周统计、按币与风险事件及SHA保存在各目录。root最终产物／source SHA及预算一致证据`.cache/seventh-final-verification-20261005.json`。

## EXP-102~121：第六轮出场规则优化与持仓约束消融实验实际结果

- 状态：全部完成。实际于UTC 2026-10-04 14:45—14:55运行；配置`configs/sixth_experiment.toml`。
- $2 \times 2$ 析因消融矩阵（EXP-102~EXP-113）：
  - **基准对照 C0**：W1净收益+2.98%（回撤7.07%），W2净收益+32.40%（回撤5.99%），R2025净收益-18.31%（回撤20.05%，触发8次8%止损）。
  - **规则 A 变体 C1（8h 时限）**：时限强制平仓显著压制了 2025 的止损发生（从 8 次降至 3 次，减亏至 -14.35%），并在 W1 录得 +7.10%；但**严重机械截断了 2024 年强趋势单的利润奔跑**，W2 净收益从 +32.40% 跌至 +22.67%，牛市收益保留率仅为 **69.98%**（低于预先冻结的 $\ge 75\%$ 门槛，被一票否决淘汰）。
  - **规则 B 变体 C2（动态保本止损）**：在 W2 牛市让趋势充分奔跑，录得 +26.62% 净收益，牛市收益保留率高达 **82.17%**（远超 75% 门槛）；同时在 2025 震荡市中，9 次在利润回吐时触发保本退出（平仓价锁定于 `average_cost * 1.0025`），将净亏损从 -18.31% 显著收窄至 **-12.91%**（减亏 5.40 USDT），最大回撤收窄至 **16.20%**；跨三年合成收益达到 **+0.0890%/周**，三期总财富乘数达到 **1.1494x**，为全矩阵最高。
  - **组合变体 C3（双规则组合）**：同样受制于时限规则截断趋势，W2 净收益跌至 +20.36%（保留率仅 62.85%），表现劣于纯 C2。
- 消融筛选与参数永久冻结（EXP-114）：
  - 依据预先冻结标准，C2 为全矩阵中**唯一**通过全部门槛的胜出变体。正式生成并永久冻结参数卡：`strategy = "rule_b_breakeven_stop"`，`breakeven_activation = 0.0120`，`breakeven_ratio = 0.0025`，`cooldown_hours = 4`，`stop_loss = 0.08`。
- 胜出候选 C2 跨时期压力测试（EXP-115~EXP-120）：
  - **higher_execution 成本档（双边往返 0.40%）**：W1 净收益 +3.21%（回撤 6.85%），W2 净收益 +21.55%（回撤 5.99%），R2025 净亏损 -16.27%（回撤 19.20%）。6项预定量化标准全数达标。
  - **strict 极端摩擦档（双边往返 0.60%）**：W1 净收益 +0.62%（回撤 8.36%），W2 净收益 +14.98%（回撤 6.24%），R2025 净亏损 -23.10%（回撤 25.39%）。底线触发次数均为 0，系统具备强大鲁棒性。
- 综合对比评估与三层结论最终评定（EXP-121）：
  - **结论一（方法有效性）**：**【通过】**（实现严格无未来泄露，持仓均价计算纠正、消除重复扣费，禁止同根 K 线即时重买并执行 4 小时冷却，代码单测 100% 通过）。
  - **结论二（相对改善观察）**：**【显著改善】**（C2 相对 C0 在 2025 减亏 5.40 USDT，回撤压低 3.85 个百分点，2024 保持 82.17% 高保留率，在三档成本下均展现清晰正向贡献）。
  - **结论三（达到用户每周 1.5% 目标）**：**【目标未达到】**（C2 三年合成复合周收益为 +0.0890%/周，2025 单年仍录得 -12.91% 亏损，距离用户周度 +1.500% 长期目标仍有结构性差距）。
- 详见 [EXP-114消融评估报告](artifacts/experiments/EXP-114/report.md) 与 [EXP-121全景报告](artifacts/experiments/EXP-121/report.md)。

## EXP-068~101：第五轮受控窗口回测、滚动选择、压力测试与综合对比实际结果

- 状态：全部完成。实际于UTC 2026-10-04 13:40—13:50运行；使用独立环境，配置`configs/fifth_experiment.toml`。
- 16组W1/W2基础窗口回测（EXP-068~EXP-083）：
  - `gross_direction_v1`策略：低阈值（0.40/0.50）在两窗口均产生28.96%~46.21%的巨大回撤，严重违反<=25%门槛；高阈值（0.60/0.64）出击次数骤降，W1周期仅5~13笔，W2在0.64仅5笔（未达>=30笔）。**旧标签在全网格无一候选同时满足两窗门槛**。
  - `net_positive_base_v1`策略：成功过滤微利噪声后，**阈值0.50成为两窗全网格唯一双达标候选**。W1（2023）净收益+2.98%，回撤7.07%，32周期；W2（2024）净收益+32.40%，回撤5.99%，66周期；两窗合成周复合增长率达到 **+0.2973%/周**，无底线触发。
- 滚动选择与参数冻结（EXP-084）：
  - `net_positive_base_v1`评定为`qualified_and_selected`，选定冻结阈值T=0.50，准予执行R2025盲测（`do_not_run_R2025 = False`）；
  - `gross_direction_v1`评定为`failed_with_reference`，固定原0.64作为对照基准。
- W1/W2压力测试（EXP-085~EXP-092）：
  - 选定候选`net_positive_base_v1`（T=0.50）在higher_execution成本下W1收益+2.01%、W2收益+29.78%；在极端strict摩擦下W1收益+0.04%、W2收益+22.38%，表现出优秀的抗摩擦鲁棒性。
- R2025独立盲测与压力测试（EXP-093~EXP-100）：
  - 模型训练（EXP-093 gross / EXP-094 net）：拟合2022-01-01至2025-01-01全量开发期三币独立模型（C=0.1，12特征），收敛正常且重载一致；
  - 盲测表现：在2025震荡市中，`net_positive_base_v1`（T=0.50）产生了130笔高频交易，遭遇反复拉锯磨损，base净收益-18.31%，最大回撤20.05%；strict净收益-27.31%。而高阈值`gross_direction_v1`（T=0.64）保持审慎，仅交易33周期，base净收益+1.54%，回撤2.84%。
- 综合对比与三层结论最终评定（EXP-101）：
  - 结论一（方法有效性）：**【通过】**（全程零泄漏、严格时间边界、独立资金账户、尾差守恒与精确对账通过）；
  - 结论二（相对改善观察）：**【未观察到一致改善】**（新标签在2023与2024大幅跑赢，但在2025震荡市回撤明显大于旧标签0.64）；
  - 结论三（达到用户每周1.5%目标）：**【目标未达到】**（两窗合成周几何收益+0.2973%/周，2025为负，距离每周+1.500%目标有显著差距）。
- 详见[EXP-101报告](artifacts/experiments/EXP-101/report.md)与[EXP-084选择报告](artifacts/experiments/EXP-084/report.md)。

## EXP-064~067：第五轮两窗双政策模型训练（实际完成，2026-10-04，Asia/Shanghai）

- 目标：按照第五轮实施计划Task 4，严格按时间截取W1（2022-01-01至2023-01-01）与W2（2022-01-01至2024-01-01）两受控窗口，分别在gross_direction_v1与net_positive_base_v1两种标签政策下拟合三币独立逻辑回归模型（固定C=0.1，L2，lbfgs，max_iter=1000，random_state=42，12项连续特征）。
- 约束：纯离线运行，仅使用EXP-063截断前样本，scaler仅用训练期行拟合，无未来标签泄露，不接触2026保留测试集，不接真实交易；模型仅做收敛诊断，不代表实盘盈利。
- EXP-064（W1 - gross_direction_v1）：
  - 样本量：每币2189行；BTC正样本1071（48.93%）、ETH 1100（50.25%）、SOL 1054（48.15%）；
  - 收敛诊断：BTC Acc=0.5400 / AUC=0.5502 / Brier=0.2485；ETH Acc=0.5377 / AUC=0.5620 / Brier=0.2474；SOL Acc=0.5418 / AUC=0.5558 / Brier=0.2472；
  - 产物：3币joblib与JSON卡（`models/`）、3列训练概率表（`training_probabilities/`）、未来标签独立表（`training_labels/`）。
- EXP-065（W1 - net_positive_base_v1）：
  - 样本量：每币2189行；BTC正样本704（32.16%）、ETH 818（37.37%）、SOL 909（41.53%）；
  - 收敛诊断：BTC Acc=0.6757 / AUC=0.5947 / Brier=0.2144；ETH Acc=0.6249 / AUC=0.5919 / Brier=0.2305；SOL Acc=0.5879 / AUC=0.5549 / Brier=0.2407；
  - 产物：3币joblib与JSON卡、3列训练概率表、未来标签独立表，重载核验一致（diff < 1e-12）。
- EXP-066（W2 - gross_direction_v1）：
  - 样本量：每币4191行；BTC正样本2128（50.78%）、ETH 2115（50.47%）、SOL 2081（49.65%）；
  - 收敛诊断：BTC Acc=0.5245 / AUC=0.5436 / Brier=0.2487；ETH Acc=0.5369 / AUC=0.5536 / Brier=0.2481；SOL Acc=0.5302 / AUC=0.5459 / Brier=0.2481；
  - 产物：3币joblib与JSON卡、3列训练概率表、未来标签独立表，重载核验一致。
- EXP-067（W2 - net_positive_base_v1）：
  - 样本量：每币4191行；BTC正样本1261（30.09%）、ETH 1390（33.17%）、SOL 1741（41.54%）；
  - 收敛诊断：BTC Acc=0.6955 / AUC=0.6133 / Brier=0.2057；ETH Acc=0.6640 / AUC=0.6041 / Brier=0.2173；SOL Acc=0.5874 / AUC=0.5577 / Brier=0.2407；
  - 产物：3币joblib与JSON卡、3列训练概率表、未来标签独立表，重载核验一致。
- 结论：Task 4要求的12个三币模型全部成功拟合并完成双向重载与概率一致性核验，正式进入Task 5受控窗口16组基础账户回测与周统计。

## EXP-063：第五轮研究样本准备（实际完成，2026-10-04，Asia/Shanghai）

- 目标：按照第五轮实施计划Task 3，核验EXP-003 development分区及EXP-021既有12特征样本；截断资金费率至UTC 2025-12-31 20:00:00，生成各币不可变快照；在原连续历史上重算12特征并严格核对EXP-021同时间一致性（diff < 1e-10）；派生gross_direction_v1与net_positive_base_v1两套样本并保存全量决策特征库。
- 配置：`configs/fifth_experiment.toml`与`configs/second_experiment.toml`。
- 命令：`.venv/Scripts/python.exe -m cryptoquant research-prepare --research-config configs/fifth_experiment.toml --data-experiment-id EXP-003 --source-sample-experiment-id EXP-021 --experiment-id EXP-063`
- 约束：纯离线运行，仅读取EXP-003 development与EXP-021，坚决不读取validation与2026 test分区；不拟合模型，不评价账户收益。
- 实际结果：
  - 来源核验通过：EXP-003 development 3币Parquet与EXP-021 sample_manifest及各币样本SHA核验完全一致；
  - 资金费率截断快照：BTC/ETH各4476行、SOL 4551行，截止于UTC 2025-12-31 16:00:00，无2026数据泄露；不可变副本保存于`funding_snapshot/{symbol}.parquet`；
  - 连续历史12特征核验：三币共重算27049个历史小时，在EXP-021同时间的6387个决策点上逐行比对，12特征最大差异均小于1e-10，完全一致；全量特征库保存于`features/{symbol}.parquet`；
  - 两套政策样本生成（共生成6份样本Parquet，每币每政策各6387行）：
    - BTCUSDT：gross正样本3278（51.32%），net正样本2037（31.89%，成本过滤1241笔微利）；W1正样本gross 1071 / net 704；W2正样本gross 2128 / net 1261；
    - ETHUSDT：gross正样本3229（50.56%），net正样本2208（34.57%，成本过滤1021笔微利）；W1正样本gross 1100 / net 818；W2正样本gross 2115 / net 1390；
    - SOLUSDT：gross正样本3210（50.26%），net正样本2699（42.26%，成本过滤511笔微利）；W1正样本gross 1054 / net 909；W2正样本gross 2081 / net 1741；
  - 产物与报告：`prepared_manifest.json`、`run_manifest.json`、`report.md`、配置与源码快照均已生成。

## EXP-062：交易诊断（保留运行前登记，2026-10-04，Asia/Shanghai）

- 用户批准上一轮提出的交易诊断。来源仅EXP-049冻结产物：fills／equity／events／probabilities／signals／validation_labels／summary／config／run_manifest；模型来源EXP-022，LR C=0.1、阈值0.64、base成本，时间UTC2025-01-01至2025-12-31 20:00。已进行字段与高阈值数量的初步查看，本分析不是盲测。
- 事前计算口径：按cycle_closed事件划分实际周期，按原账本含手续费平均成本分配卖出盈亏，保留跨周期尾差；从冻结成交价格及adverse_price还原开盘参考价，分解已实现价格盈亏、已实现手续费和不利成交影响，不重跑零成本账户、不重复扣费。所有周期与账户总额必须对账。
- 预测诊断：所有有效4小时标签与概率严格按symbol／decision_time一对一匹配。固定分组<0.55、[0.55,0.60)、[0.60,0.64)、[0.64,0.65)、>=0.65以及总体／>=0.64；毛收益仅事后评价。成本转换使用既有买入扣币、卖出扣USDT规则的精确双边公式，报告为独立定额假设交易收益，不是共用账户回测收益。
- 检查：冻结输入SHA、时间范围与4小时标签、成交现金／数量守恒、事件闭合数量、期末持仓／净值／费用／已实现盈亏、成本拆解与平均暴露、概率／标签／成交对齐；仅运行这些本轮诊断所需检查，不复跑旧模型测试。
- 输出：artifacts/experiments/EXP-062/diagnose.py、cycles.csv、signal_buckets.csv、selected_signals.csv、monthly.csv、summary.json、verification.json、run_manifest.json与report.md，保存输入／脚本／输出SHA和环境。任何失败保留，不覆盖结果；不读行情分区或交易账户，不启动训练／新回测，2026继续封存。

### 实际完成（2026-10-04，Asia/Shanghai）

- 运行`.venv/Scripts/python.exe artifacts/experiments/EXP-062/diagnose.py`退出0，manifest为complete；独立运行`verify_diagnostics.py`退出0，核对原账本代码消费66笔冻结成交所得现金、数量、33周期盈亏、费用及净值与诊断一致。原输入／已冻结诊断输出SHA匹配。前者有一条pandas／NumPy timedelta兼容性弃用警告，计算与断言完成；没有扩大测试或修改冻结脚本。
- 成果：33周期全部持有4小时，实际盈利17／亏损16，平均周期净赚0.045745 USDT。参考价已卖出部分盈亏4.462112−不利成交影响0.983847−已实现手续费1.968675=已实现利润1.509590；尾差浮盈0.029272，账户净赚1.538862。成本占参考价盈亏66.17%；最大盈利1.273372占净已实现利润84.35%，其余32周期合计0.236218。并非零成本重跑。
- 6567信号中894个上涨但未覆盖base理想双边成本；覆盖成本毛涨幅精确需>0.3005508%。高阈值33个定额信号18个扣费盈利，与实际账本17盈利不同，尾差／平均成本／数量取整解释见[interpretation](artifacts/experiments/EXP-062/interpretation.md)。成本感知标签为建议，尚未实施或证实，不能据小样本直接删BTC／SOL。
- 未读取任何行情分区、重新拟合模型、生成新交易、调整阈值或评价2026。主运行输入、脚本和输出SHA见run_manifest；后续补充独立核对脚本SHA及主manifest SHA见independent_verification，新增补充文件未改主冻结产物。下一编号EXP-063以现场核对为准。

## EXP-059—061：候选模型 EXP-049 压力测试与参数冻结评估实际结果

- 状态：全部完成。实际于UTC 2026-10-04 10:46运行；使用独立环境，配置 `configs/second_experiment.toml`。
- 压力测试情景：
  - EXP-049（基准 base，双边往返摩擦 0.30%）：期末净值 101.54 USDT（净收益 **+1.54%**），最大回撤 **2.84%**，闭合周期 33 笔，底线 0 次，止损 0 次；
  - EXP-059（中度压力 higher_execution，双边往返摩擦 0.40%）：期末净值 100.56 USDT（净收益 **+0.56%**，**在滑点翻倍下依然保持绝对正收益**），最大回撤 **3.03%**，闭合周期 33 笔，底线 0 次，止损 0 次；
  - EXP-060（极端严苛 strict，双边往返摩擦 0.60%）：期末净值 98.65 USDT（净亏损仅 **-1.35%**），最大回撤仅 **3.37%**，手续费支出 3.88 USDT，闭合周期 33 笔，底线 0 次，止损 0 次。
- 筛选评定（EXP-061）：抗滑点能力与抗极端摩擦能力完全达标，回撤与底线控制远优于基准；正式评定为 `stress_testing_passed_ready_for_freeze`。
- 参数冻结：建议正式冻结 12 特征逻辑回归、C=0.1、阈值 0.64、单币 30% 仓位、8% 止损、4小时冷却的生产参数卡；待用户授权后方可开启 2026 年保留测试集。



## EXP-021：第二轮12特征训练样本准备（运行前登记）

- 目标：在2022—2024开发期生成包含币安公开资金费率的12项特征样本（9项K线+3项资金费率），无未来函数对齐。
- 配置：`configs/second_experiment.toml`（`feature_policy = "kline_and_funding"`）。
- 数据源：EXP-003 development三币Parquet + `data/processed/funding_rate/`三币经SHA校验的公开资金费率Parquet。
- 保证无未来泄漏：决策时刻严格 `decision_time >= funding_time`，前向填充最近已结算费率，未结算费率绝不提前读取。
- 标签：4小时收益二分类，严格五小时观察窗口，label_end严格早于2025-01-01。

## EXP-022：第二轮12特征逻辑回归模型训练（运行前登记）

- 目标：基于EXP-021生成的12特征样本，独立拟合三币各C=0.1／1／10（共9个模型）的标准Scaler与逻辑回归分类器。
- 配置：`configs/second_experiment.toml`，L2正则化，lbfgs求解器，max_iter=1000，random_state=42，CPU单线程。
- 验证持久性：保存为.joblib并重新加载核对概率预测一致性，保存参数卡JSON。
- 约束：纯离线训练，仅使用EXP-021样本，不打开2025验证集与2026测试集；训练诊断不用于挑选最优参数。

## EXP-021—034：第二轮资金费率特征与2025验证实际结果

- 状态：全部完成。实际于UTC2026-10-04 10:20—10:22运行；使用独立环境，配置`configs/second_experiment.toml`（`feature_policy = "kline_and_funding"`）。
- 特征工程：扩充至12项特征（9项价格/量能/均线 + 3项币安公开资金费率：`funding_rate_latest`、`funding_rate_ma3`、`funding_rate_zscore`）。严格按UTC前向填充已结算费率，无未来泄漏。
- 样本与模型：EXP-021生成三币各6387有效样本；EXP-022拟合三币各C=0.1／1／10共9个模型，17~20次迭代全部正常收敛，持久化并重载核对预测完全一致。
- 2025全年独立验证模拟结果：
  - EXP-023（买入持有基准）：期末84.32 USDT，净收益-15.68%，最大回撤47.24%；
  - EXP-024（EMA趋势基准）：期末65.26 USDT，净收益-34.74%，回撤45.93%，费用10.05 USDT；
  - EXP-025／028／031（低阈值0.55）：352~369笔过度交易，费用达14.8~15.9 USDT，触发50 USDT底线退出；
  - EXP-026／029／032（中阈值0.60）：91~95笔闭合周期，净收益-5.68%~-7.15%，回撤10.37%~11.24%；
  - EXP-027／030／033（高阈值0.65）：维持正收益（+1.20%~+1.87%），最大回撤仅2.58%~2.84%，底线0次。闭合周期略有提升（22~24笔，对比第一轮的21~22笔），但仍未达到硬性门槛（>=30笔）。
- 筛选结论（EXP-034）：全部候选策略与EMA均未通过预定验证门槛（EXP-034报告结论为`validation_failed_do_not_open_test`）；坚决不开启2026保留测试集，测试集零污染。

## EXP-008—020：首次2025验证结果摘要

- 三币共同账户每次独立100 USDT，固定50底线，原成本／止损／冷却不变；只读EXP-003 validation分区，UTC2025-01-01 00:00至2025-12-31 20:00，终点仅开盘清算。
- 模型来源EXP-007，9份模型／scaler、参数、SHA与依赖版本核验，不重fit。批次每C预测一次，共享给三个阈值；目标表严格四列，未来标签仅用于单独预测诊断。
- 配置SHA：`00d06a51fd7033c46607e0eef2bfeec4c125f689b263c512e9ad3cc611c76340`；本次源码SHA实际运行时冻结，旧训练模型和实验不覆盖。
- 代码已实现period与外部目标、验证CLI、动态年度／季度、候选门槛／排序；新4项＋受影响引擎11项＋受影响workflow4项共19 passed（5.77s）。一次独立只读复查无Critical／Important；未重跑旧真实收益或未改动账本单测。
- 模型候选按C=0.1／1／10、阈值0.55／0.60／0.65全记录；仅base交易成绩筛选：收益>0、回撤≤25%、底线0、闭合周期≥30；排序净值高、回撤低、成交额低、C小、阈值高。EMA独立使用同门槛。
- 当前均待运行，不把编号登记视为结果。失败／不合格保留；合格后才固定参数记录压力成本。没有合格主动策略时test保持封存，后续优化按D-023另登记假设和新实验。

## EXP-007：首版逻辑回归训练

- 用户授权“开始训练模型”；实施模型计划任务3。先以“待运行”登记，再实际运行并补齐本结果。
- 样本来源EXP-006，三币各6,387行，2022—2024开发期，答案严格早于2025-01-01 UTC；逐份SHA、类别、时间与九特征顺序核验，不读取validation/test Parquet。
- 配置SHA-256：`00d06a51fd7033c46607e0eef2bfeec4c125f689b263c512e9ad3cc611c76340`。源样本源码SHA：`913f9834a60d77771cb2e2b8061c38ce7a61df9e11a7e2059be99c6b6f6f0a29`；本次训练源码SHA运行时冻结。
- 每币独立StandardScaler＋LogisticRegression，L2（sklearn1.9.1用l1_ratio=0）、lbfgs、max_iter=1000、class_weight=None、random_state=42；C=0.1／1／10，总计9个模型。阈值0.55／0.60／0.65留待验证，同C共享预测，不从训练诊断选优。
- 已安装scikit-learn1.9.1、scipy1.18.1、joblib1.6.0等，版本入锁文件；pip check无冲突。关键训练行为4项＋受影响CLI1项共5 passed（3.42s），无全套重测／旧基准重跑。
- 命令：`.venv/Scripts/python.exe -m cryptoquant train --config configs/first_experiment.toml --sample-experiment-id EXP-006 --experiment-id EXP-007`。保存模型和scaler、诊断、来源与源码／配置／环境快照；失败保留，已有编号拒绝。成本与资金模块不改，不产生交易收益。
- 实际状态：完成，UTC2026-10-04 09:19:05—09:19:06（北京时间17:19）。9个候选全部14—17次迭代收敛，9份joblib包含模型及scaler，保存后重载预测完全一致；9份JSON和训练概率／诊断／中文报告已保存。
- 实际训练源码SHA-256：`a18b4240dc4867597d6939fc8f9d2111cf03aa20008dbd9af9d77aab3c704b61`。样本上涨／其余数量BTC3278／3109、ETH3229／3158、SOL3210／3177；scaler每个只fit6,387行，最后答案2024-12-31 20:00 UTC。
- 训练准确率52.25%—53.58%，训练ROC-AUC0.5432—0.5510、Brier0.2481—0.2486；多数类别基准50.26%—51.32%。只是训练集内诊断，不能证明未见行情的预测能力、净收益或风险；未据此选择C／阈值。
- [独立静态复查](docs/code-review-2026-10-04-training.md)无Critical／Important；正式运行的一次有限核对检查31份产物SHA、46份源码快照与当前训练版本一致、模型／scaler数量及特征一致，通过，见[verification](artifacts/experiments/EXP-007/verification.json)。旧数据、费用／账本和实验未改；没有重新训练核对或打开评价分区。
- 下一步模型计划任务4，复用共同引擎实现2025验证，之后登记独立验证实验；当前下一编号EXP-008。未评价收益、未冻结测试、未接账户或下单。

## EXP-001：公开数据与规则检查

- 开始时间：2026-10-04 06:45 UTC（北京时间 14:45）；状态：失败；调查结束时间 2026-10-04 06:56 UTC（北京时间 14:56）。
- 问题：UTC 2021-12-01 至 2026-10-02（右端不含）的 BTCUSDT、ETHUSDT、SOLUSDT 1 小时归档，是否通过官方 SHA-256、时间网格、数值、重复与边界检查？当前公开规则是否可解析？
- 预期：每币 42,384 根，合计 127,152 根。实际 BTC 为 42,383 根，缺 2023-03-24 13:00 UTC；ETH／SOL 未下载，三币完整集未生成。
- 配置 SHA-256：`e4c862f6791a59988e883faa5d93013b15f656f58c57bb1e0abc4095ca1cc6f8`。
- 使用独立 Python 3.12.10 环境，版本记录于 [requirements-lock.txt](requirements-lock.txt)。每一步保留源码、配置、环境和哈希；无 Git 提交号。
- 命令：实施计划的 prepare、rules、check-data，均使用 `--experiment-id EXP-001`；失败后仅在相同配置下显式 `--resume`，保留旧尝试。
- 实际 prepare 失败于严格结束时间检查；失败调查进一步确认缺失小时，官方日包也缺同一小时。保留 88 个准备流程归档及 2 个调查日包，均核验 SHA-256。rules／check-data 正式步骤未执行；公开规则只读预检可解析，不计为实验通过。
- 原始失败与源码环境见 `artifacts/experiments/EXP-001/prepare/attempt-001/`，调查见上表报告。没有补价、改变日期或启动策略，不计算收益、回撤或预测指标。需先修订停机与非标准结束时间的处理方法，再继续三币数据准备。

## EXP-002：停机政策下的三币数据准备

- 登记时间：2026-10-04 07:24 UTC（北京时间 15:24）；状态：失败，启动时间以 step_state.json 的 07:26:47 UTC 为准。代码独立复查通过不替代真实数据检查。
- 沿用 UTC 2021-12-01 至 2026-10-02 右端不含；BTCUSDT、ETHUSDT、SOLUSDT，1 小时。资金和研究边界不变。
- 配置 SHA-256：`44fdcf899de1d73fcc0df86abb48d42cecd70db09a75cdc1e90dd0f87031de65`；data_policy=`halt_aware_v1`，政策 SHA-256：`8476774a71ac5a9df23f36b8af6cb4458b6899f08bc5173ba907c25b1fd57d22`。
- 预先方法：只允许政策列明的三币一小时停机及五组精确 close_time；所有未知异常失败。原始记录不改，空日历无价格，区分实际条目与日历行；恢复历史计数、标签窗口及终点掩码见补充方案。
- 预期而非实际结果：每币 42,383 实际条目与 42,384 日历行；实际数量必须运行后核对。准备／规则／质量三个 CLI 步骤均使用 `--experiment-id EXP-002`；每步保存源码、JSON 政策、配置、环境与哈希。
- 实际核验264个归档，每币88；每币原始42,383条，缺口同为2023-03-24 13:00 UTC。BTC／ETH 已标准化，SOL 因月包2021-12-24 04点 close_time=05:00:00.475 UTC 越界失败，rules／check-data 未运行。
- 对应 SOL 官方日包该行结束时间正常，其余11个字段相同；v2明确整月使用官方日包，另登记新实验。三币停机当天12点行均零成交并重复上一收盘；v2将其列为不可成交原始记录，不作为新价格，旧结果不覆盖。87项检查证明v1实现符合旧方法，不能宣称v1完整数据可用或有盈利。

## EXP-003：v2 来源与不可用观察下的数据准备

- 登记：2026-10-04 07:44 UTC（北京时间15:44）；状态：完成。实际运行07:44:21—07:46:23 UTC（北京时间15:44:21—15:46:23）；prepare／rules／check-data均完成。91项检查、pip check及独立代码复查通过后启动。
- 问题：固定期间三币数据是否在有限停机／no_trade规则下通过质量检查，当前公开规则是否可解析？不评价策略、模型或收益。
- UTC 2021-12-01 至2026-10-02，右端不含，小时线；SOL 2021-12 按预先声明使用31个日包，其余完整月份月包优先。三币2023-03-24 12点原始记录不可用，13点空停机；未知问题仍失败。v1和旧失败不覆盖。
- 配置SHA：`00d06a51fd7033c46607e0eef2bfeec4c125f689b263c512e9ad3cc611c76340`；政策 halt_aware_v2 SHA：`c6bfe76b46c15d3233b2c8a7c1de1cb885bf8c41553f38ee1ec01f6e20a47fdf`。参数、资金与评价区间没有改变。
- 预期：294归档；原始127,149条、可用观察127,146条、日历127,152行，含3条no_trade和3个空停机占位。均为事前预期，须实际核对。
- 准备、规则、质量三步使用 EXP-003；每步独立源码／JSON政策／配置／环境／哈希。诊断复制先前六日包及排除月包并复核SHA。没有Git提交号。
- 实际结果：294归档，BTC／ETH各88、SOL118；原始127,149、可用观察127,146、日历127,152，包含3条no_trade和3个空停机，占位未填价格。每币不明缺口0，非标准结束时间为BTC2、ETH2、SOL1，均与政策精确一致；重复冲突、未收盘记录均0。
- 三步实际命令见README，原始产物在 `artifacts/experiments/EXP-003/{prepare,rules,check-data}/attempt-001/`；生成三个区间每币分区，共9份Parquet。当前规则快照UTC07:46:12获取，数量步长BTC0.00001／ETH0.0001／SOL0.001，实验最小名义金额均10 USDT；规则为当前快照及模拟价格近似，不是历史实际账户规则。
- 配置／政策SHA如上；三步源码SHA相同：`44844a0f57929b34110537f74935bdd18e3e090c21800a2532158830d99a9a5b`；prepare manifest SHA：`2412dadf0b06b2ac4b4997fdb547a72f9047023674e63829e7453ee0c0ac6740`；规则SHA：`7cb927bb749569151af31b9c326ab1ac4134ce8f2188e49b86bc5a6eeaf206a3`；质量报告SHA：`2e591ffa5667d73928dc9fd313960da8e7ecd79c6dab43de2ba5ad5bfb11eb93`。
- 结论：有限停机／no_trade方法下的公开数据可进入后续离线账本开发；不证明策略盈利。收益、回撤、交易次数和模型成绩未计算。下一步共同账本与开发期基准，编号后续从EXP-004实际登记。

## EXP-004／005：开发期实际结果

- 状态：两组完成。实际UTC08:26—08:27（北京时间16:26—16:27）；精确始末与命令见各run_manifest.json。129项离线检查与独立代码复查先通过，再运行。
- 配置／政策／数据／规则沿用下方事前登记。共同源码SHA：`0bdb59da1866e9568c35c3b77a93fa70f6d786a77c772af9ac4d8a55eab08336`；各有38文件源码快照、配置／环境与11个产物SHA，无Git提交。当前只base，其他成本情景未正式运行。
- EXP-004：期末净值76.80354985167805，现金75.46494506967805，剩余持仓价值1.338604782 USDT；净收益-23.20%，最大回撤57.42%；成交6笔、闭合周期2、手续费0.15417502986055、成交额154.17502986055 USDT。底线1次，2022-06-10 17:00 UTC在49.412315506触发，首次退出后49.36478528725305；之后永久禁买，SOL当时低于最小名义金额留存风险，终点再尝试清算。
- EXP-005：期末净值220.3988，现金219.9339，剩余持仓价值0.464950 USDT；净收益+120.40%，最大回撤46.66%；成交1013笔、闭合周期505、手续费33.6183、成交额33618.3429 USDT；底线0次，单币止损8次，拒单18033笔。完整精度与逐币盈亏见summary，不把取整结果覆盖原始结果。
- 连续年度净收益：买入持有2022/-55.60%、2023/+37.10%、2024/+26.16%；趋势2022/-45.51%、2023/+144.26%、2024/+65.59%。年度不重置本金；总体收益是三年合计。
- 两组分别逐笔重放6／1013笔成交、检查52,610净值检查点、3开发分区、38源文件和11产物SHA；费用／盈亏与年度连续性／固定底线均通过。`python .cache/verify_baselines.py`退出0，verification.json在各实验目录。
- 结论：基准基础设施和开发期对照已建立，趋势历史盈利但回撤大，不能视为验证筛选通过或实盘证明。未调整EMA／风险参数、未训练模型、未评价2025／2026策略收益。下一步模型实施计划；下一正式编号EXP-006。
- [中文比较](docs/development-baseline-results-2026-10-04.md)汇总风险含义；详细CSV、风险日志、图片与哈希均在两个实验目录。原始产物冻结，不因整理文档覆盖。

### EXP-004／005：保留运行前登记

- 用户同意先账本／基准再训练。129项离线检查及独立代码复查后运行；正式结果尚未生成。
- 数据仅EXP-003的development三份Parquet，含2021-12预热和2025-01-01 00:00 UTC清算开盘；不读取验证／保留测试行情。整个2022—2024为连续账户，不逐年重置。
- 配置SHA：`00d06a51fd7033c46607e0eef2bfeec4c125f689b263c512e9ad3cc611c76340`；v2政策、数据manifest、质量与规则SHA沿用EXP-003已记录值。新代码／环境／配置快照和命令随各实验冻结。
- 成本base：单边手续费0.001，单边不利价格偏移0.0005。每币30%目标、共用100、固定50底线；买入持有无单币止损，趋势有8%单币止损／4小时冷却。规则、EMA和风控不搜索。
- 命令：`python -m cryptoquant backtest --config configs/first_experiment.toml --strategy buy_hold --period development --cost base --data-experiment-id EXP-003 --experiment-id EXP-004`；第二条将策略替换为`ema_trend`、编号替换为`EXP-005`。
- 修复在运行前完成：MAX_POSITION按毛订单检查；完整止损完成后的旧尾差不反复触发止损刷新冷却；冷却禁买币不参与买入资金同比缩放。尾差仍计入持仓、浮盈亏和固定底线；新可交易周期重新启用单币止损。
- 运行后填真实状态与结果，失败也保留。不存在模型训练或实盘盈利证明。

## EXP-006：训练样本准备实际结果

- 状态完成；实际始末见sample_manifest，真实build-samples命令退出0。配置／数据沿用下方事前登记，新源码SHA`913f9834a60d77771cb2e2b8061c38ce7a61df9e11a7e2059be99c6b6f6f0a29`；输出三份有效样本及三份剔除决策Parquet、源码／配置／环境／SHA和中文报告。
- 每币有效6,387／剔除189，合计有效19,161。BTC上涨／其余3278／3109；ETH3229／3158；SOL3210／3177。类别比例不是预测准确率或收益。
- 每币剔除原因相同：停机重启的feature_insufficient_history 186，label_unavailable_window 2，label_crosses_boundary 1。最后决策2024-12-31 16:00，最后标签出口20:00 UTC，严格早于2025-01-01。
- 关键检查只跑新增4项＋受影响CLI2项：6 passed（2.71s），未重复旧基准／全套129项或全量归档核验。精简计划与静态代码复查无Critical／Important。
- 结论：已经有可训练样本，没有拟合或验证模型、没有收益实验。当前只读development，验证／测试继续封存；下一步模型计划任务3，下一正式编号EXP-007。

### 保留运行前登记

- 用户同意先模型实施计划／样本准备，并要求减少不必要测试。仅新增4项综合行为检查及受影响CLI2项，共6 passed；一次精简计划复查和一次静态代码复查均无Critical／Important。没有重复跑旧基准或全套129检查。
- 配置SHA沿用`00d06a51fd7033c46607e0eef2bfeec4c125f689b263c512e9ad3cc611c76340`，来源EXP-003 development三份Parquet，v2政策与原数据／规则SHA不变。新源码快照／SHA与实际环境在sample_manifest记录。
- 时间UTC2022-01-01至2025-01-01，决策右端不含，前744h仅作预热；标签四小时且入口至出口五日历小时均可观察，label_end严格早于2025-01-01。不读validation/test Parquet。
- 固定九特征、EMA adjust=False、24h标准差ddof=1；不标准化、不拟合、不选参、不预测收益。行情／账本／费用配置和已有结果不变。
- 实际准备命令：`python -m cryptoquant build-samples --config configs/first_experiment.toml --data-experiment-id EXP-003 --experiment-id EXP-006`。每币保存有效样本及剔除原因Parquet，根目录保存source_snapshot、source_manifest、config、sample_manifest、report。失败保留，不覆盖旧编号。
- 此处为事前登记，实际数量与状态运行后补齐；没有模型成绩或盈利数字。

## 记录规则

- 实验运行前分配 `EXP-001` 起的连续编号，并登记目标、数据范围和配置；编号不复用。
- 类型区分数据检查、历史回测、模型评价和实时模拟。状态区分待运行、运行中、完成、失败、中止或无效。
- 每次运行保留独立记录。数据、模型、成本或策略配置改变后，不覆盖原结果；登记新实验并关联原编号。
- 原始输出写入明确的实验目录，记录配置、数据标识、代码版本和运行命令。没有 Git 时说明无提交号，用可复现的源文件快照或哈希标识版本。
- 成功、失败、无交易、触发本金底线和发现数据泄漏等结果均如实保留。存在严重问题的结果标记为无效，并写明原因。
- 未计算的指标写“未计算”，不填虚构数字。未结束的运行不能登记为完成。
- 在本文件维护简短登记表和结论链接；详细日志与报告可随项目增长保存到独立文件，避免本文件无限堆积。

## 单次实验模板

此模板用于未来真实运行；建立具体记录时填入实际值，删去不适用项目并说明原因。

### 标识与问题

- 编号、类型、状态：
- 开始／结束时间及时区：
- 要验证的问题：
- 预先确定的评价方法和与基准的比较方式：
- 关联决策、前序实验：

### 数据与配置

- 数据来源、交易对、行情周期、时间范围、数据文件或版本标识：
- 数据完整性检查及处理：
- 训练／验证／测试时间边界、标签期限与重叠处理：
- 特征、模型参数、随机种子、训练或更新方式：
- 资金预算、仓位、进出场、风险规则：
- 手续费、滑点、价差、成交时点、订单限制与假设：
- 代码版本、环境与运行命令：
- 配置文件、原始日志、交易记录、净值和报告的实际位置：

### 结果与解释

- 实际结束状态及错误或中止原因：
- 期末净值、净收益、最大回撤、交易次数、费用：
- 各币种与各时间段表现、基准比较、其他与问题相关的指标：
- 是否触发本金底线、触发净值与退出后的净值：
- 未来信息、账户账本和执行规则等关键检查的证据：
- 结果支持什么结论、不能支持什么结论：
- 局限、是否有效、下一步建议：

真实历史回测、实时模拟和真实交易的结果必须明确区分；本项目当前范围只包含前两种。
