# 支付宝 AI 按量付费（402 协议）接入规范

本 Skill 作为 **Pay Skill** 上架时，服务端必须实现支付宝 **AI 按量付费**的 402 协议。
本文是这套实现的规范与自检依据；代码在 `scripts/skillpay/`。

> 依据：支付宝官方《AI 按量付费本地接口契约》与《支付宝支付产品代码开发校验清单》
> 第五节「AI 按量付费专项校验」。本实现只覆盖 402 协议 +
> `alipay.aipay.agent.payment.verify` + `alipay.aipay.agent.fulfillment.confirm` 三件事，
> **不混入** AI 网页应用收款／AI 移动应用收款的统一收单接口、异步通知或 `notify_url`。

## 一、四步编排

| 步骤 | 谁执行 | 做什么 | 本仓库对应 |
|---|---|---|---|
| **probe** | 服务端 | 请求资源；未付款时返回 **HTTP 402** + `Payment-Needed` 账单头。收到 402 即暂停交付，保存账单与订单号 | `service.PayService.probe()` / `POST /v1/grade` |
| **pay** | Agent + 支付宝官方支付能力 | 把 `Payment-Needed` 交给支付能力拉起收银台，用户本人扫码/免密付款。**Agent 只编排，不代付** | `service.pay_info()` 提供商品名与价格 |
| **complete** | 服务端 | 付款成功后携带 `Payment-Proof` **重试原请求**；服务端调 `payment.verify` 验付，通过后幂等履约 | `service.PayService.complete()` |
| **ack** | 服务端 | 交付后调 `fulfillment.confirm` 确认履约；失败可重试且保持幂等 | `service.PayService.ack()` / `POST /v1/ack` |

**调用方前置检查**：发起下单前先确认当前智能体工具列表里存在支付宝支付能力工具
（如官方 `alipay-payment-skill` / `alipay-bot` 提供的工具）。存在 → 继续；
不存在 → 终止流程，提示用户升级智能体、或从 SkillHub 安装「支付宝 AI 付」官方 Skill 后重试。

## 二、五项必做控制（逐项对照）

SkillHub 的付费改造检查会逐项核验下列五条。**每一条都必须在服务端真实实现，
不能是 TODO、注释、内存演示或伪代码。**

### 1. 402 账单下发

- 无有效 `Payment-Proof` → 返回 **HTTP 402**，响应头 `Payment-Needed` 放 Base64URL 编码的账单。
- 响应体只用于调试，**智能体支付的依据是 Header**。
- **必须先持久化订单，再返回账单**——否则用户付款后带凭证回来时映射不回本地订单。
- 实现：`bill.build_payment_needed()` + `service.probe()`（顺序：`create_pending` → 返回 402）。

### 2. 携带凭证重试

- 付款后调用方用**同一请求**重试，并在请求头带 `Payment-Proof`。
- 凭证解析失败／`active != true`／`trade_no` 不一致 → 一律回到 402，让 Agent 重新支付。
- **结果不明时不得要求用户重复付款**。
- 实现：`proof.parse_payment_proof()` + `service.complete()` 的 3.1 / 3.3 分支。

### 3. 验付调用

- 收到 `Payment-Proof` 后**必须**调用 `alipay.aipay.agent.payment.verify`，
  业务入参 `trade_no`、`payment_proof`、可选 `client_session`。
- 验付成功不能只看 `code=10000`，还必须同时校验：
  `active=true`、返回 `amount` 等于本地订单金额、返回 `out_trade_no` 等于本地订单号、
  返回 `resource_id` 等于当前请求资源、`trade_no` 未被重复履约、本地订单处于允许状态。
- **任一校验失败 → 返回 402，不返回资源。**
- 实现：`gateway.AlipayGateway.payment_verify()` + `service.complete()` 的 3.2–3.9。

### 4. 履约确认

- 资源生成后**必须**调用 `alipay.aipay.agent.fulfillment.confirm`，业务入参只有 `trade_no`。
- **确认成功后才把订单标记为 `FULFILLED`**；确认失败返回 502，
  允许用**同一 `Payment-Proof`** 重试，避免"资源已生成但平台未记录履约"。
