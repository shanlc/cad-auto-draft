"""Normative parameters, kept in one place and overridable by config.

These are *draft defaults*, not a substitute for the code text.
Every value below is intentionally conservative (smaller spacing, larger
or equal pipe size) and must be re-checked by a licensed engineer
against the current edition of the standard, the project hazard
classification and local rules before any formal drawing is issued.

References (China, check for the latest edition / amendment):
    GB 50015  建筑给水排水设计标准          -- 给水、排水、雨水
    GB 50016  建筑设计防火规范              -- 防火分区、消防设施设置原则
    GB 50974  消防给水及消火栓系统技术规范  -- 消火栓系统
    GB 50084  自动喷水灭火系统设计规范      -- 喷淋系统
    GB 50140  建筑灭火器配置设计规范        -- 灭火器配置
    GB 50014  室外排水设计标准              -- 室外排水衔接
"""
from __future__ import annotations

REFERENCES = [
    "GB 50015 建筑给水排水设计标准：给水、排水、雨水系统设计",
    "GB 50016 建筑设计防火规范：消防设施设置的基本原则",
    "GB 50974 消防给水及消火栓系统技术规范：室内消火栓系统",
    "GB 50084 自动喷水灭火系统设计规范：喷头布置与系统设计",
    "GB 50140 建筑灭火器配置设计规范：灭火器配置与最大保护距离",
    "GB 50014 室外排水设计标准：室外排水衔接",
]

# Fixture: (water equivalent, water DN, drainage DN)
FIXTURES = {
    "washbasin": (0.5, 15, 50),
    "toilet": (0.5, 15, 100),
    "shower": (0.75, 15, 50),
    "kitchen_sink": (1.0, 20, 75),
    "washing_machine": (1.0, 20, 50),
    "floor_drain": (0.5, 15, 50),
}

# GB 50015 style design-second-flow coefficient alpha, by building type.
ALPHA = {"residential": 2.5, "hotel": 2.5, "office": 1.5, "school": 2.0}

# Minimum drainage slope, by DN (draft defaults, conservative side).
DRAINAGE_SLOPE = {50: 0.025, 75: 0.015, 100: 0.012, 125: 0.010, 150: 0.007}


def water_dn_for_flow(flow_l_s: float) -> int:
    """Very conservative DN choice from a calculated flow (L/s)."""
    for limit, dn in [(0.3, 20), (0.7, 25), (1.2, 32), (2.0, 40), (3.5, 50),
                      (6.0, 65), (10.0, 80), (16.0, 100)]:
        if flow_l_s <= limit:
            return dn
    return 125


def drainage_dn_for_fixture(kind: str) -> int:
    return FIXTURES.get(kind, (0.5, 15, 50))[2]


# Sprinkler spacing: conservative draft values, below the usual code
# maxima for the corresponding hazard level. Never increase them here
# without a code check.
SPRINKLER_SPACING = {"light": 4.0, "medium1": 3.6, "medium2": 3.4}
SPRINKLER_AREA_PER_HEAD = {"light": 16.0, "medium1": 12.0, "medium2": 10.0}

# Indoor hydrant, GB 50974 draft defaults.
HYDRANT = {
    "dn": 65,
    "hose_length_m": 25.0,
    # Effective coverage radius used for the self-check: hose length
    # discounted, so the check fails before the code limit is reached.
    "effective_radius_m": 20.0,
    "spacing_m": 30.0,
}

# Extinguisher maximum travel distance (m), GB 50140 style, by fire
# class and danger level. A = solid, B = liquid.
EXTINGUISHER_TRAVEL = {
    ("A", "serious"): 15.0, ("A", "medium"): 20.0, ("A", "light"): 25.0,
    ("B", "serious"): 9.0, ("B", "medium"): 12.0, ("B", "light"): 15.0,
}

# Rainwater, GB 50015 style draft defaults.
RAINWATER = {
    "downspout_dn": 100,
    # Conservative service area per DN100 downspout, to be replaced by
    # the project rainfall calculation (Q = q * F) in formal design.
    "area_per_downspout_m2": 200.0,
    "max_spacing_m": 20.0,
}


def rain_flow_l_s(intensity_mm_h: float, area_m2: float) -> float:
    """Q (L/s) = intensity (mm/h) * area (m2) / 3600, unit conversion only."""
    return round(intensity_mm_h * area_m2 / 3600.0, 2)
