---
name: gaokao-continuation-essay-grading
description: "高中英语读后续写作文自动批改与报告生成。输入学生手写答题卡（JPEG 扫描件）与原题材料，输出逐句批改、情节分析、出彩表达、个性化提升、润色稿等 11 个板块的个人报告（HTML + A4 PDF），并可批量处理整个班级、生成班级成绩台账。支持上架为按篇计费的付费技能（Pay Skill）：内置支付宝 AI 按量付费 402 协议，含 Payment-Needed 账单下发、Payment-Proof 携带凭证重试、payment.verify 验付调用、fulfillment.confirm 履约确认与订单持久化幂等。触发词：读后续写批改、作文自动批改、答题卡批改、英语作文报告、生成批改报告、批量批改作文、付费技能、按量付费、402 收款、Pay Skill。"
description_en: "Grade handwritten Gaokao continuation-writing answer sheets and produce structured A4 PDF reports (11 sections: sentence-by-sentence correction, plot analysis, highlights, personalised upgrades, polished version) plus a class-wide score ledger. Can be published as a pay-per-report paid skill: ships an Alipay AI pay-per-use (HTTP 402) integration with Payment-Needed billing, Payment-Proof retry, alipay.aipay.agent.payment.verify, alipay.aipay.agent.fulfillment.confirm, and idempotent order persistence. Use for continuation-writing grading, answer-sheet grading, batch essay grading, paid skill monetisation, or generating English essay feedback reports."
version: 1.1.0
author: Cocogoat-77
agent_created: true
---

# 高中读后续写自动批改

把学生手写答题卡批量转成与批改报告样本同规格的个人报告，并顺带产出班级教学决策数据。

## 默认约定

- 满分 25 分（高考读后续写制），得分必须落在 `references/rubric.md` 的档位与校准锚点内。
- **本 Skill 不绑定任何具体题目。** 凡与情节有关的内容——原题前文、两段首句、`source_summary`、`p1_tag`／`p2_tag`、情节链大纲、场景词汇、所有引用学生英文的句子——一律来自**当次** `assignment.json` 与**该生实际写的作文**。换一道题就重新生成一份 `assignment.json`，Skill 本体不需要改。
- 报告结构、版式、配色、字段命名一律以 `references/report-spec.md` 为准，不得自行增删板块。
- **报告版式有两套皮肤可选**（`--theme`），见 `references/themes.md`：`default` 原版（默认，1:1 复刻批改报告样本）／`apple` Apple 风格（**要打印选它**）。皮肤只换长相，不换判定与板块。用户没指定就用 `default`。
- 问题标签、错误类型、衔接检查用语只能取自 `references/tag-library.md` 的固定集合。
- 学生姓名的写法：报告标题与页眉用学生的真实姓名，不用学号代替。
- 未提供原题时，先做语言层批改（逐句批改、错误分析、出彩表达、个性化提升），情节分析相关板块留空并明确告知用户缺什么，不虚构原文情节。

## 环境依赖

首次使用前确认（缺失则装到 WorkBuddy 的隔离环境，不要污染用户全局 Python）：

```bash
<python> -m pip install pymupdf playwright openpyxl pycryptodome
<python> -m playwright install chromium
```

`pymupdf` 用于加盖页眉页脚；`playwright` + 自带 Chromium 用于 HTML→PDF（**不要用命令行的 Edge 无头模式**，用户已打开 Edge 时会被接管并静默失败）；`openpyxl` 仅生成班级台账时需要；`pycryptodome` 仅上架 Pay Skill 时需要（402 账单的 RSA2 签名，也可用 `cryptography` 替代）。

## 四路工作流

| 路线 | 用途 | 何时用 |
|---|---|---|
| **A 单篇精批** | 1 张答题卡 → 1 份报告 | 首次验证版式与评分、个别学生补批 |
| **B 批量流水线** | 全班答题卡 → 每人一份报告 | 日常批改主路径 |
| **C 班级台账** | 全班 → Excel 台账 + 班级诊断 | B 的自动副产品，也可单独跑 |
| **D 成长档案** | 同一学生跨次对比 | 累积 ≥2 次数据后 |

### A 单篇精批

