# -*- coding: utf-8 -*-
"""
pack_for_upload.py —— 手动上传 GitHub 前，把「该上传的文件」按原目录结构拷到一处。

为什么需要它
------------
GitHub 网页端的 `Add file → Upload files` **不读 .gitignore** —— 拖进去什么就传什么。
所以手动上传时，安全网不是 .gitignore（那份黑名单只对 git 命令生效），
而应该是一份**白名单**：只放行该上传的文件，白名单之外的东西一律进不了包。

本脚本就是这张白名单的执行者。它只拷贝下面 WHITELIST 列出的文件，
学生数据、批改产物、缓存、虚拟环境等等，无论存在于哪里都不会被带进去。

用法
----
    python scripts/pack_for_upload.py                  # 打到 ./上传到GitHub/
    python scripts/pack_for_upload.py --outdir D:/上传
    python scripts/pack_for_upload.py --dry-run         # 只打印清单，不拷文件

拷完把整个 `上传到GitHub/` 文件夹拖进 GitHub 的上传框即可（GitHub 会保留相对路径）。
"""
import argparse
import os
import shutil
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============ 白名单：只有这些文件该上传 ============
# 新增文件时记得同步这里，以及 README 的「目录结构」一节。
WHITELIST = [
    # --- 根目录 ---
    "SKILL.md",             # Skill 主文件：工作流、硬约束、质量闸门
    "README.md",
    "LICENSE",
    ".gitignore",           # 对用 git 命令的人是安全网；手动上传时它只是个说明文件
    ".gitattributes",
    # --- 模板 ---
    "assets/report-template.html",              # 原版皮肤
    "assets/themes/report-template-apple.html",  # Apple 打印版皮肤
    # --- 参考文档 ---
    "references/report-spec.md",   # 版式 + 配色 + 数据契约（原版权威规格）
    "references/themes.md",        # 两套皮肤的设计规范 + 模板占位符契约
    "references/rubric.md",        # 25 分制档位与校准锚点
    "references/tag-library.md",   # 标签库 / 错误类型库 / 衔接检查用语
    # --- 脚本 ---
    "scripts/manifest.py",
    "scripts/aggregate.py",
    "scripts/render.py",
    "scripts/pack_for_upload.py",
]

# ============ 黑名单：这些东西一个都不能上传 ============
# 仅用于打印提醒，不参与拷贝逻辑（拷贝只认白名单，所以黑名单漏写也不会出事）。
NEVER_UPLOAD = [
    "部分答题卡/  部分报告/      —— 答题卡扫描件、批改报告（含姓名学号）",
    "results/  results_bak/  final/  out/  —— 批改中间产物与报告（含姓名、成绩、手写笔迹）",
    "*.jpg  *.jpeg  *.png        —— 学生手写照片、裁剪图",
    "*.pdf                       —— 生成好的批改报告",
    "*.xlsx                      —— 班级台账（全班姓名 + 成绩）",
    "__pycache__/  .venv/        —— Python 缓存与虚拟环境",
]


def pack(outdir, dry_run=False):
    missing = []
    copied = []

    outdir_abs = os.path.abspath(outdir)
    if outdir_abs.startswith(os.path.abspath(SKILL_DIR) + os.sep):
        sys.exit("输出目录不能放在 Skill 目录内部（会把自己套进去）：%s\n"
                 "换个位置，比如 --outdir D:/上传到GitHub" % outdir_abs)

    print("白名单 %d 个文件：" % len(WHITELIST))
    for rel in WHITELIST:
        src = os.path.join(SKILL_DIR, rel)
        if not os.path.exists(src):
            missing.append(rel)
            print("  [缺失] %s" % rel)
            continue
        size = os.path.getsize(src)
        if dry_run:
            print("  [OK]   %-44s %6d B" % (rel, size))
            continue
        dst = os.path.join(outdir_abs, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
        print("  [拷入] %-44s %6d B" % (rel, size))

    if missing:
        print("\n[警告] 有 %d 个白名单文件不存在，请检查路径。" % len(missing))

    if not dry_run:
        print("\n已输出到：%s" % outdir_abs)
        print("共 %d 个文件。把整个文件夹拖进 GitHub 的 Add file → Upload files 即可。"
              % len(copied))

    print("\n以下内容【绝不在包内】，上传前请再扫一眼上传列表，确认没有这些东西：")
    for line in NEVER_UPLOAD:
        print("  ×  " + line)

    return 0 if not missing else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join(os.getcwd(), "上传到GitHub"),
                    help="输出目录，默认 ./上传到GitHub")
    ap.add_argument("--dry-run", action="store_true", help="只打印清单，不拷文件")
    args = ap.parse_args()
    sys.exit(pack(args.outdir, args.dry_run))


if __name__ == "__main__":
    main()
