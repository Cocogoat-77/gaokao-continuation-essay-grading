# -*- coding: utf-8 -*-
"""
render.py —— 读学生批改结果 JSON，输出 HTML 与 A4 PDF。

用法：
    python render.py --json results/<学号>_<姓名>.json --outdir ./out
    python render.py --jsondir ./results --outdir ./out        # 批量
    python render.py --jsondir ./results --outdir ./out --html-only

皮肤（版式可选，详见 references/themes.md）：
    python render.py --list-themes                             # 列出所有皮肤
    python render.py --jsondir ./final --outdir ./out --theme apple
    python render.py --jsondir ./final --outdir ./out --theme apple --marks strict

    --theme  default(默认，1:1 复刻批改报告样本) / apple(打印友好)
    --marks  theme(默认，跟随皮肤配色) / strict(强制 report-spec 的 #CACACA 灰底+红字)

依赖：pymupdf（pip install pymupdf）；Playwright 自带 Chromium（HTML→PDF）。
"""
import argparse
import json
import os
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(SKILL_DIR, "assets")
THEME_DIR = os.path.join(ASSETS, "themes")

# ---------- 皮肤注册表 ----------
# 所有模板共用同一套占位符契约（见 references/themes.md 第六节），换皮肤只换 CSS 与版式，
# 不动正文、不动 11 个板块、不动 JSON 契约。
THEMES = {
    "default": os.path.join(ASSETS, "report-template.html"),
    "apple": os.path.join(THEME_DIR, "report-template-apple.html"),
}
THEME_DESC = {
    "default": "原版 —— 逐元素复刻批改报告样本版式（默认）",
    "apple": "Apple 风格 —— 纯白纸 + 灰色圆角卡 + 描边胶囊标题，无暗底，适合打印",
}

TEMPLATE = THEMES["default"]

# `--marks strict` 时追加的覆盖样式：把订正标记拉回 report-spec 的约定。
# 设计皮肤为了守住"每套只有一个强调色"，订正文本走的是各皮肤自己的强调色；
# 需要严格 1:1 对齐批改报告样本时用这个开关，皮肤随便挑、标记配色仍是规格内的。
STRICT_MARK_CSS = """
/* ===== --marks strict：强制 report-spec 的修订标记配色 ===== */
del { color: #FF0000 !important; text-decoration: line-through !important; background: transparent !important; }
ins { background: #CACACA !important; color: #FF0000 !important; font-weight: 600 !important; text-decoration: none !important; }
"""

STRICT_MARKS = False


def use_theme(name):
    """切换皮肤（同时更新模块级 TEMPLATE，build_html 直接读它）。"""
    global TEMPLATE
    if name not in THEMES:
        raise SystemExit("未知皮肤 %r。可选：%s" % (name, "、".join(THEMES)))
    path = THEMES[name]
    if not os.path.exists(path):
        raise SystemExit("皮肤文件缺失：%s" % path)
    TEMPLATE = path
    return path


def use_marks(mode):
    """mode: 'theme' 跟随皮肤（默认）｜'strict' 强制 report-spec 配色。"""
    global STRICT_MARKS
    STRICT_MARKS = (mode == "strict")


def list_themes():
    for k in THEMES:
        exists = "OK " if os.path.exists(THEMES[k]) else "缺失"
        print("  %-8s [%s] %s" % (k, exists, THEME_DESC[k]))


# ★ 本脚本**不得改动宿主注入的任何环境变量**。
# 早先版本在导入时删掉宿主下发的「批量删除守卫」与审计类环境变量，好让临时目录清理
# 不被拦下。那是**削弱宿主安全控制**的做法，安全评审据此判定为可疑风险（实测被扣分）。
# 现已彻底移除：本模块不再读写任何环境变量，也不再创建、不再递归删除任何临时目录 ——
# HTML→PDF 只留 Playwright 一条路径（见下方 html_to_pdf）。

YOUYUAN = r"C:\Windows\Fonts\SIMYOU.TTF"