1. 读答题卡图片，**逐词原样转写**两段续写内容（见下方硬约束）。
2. 统计词数（只数两段续写正文，不含段落标签、不含印好的提示句）。
3. 按 `references/report-spec.md` 第五节的 JSON 契约，产出该学生的 JSON 文件。
4. 运行渲染：

```bash
python scripts/render.py --json results/<学号>_<姓名>.json --outdir ./out
# 换皮肤（可选）：--theme apple；--list-themes 看全部
```

5. 交付 `./out/读后续写_<学号>_<姓名>.html` 与 `.pdf`。用 `present_files` 打开 HTML 预览。

### B 批量流水线

**阶段 0｜准备**

```bash
python scripts/manifest.py --answer-dir "<答题卡目录>" --report-dir "<已有报告目录，可省略>" \
                           --out assignment-manifest.json
```

按需创建题目级配置 `assignment.json`（结构见 `references/report-spec.md` 第六节）：题型、日期、满分、**原题前文**、两段首句、三组场景词汇。原题与首句必须由老师提供，不得从学生作文反推后当作原文写入。

> **换题必须换配置。** `source_text`／`prompt1`／`prompt2`／`scene_vocab` 全部与当次题目绑定，不可沿用上一题。每次拿到新题，先确认这四项，再开始批改；缺原题时按 `默认约定` 只做语言层批改，情节分析相关板块留空并告知老师。

**阶段 1｜逐篇批改（按批进行，建议每批 5–8 份）**

- 从 `assignment-manifest.json` 取待处理学生；**已存在 `results/{学号}_{姓名}.json` 的直接跳过**（断点续跑）。
- 对每份答题卡执行与路线 A 相同的 1–3 步，JSON 落到 `results/`。
- 每批结束即回报进度（已处理 / 总数 / 失败名单），不要等全部跑完再汇报。
- 单张答题卡整体不可用（大面积模糊、裁切不全、内容明显缺失）时，把该生标为 `needs_review` 并放进失败清单，不猜写后判错。**但别把这条用歪**：只是个别词看不清、或拿不准某个词有没有被划掉，不构成"需要复核"，按硬约束第 1 条默认按划掉处理，照常出报告。

**阶段 2｜班级聚合**

```bash
python scripts/aggregate.py --results-dir ./results --assignment assignment.json \
                            --outdir ./final --ledger ./班级台账.xlsx
```

该脚本**按班级分别聚合**：从本班挑出佳句、把场景词汇注入本班每份 JSON 的 `class_shared`，并生成台账。脚本会打印每个班的人数、佳句条数、场景组数。**佳句池是全班的**——取本班所有学生成绩最高的前 N 句，同一班内每份报告拿到的佳句列表完全相同。

> 注意：`学生佳句`、`场景词汇` 都是**班级级**内容，跨班不通用。**佳句区允许出现学生本人的句子**：只要他自己那句进了全班前 N，就会出现在自己的报告里，这是正常的，不要按人过滤掉。反过来，如果某个班只批改了 1 个人，那个班的佳句池就只有他自己 1 句。要得到信息量足够的佳句，把整个班批改完再聚合即可。

**阶段 3｜渲染输出**

```bash
python scripts/render.py --jsondir ./final --outdir ./out
# 可选：--theme apple 换 Apple 打印版；--marks strict 强制规格内的修订标记配色
#       --list-themes 查看全部皮肤。版式与设计规范见 references/themes.md
```

> 同一个 `final/` 可以反复渲染成不同皮肤，互不影响 —— 皮肤是纯 CSS 层的替换。
> **要给老师打印的版本用 `--theme apple`**（无暗底、省墨、不糊字）。

**阶段 4｜质检**（见下方质量闸门）通过后交付：报告 PDF 打包 + 台账 Excel。

### C 班级台账

阶段 2 的 `--ledger` 即产出。台账含两张表：`成绩台账`（学号/姓名/班级/得分/词数/语法错误数/卷面等级/问题标签/主要错误类型）、`班级诊断`（得分分布 + 错误类型人次排行）。汇报时点出错误人次最高的 3 类。

### D 成长档案

同一学生跨次 JSON 累积后，对比 `score`、`word_count`、`errors[].type` 集合与 `tags`，输出进步曲线与反复出现的易错点清单。数据不足两次时不生成。

## 付费调用（Pay Skill · 支付宝 AI 按量付费）

