# 报告版式与皮肤规范

同一份批改 JSON，可以渲染成两种版式。**内容、11 个板块、字段契约完全不变**，换的只是 CSS 与版式语言。

## 一、怎么选

```bash
python scripts/render.py --list-themes                                  # 先看有哪些
python scripts/render.py --jsondir ./final --outdir ./out               # 默认：原版
python scripts/render.py --jsondir ./final --outdir ./out --theme apple # 换 Apple 版
```

| `--theme` | 名称 | 版式特征 | 什么时候用 |
|---|---|---|---|
| `default` | **原版** | 逐元素复刻批改报告样本的版式与配色 | **默认**。要对齐批改报告样本、要交给家长／教务看"和样本一致" |
| `apple` | **Apple 风格** | 纯白纸 + 灰色圆角卡片 + 描边胶囊标题，**零暗底** | **要打印的时候选它**（见第四节） |

> 皮肤只影响**长相**，不影响**判定**。不管选哪套，`rubric.md` 的评分口径、`tag-library.md` 的标签集合、`report-spec.md` 的板块顺序都必须照办。
> 用户没指定皮肤时用 `default`。

## 二、修订标记的两种口径（`--marks`）

这是选皮肤时唯一需要留意的**语义**差异，不是纯视觉。

| 模式 | 行为 |
|---|---|
| `--marks theme`（默认） | 修订标记**跟随皮肤**：「错误原文」永远是红字+红删除线；「订正文本」用它自己那支强调色 |
| `--marks strict` | 强制回到 `report-spec.md` 的口径：`<del>` 红字+红删除线无底纹；`<ins>` **`#CACACA` 灰底 + 红字** |

两套皮肤在默认（`theme`）模式下订正文本的取色：

| 皮肤 | `<del>` 错误原文 | `<ins>` 订正文本 | 为什么 |
|---|---|---|---|
| `default` | `#FF0000` + 红删除线 | `#CACACA` 灰底 + `#FF0000` 红字 | 就是样本报告的原样 |
| `apple` | `#d70015` + 红删除线 | Action Blue `#0066cc` 加粗 | Apple 调色板无红；强调色留给"该点的东西" |

> 需要"Apple 版式 + 规格内标记配色"时，加 `--marks strict`：
> ```bash
> python scripts/render.py --jsondir ./final --outdir ./out --theme apple --marks strict
> ```
> 它会在模板的 `</style>` 前追加一段 `!important` 覆盖，把 `del`/`ins` 拉回 `report-spec.md` 的 `#CACACA` 灰底 + 红字。

## 三、两套皮肤共通的铁律

1. **每套皮肤只有一个强调色。** 蓝色只用于"这是该点的东西"——板块标题、订正文本、学生姓名、优化建议。不做装饰性用色。
2. **卡片、按钮、文字一律无阴影。** 层级只靠底色差、发丝线、留白。
3. **圆角成套。** 一套皮肤内的圆角值必须收敛在 2–3 个档位（如 8/12/18 + 胶囊），不随手写。
4. **红色只作语义色。** 它只表示"这里错了"，不参与品牌层级，不用于标题、边框、装饰。
5. **`<del>` 与 `<ins>` 必须成对。** 只标真实修改处；不改动正确的部分。详见 `report-spec.md` 第五节。
6. **不得写死任何题目内容。** 模板里不许出现某道题的原题、首句、人物、场景词汇——那些一律来自当次 `assignment.json`。
7. **不得增删板块。** 11 个板块缺一不可，顺序固定。

## 四、各皮肤规范

### 4.1 `default` 原版

**唯一权威是 `references/report-spec.md`**，本文档不重复。核心配色：

| 用途 | 色值 |
|---|---|
| 正文、标题、`【】`标签 | `#000000` |
| 板块标题、板块虚线、强调标签、替换建议 | `#0F86FF` |
| 错误原文 `<del>` | `#FF0000` 文字 + 0.6pt 红色删除线，**无底纹** |
| 订正文本 `<ins>` | `#CACACA` 灰底 + `#FF0000` 红字 |
| 问题标签底 / 段落分析标签底 / 卷面点评底板 | `#DBEDFF` |
| 问题标签、卷面点评实心药丸 | `#0F86FF`（白字） |
| 出彩表达绿条 | `#0DBC51` |
| 学生佳句行底 | `#F8F9FA`，行间虚线 `#DCDCDC` |
| 场景词汇单元格描边 | `#EB5415` |
| 小标题卡图标框 | 底 `#FDF0DC`、边 `#E8B463`、图标 `#B07414` |

字体走 `Times New Roman` + `YouYuan 幼圆` 混排，全部尺寸用 pt。

### 4.2 `apple` Apple 风格（打印版）

| token | 值 |
|---|---|
| 画布 | 纯白 `#ffffff`（全篇只有白纸一个底色） |
| 灰面 | `#f5f5f7`，**只作内嵌圆角卡片**，不做通栏色带 |
| 文字 | ink `#1d1d1f` / muted `#7a7a7a` / muted-2 `#6e6e73` |
| 描边 | hairline `#e0e0e0` / 卡片线 `#e8e8ed` / 分隔 `#f0f0f0` |
| 强调 | Action Blue `#0066cc`（只用在描边与文字上，不做实底填充） |
| 圆角 | 胶囊 `9999px`；灰色卡片 `16px`；白色卡片 `14px` |
| 字体 | `system-ui` / `-apple-system` 系统栈 |

**版式规则：**

