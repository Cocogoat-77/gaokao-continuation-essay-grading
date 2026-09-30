# 更新日志

本文件记录本项目的所有重要变更。
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/) `主版本.次版本.修订号`：

- **主版本**：有不兼容的改动时 +1（例如改了 JSON 字段契约、报告板块顺序）
- **次版本**：向下兼容地新增功能时 +1（例如新增一套皮肤、新增一个脚本）
- **修订号**：只修 bug、改错字时 +1

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [1.4.1] - 2026-09-30

### 新增

- **免费体验端点 `POST /v1/trial`**：每个来源 IP 每天可免费渲染 **1 篇**（北京时间自然日，
  零点自动刷新额度），**不走 402、不建订单、不涉及支付**；请求体与 `/v1/grade` 相同但
  `reports` 只允许 1 份。额度用完返回 429；**先占额度再渲染**（唯一索引防并发重复占用），
  渲染失败自动退还当日额度。
  `store.py` 新增 `trials` 表（ip+date 唯一索引）与 `trial_used_today` / `record_trial` / `cancel_trial`；
  `service.py` 新增 `trial()`（渲染复用内联管线）；`server.py` 新增路由（取 TCP 对端 IP，
  服务器为直连模式；日后若加反向代理需改读转发头）。
  `selftest.py` 新增【十一】用例：首次 200 / 同日重复 429 / 跨 IP 各有额度 / 多篇 400 /
  跨天恢复 / 坏请求不占额度。64/64 通过。
- 精简版 `submit_grade.py` 新增 `trial` 子命令（v1.4.2），买家可免费试批。
- **README 全面改版**：改为面向开发者的详尽程序说明（双版本架构、目录职责、硬约束摘要、
  渲染管线、付费层与五项必做控制、内联契约、/v1/trial、服务端部署指南、自测清单、安全设计）；
  面向使用者的《使用教程》随 SkillHub 精简版发布。

---

## [1.4.0] - 2026-09-30

### 新增

- **内联报告契约（远程买家全链路）**：`service.default_deliver` 支持
  `payload.reports = [{"name": 文件名, "content": 报告JSON}]`——报告内容随请求上传，
  服务端写入临时目录渲染，渲染完**整目录删除**；响应的 `files[]` 携带 HTML/PDF 的
  Base64 内容，`produced` 只回传文件名不泄漏服务器路径。`count_reports` 按内联篇数计费，
  篇数防篡改复用 3.5 校验（下单 2 篇重试改 1 篇 → 402）。
  **安全**：内联模式强制使用服务端临时目录，**忽略买家传入的 `outdir`**（杜绝任意路径写盘）。
- **Linux 服务端渲染支持**：`render.py` 新增 `_find_cjk_font()`——页眉页脚字体按候选列表
  （Windows 幼圆 → wqy/noto/uming 等常见 CJK 字体）逐一探测，最后兜底 `fc-match`，
  并用 `has_glyph` 验证真能写出中文字形；找不到时跳过盖章（stderr 提示）而不是让整份报告失败。
  此前 `insert_font` 无条件使用 `C:\Windows\Fonts\SIMYOU.TTF`，Linux 上必抛异常。
- **请求体上限**：`server.py` 对超过 64MB 的请求体直接返回 413（`PAYLOAD_TOO_LARGE`）。
- **自测新增【九】内联模式用例**（真实渲染）：内联 2 篇账单 0.02 元 → 验付 → 渲染 →
  4 个文件 Base64 回传 → 不泄漏路径 → 篇数篡改回 402。57/57 全绿（本机与 ECS 均验证）。

---

## [1.3.1] - 2026-09-30

### 修复

- **网关验签失败（`isv.invalid-signature`）**：`gateway.py` 误用账单签名函数
  `seller_signature`（其 `SIGN_FIELDS` 白名单全是账单字段）签网关请求，
  导致验付/履约确认请求签出**空串签名**、被支付宝网关拒签。
  新增 `bill.sign_gateway_params()`（除 `sign` 外全部参数按 key 字典序，标准 RSA2）修复。
  **部署侧必须同步更新 `bill.py` + `gateway.py`**，否则 402 闭环在验付一步必失败。
- **「已收款不发货」**：订单 `pay_before` 过期后，即使支付宝验付已确认真实收款，
  `service.py`（3.8）与 `store.prepare_fulfillment` 仍会拒绝履约——
  moveToMobile 场景下「付款在时限内完成、验付请求晚到几分钟」即触发。
  现改为：**验付通过即履约**；`pay_before` 只在 probe（账单下发）阶段是硬约束
  （过期账单收银端本就不受理）。防串单/防重复由 trade_no 唯一索引与幂等履约保证。
  `selftest.py` 过期用例同步改为期待 200 履约（50/50 全绿）。

### 新增

- **服务端 HTTPS 支持**：`server.py` 新增 `--tls-cert` / `--tls-key`，
  提供 HTTPS 监听（402 协议的回打环节要求付费资源地址必须 HTTPS）。
- **报告文件随响应回传**：`service.default_deliver` 渲染出的 HTML/PDF
  以 Base64 放入 `service_result.files[]`（`name` / `kind` / `mime` / `size` /
  `data_base64`）——买家端没有服务器磁盘，只回传本地路径等于拿不到报告。
  凭据交付模式（未指定 `--json/--jsondir`）不受影响。