本 Skill 上架 SkillHub 作为 **Pay Skill** 时，按 **报告篇数**计费（默认 `0.01` 元/篇）。
付费链路走支付宝 **AI 按量付费（HTTP 402 协议）**：`402` 账单下发 → 携带 `Payment-Proof` 重试
→ 验付 → 履约确认 → 订单持久化与幂等。完整规范见 **`references/skillpay.md`**，实现在 `scripts/skillpay/`。

### 四步编排 `probe → pay → complete → ack`

| 步骤 | 谁做 | 做什么 | 命令 |
|---|---|---|---|
| **probe** | 服务端 | 请求资源；未付款时返回 **HTTP 402** + **`Payment-Needed`** 响应头（Base64URL 账单），并**先把订单落库**再返回账单 | `cli.py probe` / `POST /v1/grade` |
| **pay** | Agent + 支付宝官方支付能力 | 把 `Payment-Needed` 交给支付能力拉起收银台，用户本人扫码/免密付款。**Agent 只编排、不代付** | `cli.py pay-info` |
| **complete** | 服务端 | 付款后用同一请求 + **`Payment-Proof`** 重试；调 `alipay.aipay.agent.payment.verify` 验付，通过后幂等履约 | `cli.py complete` |
| **ack** | 服务端 | 交付后调 `alipay.aipay.agent.fulfillment.confirm` 确认履约；失败可重试且保持幂等 | `cli.py ack` |

> **前置检查**：发起下单前先确认当前智能体已安装支付宝支付能力工具
> （如官方 `alipay-payment-skill`）。不存在则终止流程，提示用户升级智能体或安装「支付宝 AI 付」官方 Skill。

### 调用示例

```bash
# 0) 离线跑通整条链路（生成密钥 + mock 网关，无需商户资质、不联网）
python scripts/skillpay/selftest.py

# 1) probe —— 未付款，输出 402 账单，退出码 402
python scripts/skillpay/cli.py probe --jsondir ./final --outdir ./out

# 2) complete —— 付款后携带 Payment-Proof 重试原请求（验付 + 履约）
python scripts/skillpay/cli.py complete --payment-proof "<Base64URL>" \
    --jsondir ./final --outdir ./out

# 3) 起本地服务，返回真实的 402 状态码与 Payment-Needed / Payment-Validation 响应头
python scripts/skillpay/server.py --port 8787
```

### 五项必做控制（对应 SkillHub 付费改造检查）

| # | 控制项 | 要求 | 实现位置 |
|---|---|---|---|
| 1 | **402 账单下发** | 无有效 `Payment-Proof` → HTTP **402** + **`Payment-Needed`**（Base64URL 账单，含 `protocol`/`method` 两段与 RSA2 `seller_signature`）；**必须在返回账单前持久化订单** | `bill.build_payment_needed` / `service.probe` |
| 2 | **携带凭证重试** | 付款后用同一请求带 **`Payment-Proof`** 重试；凭证无效一律回到 402，**不得因"结果不明"要求用户重复付款** | `proof.parse_payment_proof` / `service.complete` |
| 3 | **验付调用** | 必须调 `alipay.aipay.agent.payment.verify`，并同时校验 `active=true`、金额、`out_trade_no`、`resource_id`、`trade_no` 未重复履约、本地订单状态 | `gateway.AlipayGateway.payment_verify` |
| 4 | **履约确认** | 资源生成后必须调 `alipay.aipay.agent.fulfillment.confirm`，**确认成功后才标记 `FULFILLED`**；失败返回 502 且允许用同一凭证重试 | `gateway.fulfillment_confirm` / `store.mark_fulfilled` |
| 5 | **订单持久化与幂等** | 返回 `Payment-Needed` 前持久化 `out_trade_no`/`resource_id`/篇数/金额/状态/有效期；本地订单匹配、资源防串、金额一致性、**同一订单重复携带 `Payment-Proof` 不重复发放资源** | `store.py`（SQLite + `BEGIN IMMEDIATE` + `trade_no` 唯一索引） |

**计费口径**：账单金额 = `unit_price`（默认 `0.01` 元/篇）× 本次请求篇数
（`--json` 记 1 篇，`--jsondir` 记目录里 `.json` 的个数；单次上限 `quantity_cap`，默认 2500）。
`unit_price` 必须与 SkillHub 发布表单里的定价一致。

