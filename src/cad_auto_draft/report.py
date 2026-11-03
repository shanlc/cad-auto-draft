"""Markdown self-check report, next to the DXF."""
from __future__ import annotations

import json

from .layout import Layout
from .models import Building
from .standards import REFERENCES


def write_report(b: Building, layout: Layout, checks: list[dict],
                 ai_source: str, path: str) -> str:
    lines = [
        f"# {b.name} AI 粗稿自检报告",
        "",
        "⚠️ **本文件是 AI 粗稿的自检报告，不是计算书、不是合规证明。**",
        "正式出图前必须由注册工程师复核水力计算、规范条文、碰撞与现场条件并签字。",
        "",
        "## 系统统计",
        "",
        f"- 建筑：{b.width} m × {b.depth} m，{b.floors} 层，层高 {b.floor_height} m",
        f"- 类型 / 危险级：{b.building_type} / 喷淋 {b.hazard_level}，灭火器 {b.danger_level}",
        f"- 屋面面积：{b.roof_area} m2，雨水粗算流量：{layout.summary['rain_flow_l_s']} L/s",
        f"- 给水干管初选：DN{layout.summary['water_main_dn']}",
    ]
    for key, value in layout.summary["counts"].items():
        lines.append(f"- {key}：{value}")
    lines.append("")
    lines.append("## 管长统计（平面粗稿，单位 m）")
    for system, length in layout.summary["pipe_length_m"].items():
        lines.append(f"- {system}：{length}")
    lines.append("")
    lines.append("## 自检结果")
    for c in checks:
        lines.append(f"- [{c['level']}] {c['system']}：{c['message']}")
    lines.append("")
    lines.append("## 人工复核清单")
    for item in [
        "立管、管井位置是否与建筑、结构一致，有无梁、剪力墙冲突",
        "给水水压、排水坡度、通气、雨水重现期是否按项目正式计算",
        "消火栓是否满足两股水柱、喷淋危险级与喷头选型是否正确",
        "灭火器种类、数量、保护距离是否按防火分区复核",
        "与暖通、电气、结构的碰撞是否已做 BIM /  CAD 碰撞检查",
        "图层、标注、管材、图例是否已按天正 / 院标准转换为正式图面",
    ]:
        lines.append(f"- [ ] {item}")
    lines.append("")
    lines.append(f"## 参数来源：{ai_source}")
    lines.append("")
    lines.append("## 规范参考（须核对现行版本）")
    for ref in REFERENCES:
        lines.append(f"- {ref}")
    lines.append("")
    lines.append("## 完整统计（JSON）")
    lines.append("```json")
    lines.append(json.dumps(layout.summary, ensure_ascii=False, indent=2))
    lines.append("```")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path
