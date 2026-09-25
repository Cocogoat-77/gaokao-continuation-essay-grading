# 高中英语读后续写 · 自动批改 Skill

**v1.1.1**（2026-09-26） · [更新日志](CHANGELOG.md) · [GPL-3.0 许可](LICENSE) · 作者 [Cocogoat-77](https://github.com/Cocogoat-77)

把学生**手写**的读后续写答题卡（扫描件）批量转成结构化批改报告（HTML + A4 PDF）；批整班时还会顺带生成一份班级成绩台账。

这是一个 [WorkBuddy](https://www.workbuddy.cn) Skill，也可以只把它当作一套 **JSON → HTML/PDF 报告渲染管线**单独使用——`scripts/render.py` 不依赖 WorkBuddy，喂给它一份符合契约的 JSON 就能出报告。

## 输出什么

每人一份 A4 报告，11 个板块：

| # | 板块 | 内容 |
|---|---|---|
| 1 | 大标题 | `{M}月{D}日{题型}-{姓名}` |
| 2 | 评语 | 得分 / 完成度 / 情节内容 / 词汇句式和语法 |
| 3 | 本次作文我的问题 | 2–3 个问题标签 |
| 4 | 卷面点评 | 优秀 / 中等 / 差 + 描述 |
| 5 | 逐句批改 | 学生原文全文，错误处红字删除线 + 订正文本灰底红字 |
| 6 | 错误分析详情 | 正确形式 + 错误类型说明 |
| 7 | 情节分析 | 原文情节梳理 / 续写情节推理 / 学生续写大纲 / 点评 / 衔接与过渡分析 |
| 8 | 出彩表达 | 逐句赏析 |
| 9 | 个性化提升 | 动作 / 心理 / 语言 / 环境描写 + 结尾句 + 更多表达 |
| 10 | 我的作文润色 | 整合修订后的两段完整润色稿 |
| 11 | 学生佳句 + 场景词汇 | 班级级内容，同班共享 |

批整班时额外产出 `班级台账.xlsx`：`成绩台账`（学号/姓名/班级/得分/词数/语法错误数/卷面等级/问题标签/主要错误类型）+ `班级诊断`（得分分布、错误类型人次排行、各班均分）。

## 安装

**1. 放文件** —— 把 `gaokao-continuation-essay-grading/` 整个目录放到：

```
C:\Users\<你的用户名>\.workbuddy\skills\
```

（只想在某个项目里用，也可以放到该项目的 `.workbuddy\skills\` 下。）

**2. 装依赖**

```bash
python -m pip install pymupdf playwright openpyxl
python -m playwright install chromium
# 只有要上架为付费技能（Pay Skill）时才需要：
python -m pip install pycryptodome
```

Chromium 下载慢的话先换镜像：

```bash
set PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
python -m playwright install chromium
```

**3. 重开一个 WorkBuddy 会话**，让它重新扫描 skills 目录。

> 依赖说明：`pymupdf` 给 PDF 盖页眉页脚、`playwright` 把 HTML 转成 A4 PDF、`openpyxl` 生成台账。
> 模板用到系统字体 `C:\Windows\Fonts\SIMYOU.TTF`（幼圆，Windows 自带）。

## 用法

在 WorkBuddy 里直接说：

> 用读后续写批改 skill，批改一下这张答题卡（附图）

第一次用一道新题目时，需要先提供三样：**原题前文全文 + 两段已给出的首句 + 批改日期**。这三样是「情节分析」板块的必需材料；缺了原题只会做语言层批改（逐句批改、错误分析、出彩表达、个性化提升），不会瞎编情节。

批同一道题的后续学生时，无需重复提供。

### 只当渲染管线用

```bash
# 单篇
python scripts/render.py --json results/<学号>_<姓名>.json --outdir ./out
# 批量
python scripts/render.py --jsondir ./results --outdir ./out
# 只要 HTML，不转 PDF
python scripts/render.py --jsondir ./results --outdir ./out --html-only
# 换版式：默认是原版（1:1 复刻批改报告样本），打印用 apple
python scripts/render.py --jsondir ./results --outdir ./out --theme apple
python scripts/render.py --list-themes
```

学生 JSON 的字段契约见 [`references/report-spec.md`](references/report-spec.md) 第五节；
两套版式的设计规范、修订标记口径、模板占位符契约见 [`references/themes.md`](references/themes.md)。

### 报告版式

| `--theme` | 说明 |
|---|---|
| `default` | **原版**（默认）—— 逐元素复刻批改报告样本的版式与配色 |
| `apple` | **Apple 风格** —— 纯白纸 + 灰色圆角卡片 + 只描边的胶囊标题，零暗底。**要打印选它**，不费墨、不糊字 |

两套共用同一份 JSON、同一套占位符契约，换皮肤只是换 CSS，不影响内容与判定。
`--marks strict` 可把修订标记强制拉回 `#CACACA` 灰底 + 红字的规格口径（默认跟随皮肤配色）。

## 上架为付费技能（Pay Skill）

本 Skill 可以上架 SkillHub 作为**按报告篇数计费**的付费技能（默认 `0.01` 元/篇），
付费链路基于支付宝 **AI 按量付费（HTTP 402 协议）**，四步编排 `probe → pay → complete → ack`：

| 步骤 | 做什么 |
|---|---|
| **probe** | 请求资源；未付款时服务端返回 **HTTP 402** + **`Payment-Needed`** 账单头（Base64URL，含 RSA2 商家签名），并把订单落库 |
| **pay** | 把账单交给支付宝官方支付能力拉起收银台，用户本人付款（Agent 只编排，不代付） |
| **complete** | 付款后携带 **`Payment-Proof`** 重试原请求；服务端调 `alipay.aipay.agent.payment.verify` 验付，通过后幂等履约 |
| **ack** | 交付后调 `alipay.aipay.agent.fulfillment.confirm` 确认履约；失败可重试且保持幂等 |

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

计费口径、协议字段、五项必做控制（402 账单下发 / 携带凭证重试 / 验付调用 / 履约确认 /
订单持久化与幂等）、配置环境变量、上线前核对清单，全部见
[`references/skillpay.md`](references/skillpay.md)。

> **安全提醒**：商家应用私钥只从环境变量或本地 `skillpay.local.json` 读取，
> **不要提交到仓库**（`.gitignore` 已排除 `skillpay.local.json`、`state/`、`*.pem`）。

## 目录结构

```
gaokao-continuation-essay-grading/
├── SKILL.md                        Skill 主文件：工作流、硬约束、质量闸门
├── LICENSE                         GPL-3.0 许可证全文
├── CHANGELOG.md                    版本变更记录
├── README.md
├── assets/
│   ├── report-template.html        原版 A4 报告模板（默认皮肤）
│   └── themes/
│       └── report-template-apple.html   Apple 风格模板（打印版）
├── references/
│   ├── report-spec.md              版式 + 配色 + 数据契约（原版的唯一权威规格）
│   ├── themes.md                   两套皮肤的设计规范、修订标记口径、模板占位符契约
│   ├── skillpay.md                 支付宝 AI 按量付费（402 协议）接入规范
│   ├── rubric.md                   25 分制档位与校准锚点、固定句式
│   └── tag-library.md              问题标签库 / 错误类型库 / 衔接检查用语
└── scripts/
    ├── manifest.py                 按学号配对答题卡与已有报告，生成作业清单
    ├── aggregate.py                按班级聚合佳句与场景词汇，生成成绩台账
    ├── render.py                   JSON → HTML → A4 PDF（--theme 选皮肤）
    ├── pack_for_upload.py          白名单打包，供手动上传 GitHub（见「数据与隐私」）
    └── skillpay/                   付费改造（Pay Skill）
        ├── config.py               配置与沙箱/生产切换
        ├── store.py                订单持久化与幂等（SQLite）
        ├── bill.py                 402 账单下发（Payment-Needed + RSA2 签名）
        ├── proof.py                Payment-Proof 解析
        ├── gateway.py              payment.verify / fulfillment.confirm 调用
        ├── service.py              probe / pay / complete / ack 编排
        ├── server.py               本地 HTTP 服务（真实 402 状态码）
        ├── cli.py                  命令行入口
        └── selftest.py             离线自测（生成密钥 + mock 网关）
```

## 设计要点

- **不绑定任何具体题目。** 原题前文、两段首句、情节梳理、场景词汇全部来自当次 `assignment.json` 与该生实际作文。换一道题就换一份 `assignment.json`，Skill 本体不动。
- **手写转写忠于原样。** 学生写错的拼写、时态、搭配一律照抄，不自动改正；学生自己划掉/涂改的词一律不转写、不计词数、不算错误——判划改只看一次，拿不准就按划掉处理，不反复纠缠。
- **班级级内容按班聚合。** `学生佳句` 与 `场景词汇` 同班共享、跨班不同，绝不跨班取材；佳句取全班前 N 句，允许出现学生本人的句子。
- **版式可替换。** 报告内容与版式解耦：模板只认一套占位符契约，换成另一套皮肤不影响任何正文与判定。打印场景建议用 `--theme apple`（零暗底）。

## 数据与隐私

**本仓库不含任何学生数据。** 只有纯文本文件（Skill 文档 + 2 份 HTML 模板 + 4 个 Python 脚本）。

### 用手动上传（网页端 Add file → Upload files）

**注意：GitHub 网页端的上传框不读 `.gitignore`** —— 拖进去什么就传什么。手动上传时安全网不是 `.gitignore`，而是你自己核对那份上传列表。

所以提供了一个白名单打包脚本，只把该上传的文件拷到一处，其余东西无论在哪都不会被带进去：

```bash
python scripts/pack_for_upload.py            # 打到 ./上传到GitHub/
python scripts/pack_for_upload.py --dry-run  # 只打印清单，不拷文件
```

然后把 `上传到GitHub/` 整个文件夹拖进上传框即可（GitHub 会保留相对路径）。**上传前请扫一眼仓库里 `assets/`、`references/`、`scripts/` 之外有没有多出别的东西。**

### 用 git 命令上传

答题卡扫描件、批改报告、`results/` `final/` `out/` 等目录**一律不要提交** —— 那里面是学生的个人信息。`.gitignore` 已经把这些路径排除掉了，`git add -A` 不会收进去。

> 两条通用提醒：
> 1. `.gitignore` 只对 `git` 命令生效（`git add` / `git status` / GitHub Desktop 也遵守），**对网页端拖拽上传无效**。
> 2. **删掉文件删不掉 Git 历史。** 一旦学生信息被推上去过，事后删文件没用，只能重写历史或删库重建。所以宁可在上传前拦住。

## 版权与许可

```
Copyright (C) 2026 Cocogoat-77

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
```

本项目按 **[GNU 通用公共许可证第 3 版（GPL-3.0）](LICENSE)** 授权 —— 许可证全文见 `LICENSE`。

简单说：你可以自由使用、修改、再发布；但**如果你发布了自己改过的版本，那个版本也必须以 GPL-3.0 开源**（这就是 copyleft，也是它和 MIT 最大的区别 —— MIT 允许别人拿去闭源）。

> 本项目作者：**Cocogoat-77**（<https://github.com/Cocogoat-77>）

## 版式来源说明

本项目的**报告版式与部分固定措辞，参考并复刻自一份批改报告样本**（板块结构、配色、字号、行距等版式参数系对该样本逐元素测量而来；少量固定话术如「完成度」评语、「出彩表达」心得语、问题标签名与衔接检查项表述，与该样本一致）。

- 这部分内容的权利**不归属于本项目作者**，也**不在本项目的 GPL-3.0 授权范围内**（GPL 只能授权作者本人拥有权利的部分）。
- 本项目将其用于**教学场景下的格式还原**，作者无意主张对上述内容的任何权利。
- 如需将本项目用于商业用途，请自行评估相关权利风险。

除此之外的脚本、模板与文档均为本项目作者原创，按 [GPL-3.0](LICENSE) 授权。

## 高考评分标准说明

`references/rubric.md` 中的 25 分制档位划分依据公开的普通高等学校招生全国统一考试英语科评分标准整理，属公开信息；其中的分数校准锚点由作者对实际批改结果统计得出。

## 致谢

- **开发方式**：本项目的脚本、两套报告模板、参考文档与发布流程，是在 **[WorkBuddy](https://www.workbuddy.cn) 的 AI 助手**协作下、经人机往复迭代打磨而成；选题、评分口径、版式取舍与最终验收由作者（在职高中英语教师）决定。
- **数据来源**：判定阈值与校准锚点来自作者对本班实际批改结果的统计；报告结构参考自一份批改报告样本（见上「版式来源说明」）。
- **致使用者**：感谢每一位使用、反馈并改进这个 Skill 的老师。

> 注：AI 助手不持有本项目著作权，也不在 [GPL-3.0](LICENSE) 的授权方之列 —— 版权归作者所有（见上「版权与许可」）。此处仅作开发过程的如实说明。