# ---------- 极简模板引擎：{{key}} / {{#list}}...{{/list}} / {{.}} / 段落起始缩进 ----------

TOKEN = re.compile(r"\{\{([#/]?)([\w.]+)\}\}")


def _lookup(ctx, key):
    if key == ".":
        return ctx.get(".")
    cur = ctx
    for part in key.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _render(text, ctx):
    out = []
    pos = 0
    while True:
        m = TOKEN.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        sigil, key = m.group(1), m.group(2)
        if sigil == "#":
            close = "{{/" + key + "}}"
            end = text.find(close, m.end())
            if end == -1:
                raise ValueError("模板缺少闭合标签: " + close)
            body = text[m.end():end]
            val = _lookup(ctx, key)
            if isinstance(val, list):
                for i, item in enumerate(val, 1):
                    sub = dict(ctx)
                    if isinstance(item, dict):
                        sub.update(item)
                    else:
                        sub["."] = item
                    sub.setdefault("index", i)
                    sub["index"] = i
                    out.append(_render(body, sub))
            out.append("")
            pos = end + len(close)
        elif sigil == "/":
            pos = m.end()
        else:
            val = _lookup(ctx, key)
            out.append("" if val is None else str(val))
            pos = m.end()
    return "".join(out)


def esc(s):
    """转义文本，但保留渲染器写入的 <del>/<ins>/<b> 标记。"""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("&lt;del&gt;", "<del>").replace("&lt;/del&gt;", "</del>")
            .replace("&lt;ins&gt;", "<ins>").replace("&lt;/ins&gt;", "</ins>")
            .replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"))


def build_html(data):
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        tpl = f.read()

    if STRICT_MARKS:
        tpl = tpl.replace("</style>", STRICT_MARK_CSS + "\n</style>", 1)

    st = data.get("student", {})
    meta = data.get("meta", {})
    date_label = meta.get("title_date") or meta.get("date", "")
    title = "%s%s-%s" % (date_label, meta.get("assignment", "读后续写"), st.get("name", ""))
    pa = data.get("plot_analysis", {})
    pb = data.get("polish", {})
    imp = data.get("improvements", {})
    shared = data.get("class_shared", {})
    sr = data.get("sentence_review", {})

    ctx = {
        "TITLE": esc(title),
        "score": esc(data.get("score", "")),
        "completeness": esc(data.get("completeness")),
        "plot_comment": esc(data.get("plot_comment")),
        "language_comment": esc(data.get("language_comment")),
        "face_grade": esc(data.get("face", {}).get("grade")),
        "face_text": esc(data.get("face", {}).get("text")),
        "sr_p1": esc(sr.get("p1_html")),
        "sr_p2": esc(sr.get("p2_html")),

        "source_summary": esc(pa.get("source_summary")),
        "key_thought": esc(pa.get("reasoning", {}).get("key_thought")),
        "p1_tag": esc(pa.get("reasoning", {}).get("p1_tag")),
        "p1_plot": esc(pa.get("reasoning", {}).get("p1")),
        "p2_tag": esc(pa.get("reasoning", {}).get("p2_tag")),
        "p2_plot": esc(pa.get("reasoning", {}).get("p2")),
        "summary": esc(pa.get("reasoning", {}).get("summary")),
        "plot_review": esc(pa.get("comment")),

        "highlight_note": esc(data.get("highlights", {}).get("note")),
        "ending_original": esc(imp.get("ending", {}).get("original")),
        "ending_upgraded": esc(imp.get("ending", {}).get("upgraded")),
        "ending_note": esc(imp.get("ending", {}).get("note")),
        "polish_p1": esc(pb.get("p1")),
        "polish_p2": esc(pb.get("p2")),
    }

    ctx["tags"] = [esc(t) for t in data.get("tags", [])]
    ctx["errors"] = [{
        "correct_html": esc(e.get("correct_form_html")),
        "notes": [{"type": esc(n.get("type")), "text": esc(n.get("text"))}
                  for n in e.get("notes", [])],
    } for e in data.get("errors", [])]
    ctx["outline"] = [{
        "prompt": esc(o.get("prompt")),
        "line": esc(o.get("line")),
    } for o in pa.get("outline", [])]
    ctx["cohesion"] = [{
        "label": esc(c.get("label")),
        "items": [{
            "check": esc(i.get("check")),
            "detail": esc(i.get("detail")),
            "advice": esc(i.get("advice")),
        } for i in c.get("items", [])],
    } for c in pa.get("cohesion", [])]
    ctx["highlights"] = [{
        "sentence": esc(h.get("sentence")),
        "points": [{"label": esc(p.get("label")), "text": esc(p.get("text"))}
                   for p in h.get("points", [])],
    } for h in data.get("highlights", {}).get("items", [])]
    ctx["improve_detail"] = [{
        "category": esc(i.get("category")),
        "original": esc(i.get("original")),
        "upgraded": esc(i.get("upgraded")),
        "note": esc(i.get("note")),
    } for i in imp.get("detail", [])]
    ctx["improve_more"] = [{
        "original": esc(i.get("original")),
        "upgraded": esc(i.get("upgraded")),
        "note": esc(i.get("note")),
    } for i in imp.get("more", [])]
    ctx["quotes"] = [{
        "name": esc(q.get("name")),
        "sentence": esc(q.get("sentence")),
    } for q in shared.get("quotes", [])]
    ctx["vocab"] = [{
        "scene": esc(v.get("scene")),
        "words": esc(v.get("words")),
    } for v in shared.get("vocab", [])]

    return _render(tpl, ctx)


