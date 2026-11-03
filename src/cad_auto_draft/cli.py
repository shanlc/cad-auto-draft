"""CLI: python -m cad_auto_draft.cli --input examples/hotel_floor.json --out output

Without --ai, only deterministic rules are used. With --ai, the AI API
is consulted for parameters only (see ai_client.py); geometry is still
deterministic, and any API failure falls back to rules silently.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ai_client import ai_params, apply_params, rule_params
from .dwg import write_dxf
from .layout import build_layout
from .models import Building
from .plan_parser import parse_plan
from .report import write_report
from .validate import validate


def run_build(raw: dict, out_dir: str | Path, params: dict | None = None) -> dict:
    """Shared build used by both the CLI and the GUI.

    Returns the building, layout, checks and output paths. Raises on
    bad input so the GUI can show the error instead of crashing.
    """
    params = params or rule_params()
    building = Building.from_dict(apply_params(raw, params))
    layout = build_layout(building)
    checks = validate(building, layout)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dxf = write_dxf(building, layout, str(out / "draft.dxf"))
    report = write_report(building, layout, checks, params.get("source", "rule"),
                          str(out / "report.md"))
    summary_path = out / "summary.json"
    summary_path.write_text(
        json.dumps({"summary": layout.summary, "checks": checks,
                    "ai_params_source": params.get("source", "rule")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [c for c in checks if c["level"] == "FAIL"]
    return {
        "building": building, "layout": layout, "checks": checks,
        "dxf": dxf, "report": str(report), "summary": str(summary_path),
        "failed": bool(failed),
    }


def main(argv: list[str] | None = None) -> int:
    # Windows Actions runners (and many English Windows installs) use
    # cp1252 for stdout, which cannot encode Chinese. Without this,
    # the first Chinese print ("报告: ...") raises UnicodeEncodeError
    # and the exe exits with code 1 -- exactly the smoke-test failure
    # seen in GitHub Actions. Force UTF-8 output, never crash on print.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="给排水 + 消防 AI 粗稿生成器")
    parser.add_argument("--input", help="建筑输入 JSON（与 --plan 二选一，或用于覆盖底图解析结果）")
    parser.add_argument("--plan", help="建筑底图 DXF 文件（块 / 外部参照会被展开解析）")
    parser.add_argument("--plan-units", default="mm", choices=["mm", "m", "auto"],
                        help="底图单位，默认 mm（院图多为毫米）")
    parser.add_argument("--plan-out", help="把底图解析结果另存为 JSON，供人工检查")
    parser.add_argument("--xref", action="append", default=[],
                        help="外部参照文件映射，可重复：块名=DXF路径")
    parser.add_argument("--out", default="output", help="输出目录")
    parser.add_argument("--ai", action="store_true", help="调用 AI API 做参数建议")
    parser.add_argument("--gui", action="store_true", help="打开图形界面")
    args = parser.parse_args(argv)
    if args.gui:
        from .gui import launch_gui
        launch_gui()
        return 0
    if not args.input and not args.plan:
        parser.error("必须提供 --input 或 --plan 其中之一")

    raw: dict = {}
    if args.plan:
        xref_files = {}
        for item in args.xref:
            if "=" in item:
                name, path = item.split("=", 1)
                xref_files[name.strip()] = path.strip()
        parsed = parse_plan(args.plan, units=args.plan_units, xref_files=xref_files)
        raw.update(parsed)
        if args.plan_out:
            Path(args.plan_out).write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"底图解析: {args.plan_out}")
        if parsed.get("missing_xrefs"):
            print(f"警告：缺失外部参照（未展开）：{parsed['missing_xrefs']}")
        for warning in parsed.get("warnings", []):
            print(f"底图提示：{warning}")
    if args.input:
        raw.update(json.loads(Path(args.input).read_text(encoding="utf-8")))
    params = ai_params(raw) if args.ai else rule_params()
    result = run_build(raw, args.out, params)
    layout = result["layout"]
    checks = result["checks"]
    print(f"DXF: {result['dxf']}")
    print(f"报告: {result['report']}")
    print(f"统计: {layout.summary['counts']}")
    for c in checks:
        print(f"[{c['level']}] {c['system']}: {c['message']}")
    if result["failed"]:
        print("注意：有 FAIL 项，须人工处理后再使用本粗稿。")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
