"""Self-checks that run before any drawing is handed to a human.

A FAIL does not mean the drawing is wrong in the real world -- it means
the draft does not prove itself, and a human must look at that item.
A PASS is not a code-compliance certificate.
"""
from __future__ import annotations

import math

from .layout import Layout
from .models import Building
from .standards import EXTINGUISHER_TRAVEL, HYDRANT, SPRINKLER_SPACING


def _dist(x: float, y: float, devices) -> float:
    return min((math.hypot(x - d.x, y - d.y) for d in devices), default=9999.0)


def validate(b: Building, layout: Layout) -> list[dict]:
    checks: list[dict] = []

    def add(level: str, system: str, msg: str) -> None:
        checks.append({"level": level, "system": system, "message": msg})

    # 1. Every fixture must have a water and a drainage route.
    ws = {p.label for p in layout.pipes_of("WS")}
    dr = {p.label for p in layout.pipes_of("DR")}
    missing = [f.id for f in b.fixtures
               if f"给水-{f.id}" not in str(ws) or f"排水-{f.id}" not in str(dr)]
    add("PASS" if not missing else "FAIL", "WS/DR",
        f"洁具接管：缺失 {missing}" if missing else
        f"全部 {len(b.fixtures)} 个洁具均有给水、排水支管")

    # 2. Sprinkler coverage, sampled every 2 m, excluding shafts / stairs
    # (obstacles), which are not normally sprinkler-protected floor area.
    sps = layout.devices_of("SP")
    spacing = SPRINKLER_SPACING.get(b.hazard_level, 3.6)
    worst = 0.0
    sx = 1.0
    while sx < b.width:
        sy = 1.0
        while sy < b.depth:
            if not any(o.x <= sx <= o.x_max and o.y <= sy <= o.y_max
                       for o in b.obstacles):
                worst = max(worst, _dist(sx, sy, sps))
            sy += 2.0
        sx += 2.0
    add("PASS" if worst <= spacing * 0.75 else "WARN", "SP",
        f"喷淋抽查最远点距喷头 {worst:.1f} m（限值约 {spacing * 0.75:.1f} m）")

    # 3. Hydrant coverage, sampled every 5 m.
    fhs = layout.devices_of("FH")
    worst = 0.0
    sx = 2.5
    while sx < b.width:
        worst = max(worst, _dist(sx, b.corridor_y, fhs))
        sx += 5.0
    add("PASS" if worst <= HYDRANT["effective_radius_m"] else "WARN", "FH",
        f"消火栓走廊抽查最远点 {worst:.1f} m（有效半径 "
        f"{HYDRANT['effective_radius_m']:.0f} m，软管 {HYDRANT['hose_length_m']:.0f} m）")

    # 4. Extinguisher travel distance, sampled every 5 m.
    fes = layout.devices_of("FE")
    travel = EXTINGUISHER_TRAVEL.get(("A", b.danger_level), 20.0)
    worst = 0.0
    sx = 2.5
    while sx < b.width:
        worst = max(worst, _dist(sx, b.corridor_y, fes))
        sx += 5.0
    add("PASS" if worst <= travel else "WARN", "FE",
        f"灭火器走廊抽查最远点 {worst:.1f} m（A类最大保护距离 {travel:.0f} m）"
        f"，共 {len(fes)} 处（每层、每个防火分区至少 2 处须人工核对）")

    # 5. Rainwater.
    rw = layout.devices_of("RW")
    need = math.ceil(b.roof_area / 200.0)
    add("PASS" if len(rw) >= need else "FAIL", "RW",
        f"雨水立管 {len(rw)} 根，屋面 {b.roof_area} m2 粗算至少 {need} 根")

    # 6. Hydrant / extinguisher minimum counts.
    add("PASS" if len(fhs) >= 2 else "FAIL", "FH", f"消火栓 {len(fhs)} 个")
    add("PASS" if len(fes) >= 2 else "FAIL", "FE", f"灭火器设置点 {len(fes)} 处")
    return checks
