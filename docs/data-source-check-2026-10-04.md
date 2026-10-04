# 币安公开数据更新核查

核查日期：2026-10-04（Asia/Shanghai）

## 核查问题与方法

用户发现所引用 GitHub 页面中的部分内容显示较早的更新日期，询问数据能否继续用于研究。

本次只读查询了 GitHub 最新提交接口、币安官方公开数据说明，以及公开 S3 文件目录。没有下载或解压行情 ZIP，没有建立训练数据集，也没有执行模型实验。

## 实际观察

### GitHub 仓库

- 仓库：[binance/binance-public-data](https://github.com/binance/binance-public-data)。
- 查询：[最新提交接口](https://api.github.com/repos/binance/binance-public-data/commits?per_page=1)。
- 返回最新提交时间：2026-09-30T12:21:12Z。
- 提交：`f446ce3812bd4e5521f21faecd4ae3c6460e49fc`，消息 `Merge #506`。
- [对应提交页面](https://github.com/binance/binance-public-data/commit/f446ce3812bd4e5521f21faecd4ae3c6460e49fc)。
- 个别脚本、目录或历史修正记录的旧日期，不代表全部仓库内容或行情档案停在该日期。

### 1 小时现货 K 线文件

以下为实际返回的目录信息，发布时间使用 UTC；文件内容尚未检查。

| 交易对 | 月度目录最新行情月份 | 10 月日度目录最新行情日期 | 最新日包 LastModified（UTC） | 最新日包字节数 |
| --- | --- | --- | --- | --- |
| BTCUSDT | 2026-08 | 2026-10-03 | 2026-10-04T02:34:17Z | 1532 |
| ETHUSDT | 2026-08 | 2026-10-03 | 2026-10-04T02:34:19Z | 1478 |
| SOLUSDT | 2026-08 | 2026-10-03 | 2026-10-04T02:38:13Z | 1355 |

三个交易对的 2026 年 10 月目录均返回 10 月 1、2、3 日三个 ZIP，目录响应均为 `IsTruncated=false`。

月度目录使用前缀 `data/spot/monthly/klines/{SYMBOL}/1h/`，日度目录使用前缀 `data/spot/daily/klines/{SYMBOL}/1h/{SYMBOL}-1h-2026-10-`；调用 S3 ListObjectsV2，`max-keys=1000`。核查响应未被分页截断。

可复核的日度目录请求：

- [BTCUSDT 日度目录](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?list-type=2&max-keys=1000&prefix=data%2Fspot%2Fdaily%2Fklines%2FBTCUSDT%2F1h%2FBTCUSDT-1h-2026-10-)
- [ETHUSDT 日度目录](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?list-type=2&max-keys=1000&prefix=data%2Fspot%2Fdaily%2Fklines%2FETHUSDT%2F1h%2FETHUSDT-1h-2026-10-)
- [SOLUSDT 日度目录](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?list-type=2&max-keys=1000&prefix=data%2Fspot%2Fdaily%2Fklines%2FSOLUSDT%2F1h%2FSOLUSDT-1h-2026-10-)

## 官方说明与处理提醒

[官方 README](https://github.com/binance/binance-public-data#readme) 说明：

- 实际行情在 `data.binance.vision`，按日或按月归档；GitHub 主要提供说明和下载辅助脚本。
- 日包通常次日提供，月包在当月第一个星期一提供。2026-10-04 是星期日，按照该安排 9 月月包预计于 10 月 5 日发布；这是发布时间安排的推断，不是已经发布的事实。
- 现货归档数据从 2025-01-01 起时间戳采用微秒。混合较早数据时要按实际单位正确转换，不能一律按毫秒读取。
- ZIP 对应的 `.CHECKSUM` 可用于检查下载文件完整性；历史文件可能被修正，需要保存数据版本或校验值。

## 结论及限制

- 本次观察证明上述交易对的公开日度档案仍在发布近期文件，可以保留为候选研究数据源。
- 尚不能据此保证每个 ZIP 内容正确、历史数据完整或所有周期一致；正式准备数据时仍需下载、校验并检查时间连续性与字段。
- 检查结果是 2026-10-04 的快照，未来使用时应重新核实，不把“最新日期”当作固定配置。
- 尚未选择或实现下载器。老脚本的时间处理、接口和依赖需要评估，不能因为数据源在更新就默认老脚本全部可用。
