"""Core data models.

Design principle (important for safety):
    The AI layer may only propose *parameters* (riser position, hazard
    level, strategy notes). All geometry, pipe sizes and counts are
    produced by deterministic code in this package, so a hallucinated
    coordinate can never silently become a pipe in the drawing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Point:
    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Rect:
    """Axis-aligned obstacle / room, in metres, origin at floor corner."""
    x: float
    y: float
    w: float
    d: float
    name: str = ""

    @property
    def x_max(self) -> float:
        return self.x + self.w

    @property
    def y_max(self) -> float:
        return self.y + self.d


@dataclass
class Fixture:
    id: str
    kind: str  # washbasin | toilet | shower | kitchen_sink | washing_machine | floor_drain
    x: float
    y: float
    room: str = ""


@dataclass
class Pipe:
    system: str  # WS | DR | RW | FH | SP
    points: list[Point]
    dn: int
    label: str = ""

    @property
    def length(self) -> float:
        total = 0.0
        for a, b in zip(self.points, self.points[1:]):
            total += abs(a.x - b.x) + abs(a.y - b.y)
        return round(total, 2)


@dataclass
class Device:
    system: str  # FH | SP | FE | RW
    kind: str
    x: float
    y: float
    label: str = ""
    dn: int = 0


@dataclass
class Building:
    name: str = "标准层"
    width: float = 60.0
    depth: float = 20.0
    floors: int = 1
    floor_height: float = 3.0
    building_type: str = "residential"  # residential | hotel | office | school
    hazard_level: str = "light"  # light | medium1 | medium2
    danger_level: str = "medium"  # light | medium | serious, for extinguishers
    water_inlet: Point = field(default_factory=lambda: Point(0.0, 0.0))
    drainage_outlet: Point = field(default_factory=lambda: Point(0.0, 0.0))
    riser: Point = field(default_factory=lambda: Point(30.0, 10.0))
    drainage_riser: Point = field(default_factory=lambda: Point(30.0, 10.0))
    corridor_y: float = 10.0
    rainfall_intensity_mm_h: float = 180.0
    rooms: list[Rect] = field(default_factory=list)
    obstacles: list[Rect] = field(default_factory=list)
    fixtures: list[Fixture] = field(default_factory=list)
    exits: list[Point] = field(default_factory=list)

    @property
    def roof_area(self) -> float:
        return round(self.width * self.depth, 1)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Building":
        def pt(v: Any, default: Point) -> Point:
            if isinstance(v, dict):
                return Point(float(v.get("x", default.x)), float(v.get("y", default.y)))
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                return Point(float(v[0]), float(v[1]))
            return default

        return cls(
            name=str(data.get("name", "标准层")),
            width=float(data.get("width", 60.0)),
            depth=float(data.get("depth", 20.0)),
            floors=int(data.get("floors", 1)),
            floor_height=float(data.get("floor_height", 3.0)),
            building_type=str(data.get("building_type", "residential")),
            hazard_level=str(data.get("hazard_level", "light")),
            danger_level=str(data.get("danger_level", "medium")),
            water_inlet=pt(data.get("water_inlet"), Point(0.0, 0.0)),
            drainage_outlet=pt(data.get("drainage_outlet"), Point(0.0, 0.0)),
            riser=pt(data.get("riser"), Point(30.0, 10.0)),
            drainage_riser=pt(data.get("drainage_riser"), Point(30.0, 10.0)),
            corridor_y=float(data.get("corridor_y", 10.0)),
            rainfall_intensity_mm_h=float(data.get("rainfall_intensity_mm_h", 180.0)),
            rooms=[Rect(float(r["x"]), float(r["y"]), float(r["w"]), float(r["d"]),
                        str(r.get("name", ""))) for r in data.get("rooms", [])],
            obstacles=[Rect(float(r["x"]), float(r["y"]), float(r["w"]), float(r["d"]),
                           str(r.get("name", ""))) for r in data.get("obstacles", [])],
            fixtures=[Fixture(str(f["id"]), str(f["kind"]), float(f["x"]), float(f["y"]),
                              str(f.get("room", ""))) for f in data.get("fixtures", [])],
            exits=[pt(e, Point(0.0, 10.0)) for e in data.get("exits", [])],
        )
