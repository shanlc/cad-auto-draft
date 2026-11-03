import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ezdxf

from cad_auto_draft.plan_parser import parse_plan


def make_dxf(path: Path) -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # Room: closed polyline + text inside.
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 8), (0, 8)], close=True)
    msp.add_text("卫生间").set_placement((1, 7))
    # Fixture block.
    toilet = doc.blocks.new(name="马桶")
    toilet.add_circle((0, 0), 0.3)
    msp.add_blockref("马桶", (2, 2))
    # Nested block: outer contains an inner toilet insert at (1, 1).
    outer = doc.blocks.new(name="户型块")
    outer.add_blockref("马桶", (1, 1))
    msp.add_blockref("户型块", (4, 4))
    # Obstacle block.
    shaft = doc.blocks.new(name="管井")
    shaft.add_lwpolyline([(0, 0), (2, 0), (2, 1), (0, 1)], close=True)
    msp.add_blockref("管井", (8, 6))
    # Empty block = external reference with no file supplied.
    doc.blocks.new(name="建筑底图参照")
    msp.add_blockref("建筑底图参照", (0, 0))
    doc.saveas(str(path))


class TestPlanParser(unittest.TestCase):
    def test_blocks_nested_and_xref(self):
        with tempfile.TemporaryDirectory() as tmp:
            dxf = Path(tmp) / "plan.dxf"
            make_dxf(dxf)
            result = parse_plan(str(dxf), units="m")
        self.assertEqual(result["width"], 10)
        self.assertEqual(result["depth"], 8)
        self.assertTrue(any(r["name"] == "卫生间" for r in result["rooms"]))
        kinds = [f["kind"] for f in result["fixtures"]]
        self.assertIn("toilet", kinds)
        # Direct toilet at (2,2) and nested toilet at (4+1, 4+1) = (5,5).
        points = {(f["x"], f["y"]) for f in result["fixtures"]}
        self.assertIn((2.0, 2.0), points)
        self.assertIn((5.0, 5.0), points)
        self.assertTrue(result["obstacles"])
        self.assertIn("建筑底图参照", result["missing_xrefs"])

    def test_dwg_rejected_with_help(self):
        with self.assertRaises(ValueError) as ctx:
            parse_plan("plan.dwg")
        self.assertIn("DXF", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