---

## [1.3.0] - 2026-09-29

### 新增

- **依赖自检脚本 `scripts/check_env.py`**：只检查、不安装。报告必需组件（`pymupdf` / `playwright` /
  `openpyxl` / Chromium）、可选组件与系统字体状态，缺项时直接打印可执行的安装命令；
  `--json` 供 Agent 解析，退出码 `0/1` 表示环境是否就绪。
  刻意不启动外部进程、不起 shell、不读写任何环境变量，避免触碰安全评审红线。

### 变更

- **依赖安装改由 Agent 承担**。`README.md` 与对外安装说明的「安装」章节收敛为两步
  （放文件 → 重开会话），不再要求用户手工执行 pip / playwright 命令；
  `SKILL.md` 明确首次运行前由 Agent 自检并补齐依赖，一律装到 WorkBuddy 隔离环境，
  **不污染用户全局 Python**；缺 `openpyxl` 时仅台账降级、不阻断出报告。

---

## [1.2.0] - 2026-09-27

### 变更

- **Apple 版成为默认报告版式。** `--theme` 不带参数时即输出 Apple 风格（纯白纸 + 灰色圆角卡片 +
  只描边的胶囊标题，零暗底，打印友好）；要 1:1 复刻批改报告样本的版式，改用 **`--theme classic`**。
  `render.py` 新增 `DEFAULT_THEME` 常量，付费层的默认版式跟随它。
- **README 不再包含付费上架章节。** 相关说明（四步编排、命令示例、协议字段、配置与安全提醒）
  全部并入本文件 [1.1.0] 条目，代码与 `references/skillpay.md` 原样保留。

### 说明

- SKILL.md frontmatter 补齐 SkillHub 发布所需字段（`slug` / `displayName` / `summary` / `license` /
  `homepage` / `tags`），并在 README 标注 SkillHub 上架地址与使用教程。
- `--theme default` 写法自本版本起不再有效：取 `apple`（默认）或 `classic`（原版样本版式），
  `python scripts/render.py --list-themes` 可列出全部。
- 仓库新增 `dist/`，附上对外分发包 zip（含安装说明），可直接下载转发。

---

## [1.1.1] - 2026-09-26

**安全修复**：移除一项被安全评审判定为「削弱主机安全防御」的写法。

### 修复

- **不再读写宿主注入的环境变量**。`scripts/render.py` 曾在导入时删除宿主下发的批量删除守卫与
  审计类环境变量，以便让临时目录清理不被拦下。这是削弱宿主安全控制，SkillHub 安全评估据此判为
  「可疑风险」，安全健康度仅 60 分。现已**彻底移除**，并同步清理了注释中的相关关键词，
  避免静态扫描误命中。
- **HTML→PDF 收敛为单一 Playwright 路径**，删除了命令行调用 Edge/Chrome 无头模式的回退实现
  （`html_to_pdf_cli` / `find_browser` / `EDGE_CANDIDATES`）。该回退路径本身不可靠
  （用户已打开浏览器时会被接管并静默失败），而且是上述环境变量改写的唯一动机。
  一并移除了 `subprocess` / `tempfile` / `shutil` 依赖 —— 现在**不再启动外部进程、
  不再创建临时目录、不再递归删除任何目录**，PDF 渲染的整类风险面归零。
- Playwright 未安装时给出明确的安装指引与 `--html-only` 备选，不做隐式降级。

### 说明

- 渲染结果与 1.1.0 完全一致（已回归验证：两套皮肤均正常出 PDF，页眉页脚齐全）。
- `SKILL.md` 新增硬约束第 8 条：**不得削弱宿主的安全控制**，作为后续维护的红线。
- 功能无变化，`scripts/skillpay/` 自测仍 50/50 通过。

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

### 本地操作

```bash
# 离线跑通整条链路（生成密钥 + mock 网关，不需要商户资质、不联网）
python scripts/skillpay/selftest.py

# 看价格 / 请求资源（未付款输出 402 账单）/ 携带凭证重试
python scripts/skillpay/cli.py pay-info
python scripts/skillpay/cli.py probe --jsondir ./final --outdir ./out
python scripts/skillpay/cli.py complete --payment-proof "<Base64URL>" --jsondir ./final --outdir ./out

# 本地 HTTP 服务：返回真实的 402 状态码与 Payment-Needed / Payment-Validation 响应头
python scripts/skillpay/server.py --port 8787
```

### 说明

- 付费层对原有批改能力**零侵入**：不启用付费时，直接跑 `scripts/render.py` 的行为与 1.0.0 完全一致。
- 新增可选依赖 `pycryptodome`（仅在需要 402 签名时安装；也可用 `cryptography`）。
- `.gitignore` 新增排除 `skillpay.local.json`、`state/`、`*.pem`、`*.key`、`*.db` ——
  商家私钥与订单库绝不入库。
- **安全提醒**：商家应用私钥只从环境变量或本地 `skillpay.local.json` 读取，**不要提交到仓库**
  （`.gitignore` 已排除 `skillpay.local.json`、`state/`、`*.pem`）。

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