**安全红线**：应用私钥只从环境变量或本地非入库配置读取，禁止写进包内／日志／公开仓库
（`skillpay.local.json`、`state/`、`*.pem` 均已进 `.gitignore`）；不打印 `Payment-Proof` /
`Payment-Validation` 原始值；沙箱 `service_id` 固定 `api_mock_service_id`，生产必须换成真实值。

## 硬约束

1. **学生自己划掉／涂改的词，一律不转写、不识别、不进报告。** 转写得到的是学生**最终想保留的文本**；被划掉的词不出现在报告的任何位置，不计入词数，也不作为语法错误（它只是学生的自改过程，不是错误）。报告里出现的 `<del>` 只用于**指出真实错误并给出订正**，绝不能用来还原学生的自改痕迹。
   - **【默认规则】拿不准就按"被划掉"处理——直接执行，不要停下来纠结。** 只要一眼看不出某个词到底是学生正常写的、还是被他自己划掉的，就当作被划掉：不转写、不计词数、不算错误。**不要为了消歧反复放大、来回比对、把同一处裁剪很多遍。**
   - 可疑处的处理上限：**只看一次**。用 `pymupdf` 的 `get_pixmap(clip=..., dpi=1000~1500)` 裁一张出来看就够（本机 PIL 不可用，不要用 PIL 裁剪）。学生自己的删除线是**横贯整个词的直线**；字母之间的连笔横向笔画、书法回锋都**不是**删除线。看完仍不能确定，就回到上一条——按划掉算。
   - 划改会**连带影响错误判定**：错误分析是针对保留文本做的，删掉一个词可能使原本成立的错误类型不再成立（尤其是"句子成分残缺／连词误用"这类依赖某个连接词的判定）。改完转写后必须回头复核 `errors[]` 与 `【词汇句式和语法】` 的声明数。
   - 若手上已有该生的一份批改报告样本（`读后续写_{学号}_{姓名}.pdf`），它的"逐句批改"区印着学生原文，可以**顺手扫一眼**当参照。这只是可选捷径、不是必经步骤，**也不要为它来回比对**；万一它的读法与你的判断不一致，**仍然按"存疑即视为划掉"处理**，不要单方面采信任何一方。
2. **手写识别必须原样转写。** 学生写错的拼写、时态、搭配一律照抄，不得自动改正——模型默认倾向于输出正确英文，这是本任务最容易失败的地方。转写完成后**回看一遍**原图核对（一遍即可，不要反复重看），尤其检查：大小写、`'s`、时态词尾、拼写异常的单词。
3. **错误计数自洽。** `【词汇句式和语法】` 声明的总错误数 `{N}` 应 ≥ `errors[]` 条数——`错误分析详情` 只呈现最典型的几处，不必逐条罗列；但 `【词汇句式和语法】` 里列举的错误类型必须都能在 `errors[].notes[].type` 中找到对应，且 `{N}` 只统计真实存在的错误（实测样本中 156 词的作文典型为 11 处）。
4. **词数自洽。** `word_count` 必须等于 `【完成度】` 中声明的词数。
5. **原文引用真实。** `【完成度】`／`【词汇句式和语法】`／`出彩表达` 中引用的学生表达，必须逐字出现在转写稿里。
6. **`sentence_review` 用修订标记。** 错误原文包 `<del>`，紧跟的订正文本包 `<ins>`（成对出现，缺了 `<ins>` 订正文本就没有灰底）。只标真实修改处，不改动正确的部分。写法见 `references/report-spec.md` 第五节。
7. **不得编造。** 缺少原题、缺少学生姓名时如实说明，不虚构情节分析或仿造佳句；个别词识别不清按硬约束第 1 条处理（存疑即视为划掉），不靠猜写填空。

## 质量闸门（交付前逐项检查）