- 实现：`gateway.AlipayGateway.fulfillment_confirm()` + `store.mark_fulfilled()`；
  单独重试走 `service.ack()`。

### 5. 订单持久化与幂等

五项子要求，缺一不可：

| 子项 | 要求 | 实现 |
|---|---|---|
| 订单持久化 | 返回 `Payment-Needed` 前持久化 `out_trade_no` / `resource_id` / 金额 / 状态 / 过期时间 | `store.create_pending()` |
| 本地订单匹配 | 验付成功后查本地订单并校验状态（防凭证有效但订单不存在/过期/异常） | `store.find_by_out_trade_no()` |
| 资源防串 | 本地订单 `resource_id` 必须与验付结果、当前请求资源三者一致 | `service.complete()` 3.7 |
| 金额一致性 | 本地订单金额 == 账单金额 == 服务定价；验付返回金额时再比对实际支付金额 | `service.complete()` 3.6 + `store._amounts_equal` |
| 幂等履约 | 同一订单重复携带 `Payment-Proof` **不得重复发放资源**，应返回历史结果或可重试确认结果 | `store.prepare_fulfillment()`（`BEGIN IMMEDIATE` 原子占位 + `trade_no` 唯一索引） |

金额一律用 `Decimal` 按 2 位小数定点计算，**禁止二进制浮点误差**。

## 三、402 协议字段

`Payment-Needed` = Base64URL(`{"protocol": {...}, "method": {...}}`)，去掉尾部 `=` 填充。

**`protocol` 必备**

| 字段 | 说明 |
|---|---|
| `out_trade_no` | 商户订单号 |
| `amount` | 金额（元，字符串，2 位小数） |
| `currency` | 固定 `CNY` |
| `resource_id` | 资源标识 |
| `pay_before` | 账单有效期截止时间（带时区 ISO 8601） |
| `seller_signature` | 商家签名 |
| `seller_sign_type` | 固定 `RSA2` |
| `seller_unique_id` | 商家唯一标识 |

**`method` 必备**

| 字段 | 说明 |
|---|---|
| `seller_name` | 商户名称 |
| `seller_id` | 商户号 |
| `seller_app_id` | 应用 appId |
| `goods_name` | 商品名称（按篇计价时带上「N 篇 × 单价」明细） |
| `seller_unique_id_key` | 固定 `seller_id` |
| `service_id` | 服务市场 serviceId；沙箱固定 `api_mock_service_id` |

**商家签名规则**：按 key 字典序拼接
`amount` → `currency` → `goods_name` → `out_trade_no` → `pay_before` → `resource_id` →
`seller_id` → `service_id`，用商家私钥做 RSA2（SHA256 + PKCS#1 v1.5），结果做**标准 Base64**。
**签名只在商家本地完成，不请求支付宝服务端。**

> 注意：`seller_id` 与 `service_id` 只在 `method` 段里，校验签名时要跨两段合并 ——
> 用 `bill.sign_fields_from_payment_needed()` 还原，别只拿 `protocol` 段。

## 四、Payment-Proof 结构

Base64URL 解码后：

| 取值 | 来源 | 必需 |
|---|---|---|
| `payment_proof` | `protocol.payment_proof` | 是 |
| `trade_no` | `protocol.trade_no` | 是 |
| `client_session` | `method.client_session` | 否 |

交付成功时在响应头回 `Payment-Validation`：
Base64URL(`{"trade_no", "out_trade_no", "validated": true, "resource_id"}`)。

## 五、订单状态机

```
order_status   : PENDING_PAYMENT ──→ PAID
fulfill_status : UNFULFILLED ──→ PENDING_CONFIRM ──→ FULFILLED
```

- `pay_before` 只在 **probe（账单下发）** 阶段是硬约束：过期账单收银端本就不受理；
- **验付已通过（支付宝确认真实收款）后，不得再以 `pay_before` 已过为由拒绝交付**——
  否则等于「已收款不发货」（moveToMobile 付款在时限内完成、验付请求晚到几分钟即触发）。
  `service.py` 3.8 与 `store.prepare_fulfillment` 均按此实现；
