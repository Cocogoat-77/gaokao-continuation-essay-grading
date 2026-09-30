# gaokao-continuation-essay-grading

高中英语读后续写**手写答题卡**自动批改系统：逐词转写 → 结构化批改 JSON → 11 板块 A4 报告（HTML + PDF）+ 班级成绩台账。可作为 [WorkBuddy](https://www.workbuddy.cn) Skill 使用，也可只取其中的渲染管线、付费层独立运行。

**v1.4.1**（2026-09-30） · [更新日志](CHANGELOG.md) · [GPL-3.0 许可](LICENSE.md) · 作者 [Cocogoat-77](https://github.com/Cocogoat-77)

> 面向使用者的图文教程见 [SkillHub](https://skillhub.cn/skills/indiv-cocogoat/gaokao-continuation-essay-grading)；本 README 是面向开发者的**程序说明**。

---

## 一、双版本架构

本仓库为**完整版**（本地渲染）；另有一份**服务端渲染精简版**上架 SkillHub，两者批改规则完全一致，只差"在哪渲染"：

```
完整版（本仓库）                          SkillHub 精简版
─────────────────────────────            ─────────────────────────────
答题卡 JPEG                               答题卡 JPEG
   │ Agent 逐词转写                          │ Agent 逐词转写
   ▼                                        ▼
批改 JSON                                 批改 JSON
   │                                        │ submit_grade.py
   ▼                                        │ (HTTPS, 内联上传)
render.py ──► HTML                         ▼
   │            │                   ┌──────────────────┐
   │            ▼                   │ 服务端 (本仓库    │
   │      Playwright Chromium       │ scripts/skillpay) │
   │            │                   │ /v1/trial 免费体验│
   ▼            ▼                   │ /v1/grade  402收费│
 pymupdf      A4 PDF                │ 内联渲染→Base64   │
 盖页眉页脚                         └──────────────────┘
   │                                        │
   ▼                                        ▼
HTML + PDF（本地产物）                HTML + PDF（Base64 回传落盘）
```

- **完整版**：一切在本地完成，离线可用，适合个人使用与二次开发；
- **精简版**：买家端只产出 JSON，渲染与收费在服务端完成（买家的浏览器/机器无需任何渲染依赖），适合市场分发。

## 二、目录结构

```
gaokao-continuation-essay-grading/
├── SKILL.md                        Skill 主文件：工作流、硬约束、质量闸门（Agent 的行为规范）
├── README.md                       本文件
├── CHANGELOG.md                    版本变更记录
├── LICENSE.md                      GPL-3.0 全文
├── .gitignore                      学生数据、密钥、订单库一律不入库
├── assets/
│   ├── report-template.html        原版（classic）A4 报告模板
│   └── themes/
│       └── report-template-apple.html   Apple 版模板（默认皮肤）
├── references/
│   ├── report-spec.md              报告版式 + 批改 JSON 数据契约（唯一权威规格）
│   ├── rubric.md                   25 分制档位与校准锚点、固定句式
│   ├── tag-library.md              问题标签库 / 错误类型库 / 衔接检查用语
│   ├── themes.md                   皮肤设计规范、修订标记口径、模板占位符契约
│   └── skillpay.md                 支付宝 AI 付（402 协议）接入规范
├── scripts/
│   ├── check_env.py                环境自检（只检查不安装，缺什么打印安装命令）
│   ├── manifest.py                 按学号配对答题卡与已有报告，生成作业清单
│   ├── aggregate.py                按班级聚合佳句与场景词汇，生成成绩台账
│   ├── render.py                   JSON → HTML → A4 PDF 渲染管线
│   ├── pack_for_upload.py          白名单打包（供网页端手动上传 GitHub 用）
│   └── skillpay/                   付费层（支付宝 AI 按量付费 402 协议）
│       ├── config.py               配置加载（mode/unit_price/quantity_cap...）
│       ├── bill.py                 402 账单构造 + RSA2 签名（账单白名单 + 网关全参数）
│       ├── proof.py                Payment-Proof 解析
│       ├── gateway.py              支付宝网关封装（mock/sandbox/production + 验付/履约确认）
│       ├── store.py                SQLite 订单库（WAL + BEGIN IMMEDIATE + 唯一索引）+ 试用记录
│       ├── service.py              编排核心：probe / pay / complete / ack / trial
│       ├── server.py               HTTP(S) 服务：/v1/grade /v1/trial /v1/pay-info /v1/ack /healthz
│       ├── cli.py                  本地命令行入口（自测/联调用）
│       └── selftest.py             离线自测（mock 网关，64 项断言）
└── dist/                           对外分发包 zip
```

## 三、快速开始（完整版，本地）

```bash
# 1. 环境自检（缺什么它会给出安装命令）
python scripts/check_env.py

# 2. 单篇渲染（JSON 契约见 references/report-spec.md）
python scripts/render.py --json results/3021_张三.json --outdir ./out
# 批量 / 换皮肤 / 只要 HTML
python scripts/render.py --jsondir ./results --outdir ./out
python scripts/render.py --jsondir ./results --outdir ./out --theme classic
python scripts/render.py --jsondir ./results --outdir ./out --html-only
```

在 WorkBuddy 中作为 Skill 使用时，上述步骤由 Agent 按 `SKILL.md` 自动完成。

## 四、批改流水线（四路工作流）

| 路线 | 输入 → 输出 | 说明 |
|---|---|---|
| A 单篇精批 | 1 张答题卡 → 1 份报告 | 转写 → 词数 → JSON → 渲染 |
| B 批量流水线 | 全班 → 每人一份报告 | manifest 断点续跑 → 逐篇 JSON → aggregate 聚合 → 渲染 |
| C 班级台账 | 全班 → Excel | aggregate.py 副产品：成绩台账 + 班级诊断两张表 |
| D 成长档案 | 同一学生跨次 JSON | 对比得分/词数/错误类型演变，≥2 次数据可用 |

**关键设计：Skill 不绑定任何具体题目。** 原题前文、两段首句、情节链、场景词汇全部来自当次 `assignment.json` 与学生实际作文，换题只需换配置文件。

## 五、手写转写与批改规则（硬约束摘要）

完整规则见 `SKILL.md`「硬约束」一节，实现与文档必须保持一致：

1. **学生自己划掉/涂改的词一律不转写、不计词数、不算错误**；判划改**只看一次**，拿不准一律按被划掉处理，不反复放大纠缠；
2. **原样转写**：拼写、时态错误照抄，不得自动改正（转写后回看原图核对一遍）；
3. **错误计数自洽**：评语中声明的错误数 ≥ `errors[]` 条数，且类型都能在 `notes[].type` 找到；
4. **词数自洽**：`word_count` 与「完成度」声明一致；
5. **引用真实**：报告中引用的学生表达必须逐字出现在转写稿；
6. **修订标记成对**：错误原文 `<del>`（红字删除线）、订正 `<ins>`（`#CACACA` 灰底红字），缺一不可；
7. **不得编造**：缺材料如实说明；卷面评级按 rubric 的优先级判定。

## 六、渲染管线（render.py）

```
JSON ──► build_html（模板 + 占位符替换，esc() 保留 <del>/<ins>/<b> 白名单标记）
     ──► html_to_pdf_playwright（自带 Chromium，--no-sandbox；唯一渲染路径，不调用外部浏览器）
     ──► stamp_header_footer（pymupdf 盖页眉[班级/学号/姓名] + 页脚[页码/日期]）
     ──► subset_fonts（字体子集化，防止单份 PDF 从 ~200KB 膨胀到 ~7MB）
```

- **皮肤**：`--theme apple`（默认，零暗底）/ `--theme classic`（1:1 复刻批改报告样本）；`use_theme()` 运行时切换，模板满足 `references/themes.md` 的占位符契约即可扩展；
- **修订标记口径**：`--marks theme`（跟随皮肤配色）/ `--marks strict`（强制灰底红字规格）；
- **字体探测** `_find_cjk_font()`：页眉页脚按候选列表探测（Windows 幼圆 → Linux wqy/noto/uming），兜底 `fc-match`，并用 `has_glyph("中")` 验证真能写出中文字形；找不到则跳过盖章而不失败——这是服务端（Linux）部署的关键；
- **Playwright 是唯一 PDF 路径**：不要加命令行调用 Edge/Chrome 的回退（曾被安全评审判「削弱主机安全防御」）。

## 七、批改 JSON 数据契约

`references/report-spec.md` 是唯一权威规格：11 个板块的顺序、措辞、`<del>/<ins>` 写法、`class_shared`（佳句/场景词汇，班级级共享）、`assignment.json` 字段（`source_text`/`prompt1`/`prompt2`/`scene_vocab`）。渲染器与付费层只依赖该契约，与具体题目无关。

## 八、付费层（scripts/skillpay/）

支付宝 **AI 按量付费（HTTP 402 协议）**，按报告篇数计价（`DEFAULT_UNIT_PRICE = "0.02"`，单次上限 `quantity_cap = 2500` 篇，金额用 `Decimal` 定点计算）。

### 8.1 四步编排

| 步骤 | 动作 | 关键要求 |
|---|---|---|
| probe | 未付款 → `402 + Payment-Needed`（Base64URL 账单，RSA2 签名） | **先落库再出账单** |
| pay | 账单交给支付宝 AI 付能力，用户本人付款 | Agent 只编排、不代付 |
| complete | 同一请求携 `Payment-Proof` 重试 → 验付 → 履约 | 校验失败一律回 402，绝不让用户重复付款 |
| ack | `fulfillment.confirm` 成功后才标 `FULFILLED` | 失败 502，同凭证可重试 |

### 8.2 五项必做控制（对应官方付费改造检查）

1. **402 账单下发**（`bill.build_payment_needed`，出账单前持久化订单）；
2. **携带凭证重试**（`proof.parse_payment_proof`，解析失败回 402）；
3. **验付调用**（`gateway.payment_verify`：`active`/金额/订单号/资源标识/trade_no 未复用）；
4. **履约确认**（确认成功才 `mark_fulfilled`，失败 502 可重试）；
5. **订单持久化与幂等**（`store.prepare_fulfillment` 在 `BEGIN IMMEDIATE` 事务内原子地「重读→校验→生成→落库」，`trade_no` 唯一索引防串单）。

### 8.3 内联报告契约（远程买家全链路）

`payload.reports = [{"name": "3021_张三.json", "content": {…报告JSON…}}]`：

- 服务端写入临时目录渲染，**忽略买家传入的任何路径**（杜绝任意写盘），渲染完整目录删除；
- 响应 `content.files[]` 携带 HTML/PDF 的 Base64（`name/kind/mime/size/data_base64`），`produced` 只回传文件名；
- 篇数防篡改：complete 时重新计数与订单比对；单次 ≤500 篇（`MAX_INLINE_REPORTS`），请求体 >64MB 返回 413。

### 8.4 免费体验端点（/v1/trial）

每个来源 IP 每天可免费渲染 **1 篇**，按 `(IP, 北京日期)` 记账（`trials` 表，ip+date 唯一索引），**北京时间零点自动刷新**（`_beijing_today()` 固定 +08:00，与服务器时区解耦）。不走 402、不建订单；**先占额度再渲染**（唯一索引防并发重复占用），渲染失败 `cancel_trial()` 自动退还当日额度。额度用完返回 `429 TRIAL_QUOTA_USED`。服务器为直连模式、取 TCP 对端 IP；日后若加反向代理，需改读转发头。

## 九、服务端部署指南

以 Ubuntu + systemd 为例（生产实测环境）：

```bash
# 1) 隔离环境与依赖
python3 -m venv /opt/skillpay/venv
/opt/skillpay/venv/bin/pip install pymupdf playwright pycryptodome openpyxl
/opt/skillpay/venv/bin/python -m playwright install chromium
apt install fonts-wqy-zenhei          # 中文渲染字体（页眉页脚 + 正文兜底）

# 2) 代码与配置
#    /opt/skillpay/app/ 放本仓库（SKILL.md、scripts/、assets/、references/）
#    /opt/skillpay/app/skillpay.local.json（chmod 600）：
#    { "mode": "production", "service_id": "…", "app_id": "…", "seller_id": "…",
#      "seller_name": "…", "merchant_private_key": "…", "alipay_public_key": "…" }

# 3) TLS（402 协议的回打环节要求付费资源地址必须 HTTPS）
#    调试期可用自签证书（IP SAN）；正式运营请绑域名 + Let's Encrypt

# 4) systemd（/etc/systemd/system/skillpay.service）
[Service]
WorkingDirectory=/opt/skillpay/app
ExecStart=/opt/skillpay/venv/bin/python scripts/skillpay/server.py --host 0.0.0.0 --port 8787 --tls-cert /opt/skillpay/tls/server.pem --tls-key /opt/skillpay/tls/server.key
Restart=always
```

凭据管理红线：商户应用私钥/支付宝公钥**只**从环境变量或本地 `skillpay.local.json`（已 gitignore）读取，绝不入库、绝不打印；`state/`（订单库）与 `*.pem` 同样不入库。

## 十、测试与自检

```bash
python scripts/skillpay/selftest.py     # 离线全链路，mock 网关，无需商户资质
```

64 项断言覆盖：402 账单字段与 RSA2 签名可验/防篡改 → 按篇计价与上限 → 验付通过履约 → 幂等（重复凭证不重复发放）→ 失败分支（乱码凭证/active=false/金额不符/资源串号/订单不存在/篇数篡改/凭证复用）→ 履约确认失败 502 与 ack 恢复 → 内联渲染全链路（真实渲染、Base64 回传、不泄漏服务器路径）→ **免费体验**（首篇 200/同日重复 429/跨 IP 各有额度/多篇 400/跨天恢复/坏请求不占额度）。

`check_env.py` 只检查不安装：完整版查 pymupdf/playwright/Chromium/openpyxl；精简版仅查 openpyxl。

## 十一、安全设计

- **不削弱宿主安全**：不读写宿主注入的环境变量（守卫/审计类），不递归删除目录，不启动外部进程跑渲染；
- **资金安全**：金额 `Decimal` 定点；篇数/金额/资源标识三方校验；同一订单重复携带凭证不重复发放；
- **输入安全**：内联模式强制临时目录渲染，忽略买家路径；请求体 64MB 上限；
- **输出安全**：`produced` 只回传文件名，不泄漏服务器目录结构；不打印 Payment-Proof/Validation 原文。

## 十二、数据与隐私

本仓库不含任何学生数据（`.gitignore` 在源头排除答题卡、`results/`、`out/`、台账等）。服务端只保留订单号、篇数、金额等计费信息；报告内容渲染完成即从临时目录删除。

## 十三、打包上传 GitHub

网页端拖拽上传**不读 `.gitignore`**。手动上传请先：

```bash
python scripts/pack_for_upload.py            # 按白名单拷到 ./上传到GitHub/
python scripts/pack_for_upload.py --dry-run  # 只打印清单
```

## 十四、许可与来源说明

- 代码与文档按 **GPL-3.0** 授权：自由使用/修改/再发布，修改版须同以 GPL-3.0 开源；
- **版式来源说明**：报告版式与部分固定措辞参考并复刻自一份批改报告样本（逐元素测量而来）。该部分权利不归属本项目作者、不在 GPL 授权范围内，仅用于教学场景的格式还原；商用请自行评估权利风险；
- 25 分制档位划分依据公开的高考英语评分标准整理；校准锚点来自作者对本班实际批改结果的统计；
- AI 批改结果仅供参考，最终成绩以教师判断为准。
