#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""环境依赖自检 —— 只检查、只报告，不安装任何东西。

给 Agent 用的第一步：跑一遍看缺什么，按输出把缺的装上，再跑一遍确认。

用法：
    python scripts/check_env.py           # 人类可读报告
    python scripts/check_env.py --json     # 机读输出

退出码：0 = 必需项齐全；1 = 有必需项缺失。

设计约束（与 SKILL.md 硬约束一致）：
- 只做 importlib 探测与文件存在性检查；**不启动任何外部进程、不起 shell、不装包**
- **不读不写任何环境变量**；浏览器目录由家目录推出，不依赖 %LOCALAPPDATA%
"""
import argparse
import importlib.util
import json
import os
import sys

# 必需：缺了影响出报告
REQUIRED = (
    ("pymupdf", "PDF 盖页眉页脚 + 图片裁剪/放大（本机 PIL 不可用，靠它）"),
    ("playwright", "HTML → A4 PDF 的唯一渲染器"),
    ("openpyxl", "班级成绩台账 Excel（只批改单人时暂不需要）"),
)
# 可选：只在特定场景需要
OPTIONAL = (
    ("Crypto", "付费层 402 账单的 RSA2 签名（pycryptodome）"),
    ("cryptography", "RSA2 签名备选实现（本机可能残缺，优先用 pycryptodome）"),
)

FONT = r"C:\Windows\Fonts\SIMYOU.TTF"


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def find_chromium():
    """在家目录下的 ms-playwright 里找 Chromium，不依赖环境变量。"""
    base = os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright")
    if not os.path.isdir(base):
        return None
    for name in sorted(os.listdir(base), reverse=True):
        if not name.startswith("chromium"):
            continue
        for rel in (("chrome-win", "chrome.exe"), ("chrome-win64", "chrome.exe")):
            p = os.path.join(base, name, *rel)
            if os.path.isfile(p):
                return p
    return None


def collect():
    required, optional = [], []
    for name, why in REQUIRED:
        required.append({"name": name, "why": why, "ok": has_module(name)})
    for name, why in OPTIONAL:
        optional.append({"name": name, "why": why, "ok": has_module(name)})

    chromium = find_chromium()
    font_ok = os.path.isfile(FONT)

    missing = [r["name"] for r in required if not r["ok"]]
    if missing:
        missing.append("playwright-chromium")
    return {
        "python": sys.executable,
        "required": required,
        "optional": optional,
        "chromium": chromium,
        "font": {"path": FONT, "ok": font_ok},
        "missing_required": missing,
        "ready": not missing,
    }


def install_hint(report):
    """给出可直接执行的安装命令（用当前解释器，即 WorkBuddy 隔离环境）。"""
    py = report["python"]
    lines = []
    pkgs = [r["name"] for r in report["required"] if not r["ok"]]
    if pkgs:
        lines.append('%s -m pip install %s' % (py, " ".join(pkgs)))
    if report["chromium"] is None:
        lines.append("%s -m playwright install chromium" % py)
    return lines


def main():
    ap = argparse.ArgumentParser(description="依赖自检（只检查，不安装）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    r = collect()

    if args.json:
        r["install_hint"] = install_hint(r)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["ready"] else 1

    print("环境自检")
    print("  解释器：%s" % r["python"])
    print()
    print("必需组件：")
    for item in r["required"]:
        print("  %s %-12s %s" % ("OK  " if item["ok"] else "缺失", item["name"], item["why"]))
    print("  %s %-12s %s"
          % ("OK  " if r["chromium"] else "缺失", "chromium",
             "Playwright 自带浏览器（HTML→PDF 必需）"))
    print()
    print("可选组件：")
    for item in r["optional"]:
        print("  %s %-12s %s" % ("OK  " if item["ok"] else "未装", item["name"], item["why"]))
    print()
    print("系统字体：%s %s" % ("OK" if r["font"]["ok"] else "缺失（页眉页脚不可用，正文不受影响）",
                             r["font"]["path"]))
    print()

    if r["ready"]:
        print("结论：环境就绪，可以开始批改。")
        return 0

    print("结论：缺少必需组件，先执行以下命令再重跑本脚本：")
    for line in install_hint(r):
        print("  %s" % line)
    print()
    print("提示：Chromium 下载慢可先设镜像再装 ——")
    print("  set PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright")
    return 1


if __name__ == "__main__":
    sys.exit(main())