- **已经原子进入 `PENDING_CONFIRM` / `FULFILLED` 的同一订单，只能重试确认或返回已保存结果，
  不得重复生成资源**（`prepare_fulfillment` 里显式实现了这条）；
- 防串单 / 防重复由 trade_no 唯一索引（3.9）与幂等履约（3.10）保证。

## 六、计费口径

**按报告篇数计价**：账单金额 = `unit_price` × 本次请求篇数。

- 单价默认 `0.02` 元/篇（`SKILLPAY_UNIT_PRICE`）
- 篇数来源：内联 `reports`（列表长度，远程买家）、`--json`（1 篇）或 `--jsondir`（目录里 `.json` 个数）
- 单次调用篇数上限 `quantity_cap`（默认 2500），防止误传目录导致天价账单
- 例：一个班 40 篇 → 账单 `0.80` 元，`goods_name` 写明「40 篇 × 0.02 元」
- **`unit_price` 必须与 SkillHub 发布表单里的定价一致**，避免误导用户

篇数在下单时写入订单，`complete` 时会重新计算并比对 —— 篇数被改则金额不符，一律回到 402。

## 七、配置与部署

配置来源（后者覆盖前者）：代码默认值 → `<skill>/skillpay.local.json` → 环境变量 `SKILLPAY_*`。

| 环境变量 | 说明 |
|---|---|
| `SKILLPAY_MODE` | `sandbox`（默认）/ `production` |
| `SKILLPAY_APP_ID` | 应用 appId |
| `SKILLPAY_SELLER_ID` | 商户号 |
| `SKILLPAY_SELLER_NAME` | 商户名称 |
| `SKILLPAY_SERVICE_ID` | 服务市场 serviceId（生产必填真实值） |
| `SKILLPAY_UNIT_PRICE` | 单价（元/篇），默认 `0.02` |
| `SKILLPAY_QUANTITY_CAP` | 单次调用篇数上限，默认 `2500` |
| `SKILLPAY_MERCHANT_PRIVATE_KEY` | 商家应用私钥（裸 base64 或 PEM，或 `file:路径`） |
| `SKILLPAY_ALIPAY_PUBLIC_KEY` | 支付宝公钥（验签用） |
| `SKILLPAY_STATE_DIR` | 订单库目录，默认 `<skill>/state` |
| `SKILLPAY_GATEWAY_IMPL` | `alipay`（默认）/ `mock`（仅自测） |

**沙箱 ↔ 生产切换**：`mode` 从 `sandbox` 改为 `production` 时，网关自动切到
`https://openapi.alipay.com/gateway.do`，且 `service_id` 必须换成服务市场返回的真实值；
仍留 `api_mock_service_id` 会直接报错拒绝启动。

### 安全红线（官方校验清单要求）

1. **应用私钥只允许来自环境变量或本地非入库配置**，禁止写进包内、日志或公开仓库；
   `skillpay.local.json`、`state/`、`*.pem` 都在 `.gitignore` 里。
2. **禁止打印 `Payment-Proof` 或 `Payment-Validation` 原始值**，也不要打印私钥。
3. 订单库权限不应宽于 `0600`；单次联调的临时产物用完即清。
4. 全程不向用户暴露支付链接、二维码原文或交易号等中间过程。
5. 沙箱 appId / 私钥 / 支付宝公钥必须来自**同一套**沙箱应用，不得混用。

### HTTP 服务契约（远程买家 / 部署侧）

- **端点**：`POST /v1/grade`（`server.py`，建议配 `--tls-cert/--tls-key` 走 HTTPS；
  健康检查 `GET /healthz`，价格 `GET /v1/pay-info`，履约确认重试 `POST /v1/ack`）。