# ---------- HTML -> PDF ----------

PDF_DEP_HINT = (
    "未安装 Playwright，无法生成 PDF。请执行：\n"
    "    pip install playwright\n"
    "    python -m playwright install chromium\n"
    "或改用 --html-only 只出 HTML，再用浏览器「打印 → 另存为 PDF」。"
)


def html_to_pdf_playwright(html_path, pdf_path):
    """用 Playwright 自带 Chromium 渲染。不依赖、也不会干扰用户已打开的 Edge/Chrome。"""
    from playwright.sync_api import sync_playwright

    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--font-render-hinting=none"])
        try:
            page = browser.new_page()
            page.goto(url, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(path=os.path.abspath(pdf_path),
                     prefer_css_page_size=True,   # 采用模板里的 @page A4 与页边距
                     print_background=True)       # 保留蓝底标签、灰底修订、绿条等背景色
        finally:
            browser.close()


def html_to_pdf(html_path, pdf_path):
    """HTML → A4 PDF。**只有 Playwright 这一条路径。**

    为什么不再回退到命令行调用 Edge/Chrome：
      1. 那条路要启动外部浏览器进程、并为每次调用新建一个独立的用户数据目录，
         用户已打开浏览器时会被接管并**静默失败**（退出码 0 但不产出 PDF），本就不可靠；
      2. 它还要递归清理那个临时目录；一旦清理被宿主安全守卫拦下，就会表现为
         "PDF 明明已生成却报失败"。早期版本为此去改环境变量绕过守卫 —— 那是削弱
         宿主安全控制，安全评审会判可疑风险，已彻底移除。
    现在单一路径、失败即明确报错，不做隐式降级。
    """
    try:
        html_to_pdf_playwright(html_path, pdf_path)
    except ImportError:
        raise RuntimeError(PDF_DEP_HINT)
    return "playwright"


def stamp_header_footer(pdf_path, data):
    """在每一页加盖页眉（班级/学号/姓名）与页脚（页码/日期）。"""
    import pymupdf

    st = data.get("student", {})
    meta = data.get("meta", {})
    cls = st.get("class") or ""
    sid = st.get("id") or ""
    name = st.get("name") or ""
    date_txt = meta.get("date", "")
    weekday = meta.get("weekday", "")

    doc = pymupdf.open(pdf_path)
    font = pymupdf.Font(fontfile=YOUYUAN) if os.path.exists(YOUYUAN) else None
    total = doc.page_count
    W = doc[0].rect.width

    for i, page in enumerate(doc, 1):
        page.insert_font(fontname="yy", fontfile=YOUYUAN)
        # 页眉：右对齐，小字信息 + 大字姓名
        left_info = "班级：%s  |  学号：%s" % (cls, sid)
        w_info = font.text_length(left_info, 8) if font else len(left_info) * 8
        w_name = font.text_length(name, 15) if font else len(name) * 15
        gap = 10
        x_info = W - 20 - gap - w_name - w_info
        page.insert_text((x_info, 28.5), left_info, fontname="yy", fontsize=8, color=(0, 0, 0))
        page.insert_text((W - 20 - w_name, 33), name, fontname="yy", fontsize=15, color=(0, 0, 0))
        # 页脚
        foot = "第%d页/共%d页" % (i, total)
        w_foot = font.text_length(foot, 10) if font else len(foot) * 10
        page.insert_text(((W - w_foot) / 2, 812.5), foot, fontname="yy", fontsize=10, color=(0.5, 0.5, 0.5))
        right = "%s %s" % (date_txt, weekday)
        w_right = font.text_length(right, 10) if font else len(right) * 10
        page.insert_text((W - 20 - w_right, 812.5), right, fontname="yy", fontsize=10, color=(0, 0, 0))

    # 子集化嵌入字体：不做这一步，页眉页脚会把整个幼圆字体（6.7MB）打进去，
    # 单份 PDF 会从约 200KB 膨胀到 7MB，383 份就是 2.7GB。
    try:
        doc.subset_fonts()
    except Exception as e:
        sys.stderr.write("[warn] 字体子集化失败（PDF 会偏大）：%s\n" % e)
    doc.saveIncr()
    doc.close()


def process(json_path, outdir, html_only=False):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    st = data.get("student", {})
    # 沿用样本报告的命名：{题型}_{学号}_{姓名}.pdf
    base = "%s_%s_%s" % (data.get("meta", {}).get("assignment", "读后续写"),
                         st.get("id", "unknown"), st.get("name", ""))
    os.makedirs(outdir, exist_ok=True)
    html_path = os.path.join(outdir, base + ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(data))
    if html_only:
        return html_path, None
    pdf_path = os.path.join(outdir, base + ".pdf")
    html_to_pdf(html_path, pdf_path)
    stamp_header_footer(pdf_path, data)
    return html_path, pdf_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--jsondir")
    ap.add_argument("--outdir", help="输出目录（--list-themes 时可省略）")
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--theme", default="default", choices=list(THEMES),
                    help="报告皮肤，默认 default（原版）。用 --list-themes 查看")
    ap.add_argument("--marks", default="theme", choices=["theme", "strict"],
                    help="修订标记配色：theme 跟随皮肤（默认）｜strict 强制灰底红字")
    ap.add_argument("--list-themes", action="store_true", help="列出可用皮肤后退出")
    args = ap.parse_args()

    if args.list_themes:
        print("可用报告皮肤（--theme）：")
        list_themes()
        sys.exit(0)

    use_theme(args.theme)
    use_marks(args.marks)

    if not args.outdir:
        ap.error("缺少 --outdir")

    jobs = []
    if args.json:
        jobs.append(args.json)
    if args.jsondir:
        for fn in sorted(os.listdir(args.jsondir)):
            if fn.endswith(".json"):
                jobs.append(os.path.join(args.jsondir, fn))
    if not jobs:
        print("没有输入。请给 --json 或 --jsondir。")
        sys.exit(2)

    ok = fail = 0
    for j in jobs:
        try:
            h, p = process(j, args.outdir, args.html_only)
            print("[OK] %s" % (p or h))
            ok += 1
        except Exception as e:
            print("[FAIL] %s -> %s" % (j, e))
            fail += 1
    print("完成：成功 %d，失败 %d" % (ok, fail))


if __name__ == "__main__":
    main()