- **大标题 = 只有描边的胶囊。** `0.7pt` 蓝描边 + 蓝字 + 全透明底色，靠 `display: table` 收缩到文字宽度。次级小标题（`h3`）用同款但退一级：发丝灰描边 + 墨色字。标签胶囊（问题标签、卷面等级、段落标签）同样是纯描边、不填充。
- **灰色圆角卡片左右内缩 13pt + 自身内边距 13pt = 26pt**，正好等于白底段落的水平内边距 —— 这样灰卡里的文字和白段落里的文字**左边界严丝合缝**，通篇一条竖线。改这几个数值时必须同步改，否则会出现"卡里的字比外面缩进一截"。
- **白底段落与灰卡交替**，用卡片的灰面做分隔，不靠色带。
- **零暗底。** 设计原型里的两块深灰面（出彩表达、我的作文润色）已全部转成白底 + 描边卡；`del`/`ins` 在浅灰卡上仍可读。

## 五、打印注意

**要打印就选 `apple`。** 它是唯一为打印机改造过的皮肤：

- 全篇只有白纸一个底色，灰面仅作浅色卡片 —— **没有大面积深色块**，不费墨、不糊字。
- 标题胶囊、标签胶囊都只有描边、无填充。
- 灰卡是 `#f5f5f7`（约 4% 灰），黑白激光打印出来是很淡的一层，不会盖住字。

另外两条通用提醒：

- **必须开启"打印背景图形"。** `render.py` 走 Playwright 时用的就是 `print_background=True`；若手工用浏览器"打印 → 另存为 PDF"，要自己勾上，否则所有底色与彩色标记都会变白。
- **`@page` 的上下 `margin` 是页眉页脚的安全区**（`render.py` 用 pymupdf 在 46pt 区域内盖章）。改模板时不要把上下边距挪回容器 padding，见下节。

## 六、三个排版坑（改模板时最容易再踩）

**① 全出血底色必须写在 `@page` 上。**
`@page` 带边距时，Chrome 只把 `body` 背景画在**内容区**，四边留白。要铺满整张纸、且每一页都生效：

```css
@page { size: A4; margin: 46pt 0; background: #ffffff; }
```

（另测过 `position: fixed` 出血块：Chrome 打印时**不会**逐页重复，无效。）

**② 上下边距写 `@page`，左右的缩进交给容器。**

```css
@page { margin: 46pt 0; }     /* 左右设 0，上下留 46pt 给页眉页脚 */
.in   { padding: 15pt 26pt; } /* 左右缩进靠容器 */
```

用容器 padding 顶上下留白是**行不通的**——它只对第 1 页生效，第 2 页起内容会顶到 y=0 压住页眉（实测正文最高点压到 y=2，页眉处出现"重影"）。

**③ 胶囊标题用 `display: table`，不要用 `inline-block`。**
两者的 shrink-to-fit 效果一样，但 `inline-block` 会让**紧随其后的正文挤到同一行**；`display: table` 既能收缩到文字宽度，又保持块级独占一行。

## 七、模板契约（改模板／新增皮肤必须遵守）

模板是一个极简模板引擎，只认三个记号：`{{key}}`、`{{#list}}…{{/list}}`、`{{.}}`。
列表体内可用 `{{index}}`（自动从 1 编号）。

**标量占位符：**

| key | 含义 |
|---|---|
| `TITLE` | 报告大标题（`{月}月{日}日{题型}-{姓名}`） |
| `score` | 得分 |
| `completeness` | 【完成度】整句 |
| `plot_comment` | 【情节内容】整段 |
| `language_comment` | 【词汇句式和语法】整段 |
| `face_grade` / `face_text` | 卷面等级 / 卷面描述 |
| `sr_p1` / `sr_p2` | 逐句批改两段全文（内含 `<del>`/`<ins>`） |
| `source_summary` | 原文情节梳理 |
| `key_thought` | 关键思考过程 |
| `p1_tag` / `p1_plot` / `p2_tag` / `p2_plot` | 两段的情节标签与推理 |
| `summary` | 情节推理小结 |
| `plot_review` | 情节点评 |
| `highlight_note` | 出彩表达引言 |
| `ending_original` / `ending_upgraded` / `ending_note` | 结尾句提升三行 |
| `polish_p1` / `polish_p2` | 润色稿两段 |

**列表占位符：**

| 区块 | 每项可用字段 |
|---|---|
| `{{#tags}}` | `{{.}}`（标签文字本身） |
| `{{#errors}}` | `correct_html`；内嵌 `{{#notes}}` → `type`、`text` |
| `{{#outline}}` | `prompt`、`line` |
| `{{#cohesion}}` | `label`；内嵌 `{{#items}}` → `check`、`detail`、`advice` |
| `{{#highlights}}` | `sentence`；内嵌 `{{#points}}` → `label`、`text` |
| `{{#improve_detail}}` | `category`、`original`、`upgraded`、`note` |
| `{{#improve_more}}` | `original`、`upgraded`、`note` |
| `{{#quotes}}` | `name`、`sentence` |
| `{{#vocab}}` | `scene`、`words` |

**注意：** 所有文本都经 `esc()` 转义，但 `<del>` / `</del>` / `<ins>` / `</ins>` / `<b>` / `</b>` 会被**保留为真标签**。所以模板里写 `{{sr_p1}}` 就能直接得到带删除线与灰底的渲染结果，**不要再套一层 HTML 标签**。

**新增一套皮肤的步骤：** 满足上表契约 → 放进 `assets/themes/` → 在 `scripts/render.py` 的 `THEMES` 字典里登记一行（键名即 `--theme` 的取值，同时补一条 `THEME_DESC`）→ 在本文档第四节补一节规范。