- [ ] **转写稿中不含学生自己划掉的词**（可疑处只看一眼，拿不准的一律按划掉算，没有反复放大纠缠）
- [ ] 11 个板块齐全，顺序与 `report-spec.md` 一致
- [ ] `【词汇句式和语法】` 声明的错误数 ≥ `errors` 条数，且列举的错误类型都能在 `notes[].type` 中找到
- [ ] `word_count` 与 `【完成度】` 声明的数字一致
- [ ] 衔接&过渡分析含全部 5 条固定检查项，每条都有具体英文优化建议
- [ ] `个性化提升` 含细节描写 ≥4 类、结尾句、更多表达 3 条
- [ ] `sentence_review` 与 `errors[].correct_form_html` 里每个 `<del>` 都有配对的 `<ins>`（订正文本带灰底）
- [ ] `face.grade` 按 `references/rubric.md` 第四节的**优先级**判定：第一优先级＝**字形规范性／字母大小一致性／间距一致性**（三项是硬门槛），划改类痕迹排在第三优先级、几乎不计入；描述撰写顺序与之一致，判优秀时用词要正面（不用"较为""基本"拖后腿）
- [ ] PDF 为 A4，每页均有页眉（班级/学号/姓名）与页脚（页码/日期）
- [ ] `class_shared` 的佳句与场景词汇在同批所有报告中完全一致
- [ ] **上架 Pay Skill 时**：`python scripts/skillpay/selftest.py` 全绿（402 账单下发 → 签名可验 → 携带 `Payment-Proof` 重试 → 验付 → 幂等履约 → 履约确认，含失败分支）；`unit_price` 与发布表单定价一致；私钥未入库、未进日志

## 常见问题

- **PDF 生成失败**：渲染首选 Playwright 自带的 Chromium；未安装时执行
  `pip install playwright && python -m playwright install chromium`。
  找不到 Playwright 才会回退到命令行调用 Edge——注意**用户已打开 Edge 时无头调用会被接管并静默失败（退出码仍为 0，但不产出 PDF）**，所以不要依赖这条回退路径。仍然失败时用 `--html-only` 出 HTML，再让用户用浏览器"打印 → 另存为 PDF"。
- **PDF 中背景色丢失**：必须开启"打印背景图形"（Playwright 的 `print_background=True`）。否则蓝色药丸标签、灰色修订底纹、绿色点评条会全部变成白色。
- **PDF 中文变方框**：确认 `C:\Windows\Fonts\SIMYOU.TTF`（幼圆）存在；缺失时页眉页脚不可用，但正文仍由浏览器渲染，不受影响。
- **页码/页眉缺失**：由 `render.py` 的 `stamp_header_footer` 用 pymupdf 加盖，需安装 `pymupdf`。
- **版式微调**：改 `assets/report-template.html`（原版）或 `assets/themes/report-template-<皮肤>.html` 里的 CSS，全部尺寸用 pt。**新增皮肤**：满足 `references/themes.md` 第七节的占位符契约，放进 `assets/themes/` 并在 `scripts/render.py` 的 `THEMES` 登记一行即可被 `--theme` 选用。
- **用户问"能不能换个样子"**：给 `--theme` 的选项（`default` / `apple`），并说明「要打印选 apple」，不要自己去改模板 —— 两套皮肤都在 `references/themes.md` 里定了规范，临时改会破坏一致性。
- **手写体看不清/拿不准**：**只看一次，不反复纠缠。** 用 `pymupdf` 对该区域 `get_pixmap(clip=..., dpi=1000~1500)` 裁一张看一眼就够（本机 PIL 不可用，不要用 PIL 裁剪）。看完仍判断不了那个词是不是被划掉的，**按硬约束第 1 条默认当作被划掉、不转写**，继续往下做，**不要**换 DPI 反复重裁、不要反复回看、也不要为此停下来问人。**更不要**用"整页低分辨率图 + 语感猜测"代替——看不清就按划定，这一条已经给了兜底，不值得为单个词打断整批批改。
- **要把 Skill 发布到 GitHub**：网页端拖拽上传**不读 `.gitignore`**，所以用 `python scripts/pack_for_upload.py` 按白名单打包后再拖 —— 学生数据（答题卡、`results/`、`out/`、台账 xlsx）只可能在白名单之外，打不进包。
- **定位坐标总是不准**：先在整页上画一张 0.02 精度的坐标网格图（pymupdf `new_shape().draw_line()` 叠在原图副本上），读出各行 y 值后再裁剪，比反复试错快得多。（不同答题卡版式不同，每换一种答题卡都要重新标定；实测某一种答题卡上作文正文每行约占 0.031 页高，仅供参考。）
