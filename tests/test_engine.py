import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cad_auto_draft.layout import build_layout
from cad_auto_draft.models import Building
from cad_auto_draft.routing import route
from cad_auto_draft.validate import validate
from cad_auto_draft.models import Point


def sample() -> Building:
    return Building.from_dict({
        "name": "test", "width": 40, "depth": 20, "floors": 5,
        "riser": {"x": 20, "y": 10}, "drainage_riser": {"x": 20, "y": 10},
        "fixtures": [
            {"id": "T1", "kind": "toilet", "x": 18, "y": 14},
            {"id": "W1", "kind": "washbasin", "x": 22, "y": 14},
        ],
        "exits": [{"x": 2, "y": 10}, {"x": 38, "y": 10}],
    })


class TestEngine(unittest.TestCase):
    def test_routing_is_orthogonal(self):
        pts = route(Point(1, 1), Point(5, 4), [], 40, 20)
        self.assertEqual(pts[0].as_tuple(), (1, 1))
        self.assertEqual(pts[-1].as_tuple(), (5, 4))
        for a, b in zip(pts, pts[1:]):
            self.assertTrue(a.x == b.x or a.y == b.y)

    def test_all_systems_present(self):
        layout = build_layout(sample())
        self.assertTrue(layout.pipes_of("WS"))
        self.assertTrue(layout.pipes_of("DR"))
        self.assertTrue(layout.devices_of("RW"))
        self.assertTrue(layout.devices_of("FH"))
        self.assertTrue(layout.devices_of("SP"))
        self.assertTrue(layout.devices_of("FE"))

    def test_no_fail_on_sample(self):
        layout = build_layout(sample())
        failed = [c for c in validate(sample(), layout) if c["level"] == "FAIL"]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
