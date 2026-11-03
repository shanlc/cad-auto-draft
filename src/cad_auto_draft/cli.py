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
from .report import write_report
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="给排水 + 消防 AI 粗稿生成器")
    parser.add_argument("--input", required=True, help="建筑输入 JSON")
    parser.add_argument("--out", default="output", help="输出目录")
    parser.add_argument("--ai", action="store_true", help="调用 AI API 做参数建议")
    args = parser.parse_args(argv)

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    params = ai_params(raw) if args.ai else rule_params()
    building = Building.from_dict(apply_params(raw, params))

    layout = build_layout(building)
    checks = validate(building, layout)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dxf = write_dxf(building, layout, str(out / "draft.dxf"))
    report = write_report(building, layout, checks, params.get("source", "rule"),
                          str(out / "report.md"))
    (out / "summary.json").write_text(
        json.dumps({"summary": layout.summary, "checks": checks,
                    "ai_params_source": params.get("source", "rule")},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [c for c in checks if c["level"] == "FAIL"]
    print(f"DXF: {dxf}")
    print(f"报告: {report}")
    print(f"统计: {layout.summary['counts']}")
    for c in checks:
        print(f"[{c['level']}] {c['system']}: {c['message']}")
    if failed:
        print("注意：有 FAIL 项，须人工处理后再使用本粗稿。")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
