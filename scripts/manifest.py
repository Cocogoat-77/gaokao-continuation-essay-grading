# -*- coding: utf-8 -*-
"""
manifest.py —— 扫描答题卡与批改报告目录，按学号配对，生成作业清单。

用法：
    python manifest.py --answer-dir "<答题卡目录>" --report-dir "<已有的批改报告目录，可省略>" \
                       --out assignment-manifest.json

输出 manifest.json 结构：
{
  "count": 382,
  "matched": [{"id":"<学号>","name":"<姓名>","class":"<N>班","answer":"...jpg","report":"...pdf"}],
  "answer_only": ["<只有答题卡、没有报告的学号>"],
  "report_only": ["<只有报告、没有答题卡的学号>", ...]
}
"""
import argparse
import json
import os
import re
import sys

ID_RE = re.compile(r"(\d{6})")
NAME_RE = re.compile(r"_\d{6}_([^_.]+)")
CLASS_RE = re.compile(r"(\d+班)")


def scan(dirpath, exts):
    out = {}
    if not dirpath or not os.path.isdir(dirpath):
        return out
    for fn in sorted(os.listdir(dirpath)):
        if not fn.lower().endswith(exts):
            continue
        m = ID_RE.search(fn)
        if m:
            out[m.group(1)] = os.path.join(dirpath, fn)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer-dir", required=True, help="答题卡图片目录")
    ap.add_argument("--report-dir", help="已有批改报告目录（用于对照/提取班级与姓名）")
    ap.add_argument("--out", default="assignment-manifest.json")
    args = ap.parse_args()

    answers = scan(args.answer_dir, (".jpg", ".jpeg", ".png", ".webp", ".pdf"))
    reports = scan(args.report_dir, (".pdf",)) if args.report_dir else {}

    matched, answer_only, report_only = [], [], []
    for sid in sorted(set(answers) | set(reports)):
        a = answers.get(sid)
        r = reports.get(sid)
        if a and r:
            name = ""
            m = NAME_RE.search(os.path.basename(r))
            if m:
                name = m.group(1)
            else:
                m2 = re.search(r"[-_]([^\-_.]+)\.pdf$", os.path.basename(r))
                name = m2.group(1) if m2 else ""
            cls = ""
            m3 = CLASS_RE.search(os.path.basename(r))
            if m3:
                cls = m3.group(1)
            matched.append({"id": sid, "name": name, "class": cls, "answer": a, "report": r})
        elif a:
            answer_only.append(sid)
        else:
            report_only.append(sid)

    data = {
        "count": len(matched),
        "matched": matched,
        "answer_only": answer_only,
        "report_only": report_only,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("答题卡 %d 份，已有报告 %d 份，配对成功 %d 份" % (len(answers), len(reports), len(matched)))
    if answer_only:
        print("仅有答题卡、无报告（需新批改）：%s" % ", ".join(answer_only[:20]))
    if report_only:
        print("仅有报告、无答题卡（本批跳过）：%s" % ", ".join(report_only[:20]))
    print("清单已写入 %s" % args.out)


if __name__ == "__main__":
    main()
