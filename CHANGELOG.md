# 更新日志

本文件记录本项目的所有重要变更。
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/) `主版本.次版本.修订号`：

- **主版本**：有不兼容的改动时 +1（例如改了 JSON 字段契约、报告板块顺序）
- **次版本**：向下兼容地新增功能时 +1（例如新增一套皮肤、新增一个脚本）
- **修订号**：只修 bug、改错字时 +1

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [1.1.0] - 2026-09-26

新增**付费上架能力**：可作为 SkillHub 的 Pay Skill 上架，按报告篇数计费。

### 新增

- **支付宝 AI 按量付费（HTTP 402 协议）接入层**（`scripts/skillpay/`），完整实现四步编排
  `probe → pay → complete → ack`：
  - **402 账单下发**：无有效 `Payment-Proof` 时返回 HTTP 402 + `Payment-Needed` 响应头，
    Base64URL 编码、含 `protocol` / `method` 两段与 RSA2 `seller_signature`（本地签名，不请求支付宝）。
  - **携带凭证重试**：付款后用同一请求带 `Payment-Proof` 重试；凭证无效一律回到 402。
  - **验付调用**：`alipay.aipay.agent.payment.verify`，并校验 `active` / 金额 / `out_trade_no` /
    `resource_id` / `trade_no` 未重复履约 / 本地订单状态。
  - **履约确认**：`alipay.aipay.agent.fulfillment.confirm`，确认成功后才标记 `FULFILLED`，
    失败返回 502 且允许用同一凭证重试。
  - **订单持久化与幂等**：SQLite 订单库，`BEGIN IMMEDIATE` 原子占位 + `trade_no` 唯一索引，
    同一订单重复携带 `Payment-Proof` 不重复发放资源。
- **按篇计费**：账单金额 = 单价（默认 `0.01` 元/篇）× 本次请求篇数；单次调用篇数上限
  `quantity_cap`（默认 2500，即上限账单 25.00 元）防止误传目录导致天价账单；金额用 `Decimal` 定点计算。
- **本地 HTTP 服务**（`server.py`）返回真实 402 状态码与响应头；**命令行入口**（`cli.py`）
  暴露 `probe` / `pay-info` / `complete` / `ack` / `status` / `selftest` 六个子命令。
- **离线自测**（`selftest.py`）：生成 RSA 密钥 + mock 网关，跑通完整链路与全部失败分支，共 **48 项断言**。
- **接入规范文档** [`references/skillpay.md`](references/skillpay.md)：协议字段、五项必做控制、
  配置环境变量、沙箱↔生产切换、安全红线、上线前核对清单。

### 说明

- 付费层对原有批改能力**零侵入**：不启用付费时，直接跑 `scripts/render.py` 的行为与 1.0.0 完全一致。
- 新增可选依赖 `pycryptodome`（仅在需要 402 签名时安装；也可用 `cryptography`）。
- `.gitignore` 新增排除 `skillpay.local.json`、`state/`、`*.pem`、`*.key`、`*.db` ——
  商家私钥与订单库绝不入库。

---

## [1.0.0] - 2026-09-26

首次公开发布。

### 新增

- **完整批改流水线**：学生手写答题卡（JPEG 扫描件）→ 结构化 JSON → 11 个板块的个人报告（HTML + A4 PDF）。
  覆盖逐句批改、错误分析详情、情节分析、出彩表达、个性化提升、作文润色、学生佳句与场景词汇等板块。
- **班级批量与台账**（`scripts/aggregate.py`）：按班级聚合，产出 `班级台账.xlsx` ——
  `成绩台账`（学号／姓名／班级／得分／词数／语法错误数／卷面等级／问题标签／主要错误类型）
  与 `班级诊断`（得分分布、错误类型人次排行、各班均分）。
- **作业清单生成**（`scripts/manifest.py`）：按学号自动配对答题卡与已有批改报告，
  支持断点续跑（已存在的结果文件自动跳过）。
- **两套报告皮肤**（`--theme`）：
  - `default` —— 复刻目标报告样本的版式与配色（默认）
  - `apple` —— Apple 风格打印版：纯白纸 + 灰色圆角卡片 + 只描边的胶囊标题，**零暗底**，省墨不糊字
- **`--marks` 修订标记口径开关**：`theme`（跟随皮肤配色）／`strict`（强制规格内的灰底红字），
  让版式选择与修订标记规格解耦。
- **白名单打包脚本**（`scripts/pack_for_upload.py`）：供网页端手动上传 GitHub 使用，
  按白名单拷贝文件，学生数据不可能混入（GitHub 网页上传不读 `.gitignore`）。
- **`references/themes.md`**：两套皮肤的设计规范、`@page` 排版要点、模板占位符契约，
  以及新增一套皮肤的完整步骤。

### 说明

- **判划改口径**：学生自己划掉／涂改的词一律不转写、不计词数、不算错误；
  拿不准的一律按"被划掉"处理，不反复放大纠缠。
- **卷面三档判定的优先级**：第一优先级为字形（字体）规范性、字母大小一致性、间距一致性，
  划改类痕迹排在第三优先级、几乎不计入。
- **班级级内容**：`学生佳句` 与 `场景词汇` 同班共享、跨班不同；佳句取全班前 N 句，允许出现学生本人的句子。
- **不绑定任何具体题目**：原题前文、两段首句、情节梳理、场景词汇全部来自当次 `assignment.json`
  与该生实际作文；换一道题就换一份 `assignment.json`，Skill 本体不动。
- **不采集学生数据**：本仓库不含任何答题卡、报告或成绩数据，`.gitignore` 与
  `pack_for_upload.py` 的双重白名单已在源头拦截。
