"""Deterministic layout for all six systems on one standard floor.

No coordinates here come from a language model. The AI layer (see
ai_client.py) may only change Building parameters such as riser
position, hazard_level and danger_level; every point below is computed
from those parameters plus the building input.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .hydraulics import main_water_dn
from .models import Building, Device, Pipe, Point
from .routing import route
from .standards import (DRAINAGE_SLOPE, EXTINGUISHER_TRAVEL, FIXTURES,
                        HYDRANT, RAINWATER, SPRINKLER_SPACING,
                        drainage_dn_for_fixture, rain_flow_l_s)


@dataclass
class Layout:
    pipes: list[Pipe] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def pipes_of(self, system: str) -> list[Pipe]:
        return [p for p in self.pipes if p.system == system]

    def devices_of(self, system: str) -> list[Device]:
        return [d for d in self.devices if d.system == system]


def layout_water(b: Building) -> list[Pipe]:
    main_dn = main_water_dn(b.fixtures, b.building_type)
    pipes: list[Pipe] = []
    for fx in b.fixtures:
        dn = FIXTURES.get(fx.kind, (0.5, 15, 50))[1]
        pts = route(Point(fx.x, fx.y), b.riser, b.obstacles, b.width, b.depth)
        pipes.append(Pipe("WS", pts, dn, f"给水-{fx.id} DN{dn}"))
    if b.fixtures:
        pipes.append(Pipe("WS", [b.water_inlet, b.riser], main_dn,
                          f"给水干管 DN{main_dn}"))
    return pipes


def layout_drainage(b: Building) -> list[Pipe]:
    pipes: list[Pipe] = []
    for fx in b.fixtures:
        dn = drainage_dn_for_fixture(fx.kind)
        pts = route(Point(fx.x, fx.y), b.drainage_riser, b.obstacles,
                    b.width, b.depth)
        pipes.append(Pipe("DR", pts, dn,
                          f"排水-{fx.id} DN{dn} i={DRAINAGE_SLOPE.get(dn, 0.012)}"))
    if b.fixtures:
        pipes.append(Pipe("DR", [b.drainage_riser, b.drainage_outlet], 100,
                          "排水干管 DN100"))
    return pipes


def layout_rainwater(b: Building) -> tuple[list[Pipe], list[Device]]:
    import math as _m
    by_area = _m.ceil(b.roof_area / RAINWATER["area_per_downspout_m2"])
    by_spacing = _m.ceil(b.width / RAINWATER["max_spacing_m"]) + 1
    count = max(2, by_area, by_spacing)
    devices, pipes = [], []
    for i in range(count):
        x = b.width * (i + 0.5) / count
        devices.append(Device("RW", "rainwater_downspout", round(x, 2), b.depth,
                              f"雨水立管{i + 1} DN{RAINWATER['downspout_dn']}",
                              RAINWATER["downspout_dn"]))
        pipes.append(Pipe("RW", [Point(x, b.depth), Point(x, b.depth - 1.0)],
                          RAINWATER["downspout_dn"], f"雨水立管{i + 1}"))
    return pipes, devices


def layout_hydrants(b: Building) -> list[Device]:
    spacing = HYDRANT["spacing_m"]
    count = max(2, math.ceil(b.width / spacing) + 1)
    return [Device("FH", "indoor_hydrant", round(b.width * (i + 0.5) / count, 2),
                   b.corridor_y, f"消火栓{i + 1} DN{HYDRANT['dn']}", HYDRANT["dn"])
            for i in range(count)]


def layout_sprinklers(b: Building) -> list[Device]:
    spacing = SPRINKLER_SPACING.get(b.hazard_level, 3.6)
    devices: list[Device] = []
    y = spacing / 2
    row = 1
    while y < b.depth:
        x = spacing / 2
        col = 1
        while x < b.width:
            if not any(o.x <= x <= o.x_max and o.y <= y <= o.y_max
                       for o in b.obstacles):
                devices.append(Device("SP", "sprinkler", round(x, 2), round(y, 2),
                                      f"喷头{row}-{col}"))
            x += spacing
            col += 1
        y += spacing
        row += 1
    return devices


def layout_extinguishers(b: Building) -> list[Device]:
    travel = EXTINGUISHER_TRAVEL.get(("A", b.danger_level), 20.0)
    devices: list[Device] = []
    # Always at exits / stair doors first.
    for i, e in enumerate(b.exits or [Point(2.0, b.corridor_y),
                                      Point(b.width - 2.0, b.corridor_y)]):
        devices.append(Device("FE", "extinguisher", e.x, e.y, f"灭火器-出口{i + 1}"))
    # Then fill along the corridor so no corridor point is further
    # than one travel distance (conservative) from a point.
    x = travel
    while x < b.width - 1:
        if min(abs(x - d.x) for d in devices) >= travel * 0.8:
            devices.append(Device("FE", "extinguisher", round(x, 2), b.corridor_y,
                                  f"灭火器-{len(devices) + 1}"))
        x += travel
    if len(devices) < 2:
        devices.append(Device("FE", "extinguisher", b.width / 2, b.corridor_y,
                              "灭火器-补"))
    devices.sort(key=lambda d: d.x)
    for i, d in enumerate(devices, 1):
        d.label = f"灭火器{i}"
    return devices


def build_layout(b: Building) -> Layout:
    rw_pipes, rw_devices = layout_rainwater(b)
    pipes = layout_water(b) + layout_drainage(b) + rw_pipes
    devices = (rw_devices + layout_hydrants(b) + layout_sprinklers(b)
               + layout_extinguishers(b))
    summary = {
        "building": b.name,
        "floors": b.floors,
        "roof_area_m2": b.roof_area,
        "rain_flow_l_s": rain_flow_l_s(b.rainfall_intensity_mm_h, b.roof_area),
        "water_main_dn": main_water_dn(b.fixtures, b.building_type),
        "counts": {
            "fixtures": len(b.fixtures),
            "water_pipes": len(layout_water(b)),
            "drainage_pipes": len(layout_drainage(b)),
            "rainwater_downspouts": len(rw_devices),
            "hydrants": len([d for d in devices if d.system == "FH"]),
            "sprinklers": len([d for d in devices if d.system == "SP"]),
            "extinguishers": len([d for d in devices if d.system == "FE"]),
        },
        "pipe_length_m": {
            s: round(sum(p.length for p in pipes if p.system == s), 1)
            for s in ("WS", "DR", "RW")
        },
    }
    return Layout(pipes=pipes, devices=devices, summary=summary)
