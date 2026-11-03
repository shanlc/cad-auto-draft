"""Simplified hydraulic sizing for a draft.

These formulas are the GB 50015 style ones used for a first sizing
pass. They do NOT replace a formal hydraulic calculation, pressure
check, or water-supply / drainage calculation book.
"""
from __future__ import annotations

import math

from .standards import ALPHA, FIXTURES, water_dn_for_flow


def design_second_flow_l_s(fixtures: list, building_type: str) -> float:
    """qg = 0.2 * alpha * sqrt(Ng), Ng = sum of fixture equivalents."""
    ng = sum(FIXTURES.get(f.kind, (0.5, 15, 50))[0] for f in fixtures)
    alpha = ALPHA.get(building_type, 2.5)
    return round(0.2 * alpha * math.sqrt(ng), 3) if ng else 0.0


def main_water_dn(fixtures: list, building_type: str) -> int:
    return water_dn_for_flow(design_second_flow_l_s(fixtures, building_type))
