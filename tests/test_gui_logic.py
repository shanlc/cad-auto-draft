"""GUI-adjacent logic that must pass in CI without a display.

The full window is tested manually under xvfb (see the GUI section in
README); this file only covers the parts that decide whether the GUI
opens and what it feeds into the shared build, so the Actions
Windows run does not need a display to run the test suite.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cad_auto_draft.gui import EXAMPLE_BUILDING, _code  # noqa: E402
from main import should_launch_gui  # noqa: E402


class TestGuiLogic(unittest.TestCase):
    def test_double_click_opens_gui(self):
        self.assertTrue(should_launch_gui([]))
        self.assertTrue(should_launch_gui(["--gui"]))
        self.assertFalse(should_launch_gui(["--input", "x.json"]))
        self.assertFalse(should_launch_gui(["--plan", "x.dxf"]))

    def test_example_matches_hotel_floor_json(self):
        import json
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "examples" / "hotel_floor.json").read_text(encoding="utf-8"))
        self.assertEqual(EXAMPLE_BUILDING, data)

    def test_code_strips_chinese_label(self):
        self.assertEqual(_code("hotel（酒店）"), "hotel")
        self.assertEqual(_code(""), "")


if __name__ == "__main__":
    unittest.main()