- **免费体验**：`POST /v1/trial`——每个来源 IP 每天可免费渲染 **1 篇**（北京时间自然日，
  零点自动刷新），请求体与 `/v1/grade` 相同但 `reports` 只允许 1 份；**不走 402、不建订单**；
  额度用完返回 429（`TRIAL_QUOTA_USED`），渲染失败自动退还当日额度。
- **请求体**：`{"payload": {...}}`，payload 三选一：
  - **内联报告（远程买家，推荐）**：`{"reports": [{"name": "3021_张三.json", "content": {…报告JSON…}}], "theme": "apple"}`
    ——服务端写入临时目录渲染（**忽略买家传的任何路径**），响应 `content.files[]` 携带
    HTML/PDF 的 Base64（`name/kind/mime/size/data_base64`），`produced` 只回传文件名；
    渲染完临时目录即删。单次上限 500 篇；请求体超 64MB 返回 413。
  - **本机路径（自测用）**：`{"json": "路径"}` 或 `{"jsondir": "目录", "outdir": "输出目录"}`
  - **空 payload**：凭据交付模式（计 1 篇，不产文件，用于联调）。
- **买家侧现成实现**：精简版 Skill 的 `scripts/submit_grade.py`（纯标准库，
  `probe` / `complete` / `pay-info`，请求体缓存于 `.skillpay_submit/` 保证重试同一请求）。

## 八、本地操作

```bash
# 0) 离线跑通整条链路（生成密钥 + mock 网关，不需要商户资质、不联网）
python scripts/skillpay/selftest.py

# 1) 看价格（不下单）
python scripts/skillpay/cli.py pay-info

# 2) probe：请求资源 → 输出 402 账单，退出码 402
python scripts/skillpay/cli.py probe --jsondir ./final --outdir ./out

# 3) complete：付款后携带 Payment-Proof 重试原请求
python scripts/skillpay/cli.py complete --payment-proof "<Base64URL>" \
    --jsondir ./final --outdir ./out

# 4) ack：资源已生成但履约确认失败时单独重试
python scripts/skillpay/cli.py ack --trade-no "<trade_no>"

# 配置与订单统计
python scripts/skillpay/cli.py status

# 起本地 HTTP 服务（真实 402 状态码与响应头）
python scripts/skillpay/server.py --port 8787
```

## 九、上线前核对

- [ ] `SKILLPAY_MODE=production`，网关已是 `openapi.alipay.com`
- [ ] `service_id` 已换成真实值，**不含** `api_mock_service_id`
- [ ] appId / 应用私钥 / 支付宝公钥属于同一套**生产**应用
- [ ] 非 Java 私钥格式为 PKCS#1（Java 用 PKCS#8）
- [ ] 私钥不在代码、日志、公共仓库中明文出现
- [ ] `unit_price` 与 SkillHub 发布表单定价一致
- [ ] 订单库目录已加入 `.gitignore`，权限不宽于 `0600`
- [ ] `python scripts/skillpay/selftest.py` 全绿
- [ ] 生产环境关键字段为空时按异常处理（不沿用沙箱容错逻辑）

## 十、常见问题

| 现象 | 原因与处理 |
|---|---|
| `probe` 返回 500 `CONFIG_ERROR` | 未配置商家私钥。设 `SKILLPAY_MERCHANT_PRIVATE_KEY` 或写本地 `skillpay.local.json` |
| `probe` 返回 400 `QUANTITY_ERROR` | 篇数为 0 或超过 `quantity_cap`。分批调用或调大上限 |
| `complete` 一直返回 402 | 看响应体里的 `rejected_reason`：凭证无效／金额不符／资源串号／篇数不符，各有明确文案。验付已通过后不再有「订单过期」分支 |
| 返回 502 `FULFILLMENT_CONFIRM_FAILED` | 资源已生成、履约确认未成功。用**同一 Payment-Proof** 重试，或调 `ack` |
| 签名校验不过 | 检查是否把 `seller_id` / `service_id` 漏掉——它们只在 `method` 段，用 `bill.sign_fields_from_payment_needed()` 还原 |
| 提示需要 RSA 签名库 | `pip install pycryptodome`（官方示例用的也是它） |
