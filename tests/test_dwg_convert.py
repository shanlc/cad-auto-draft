"""DWG conversion, xref auto-discovery and binding.

No real DWG or ODA/LibreDWG tool is available in CI, so these tests
cover the parts that must work without one: candidate search,
helpful failure when no converter exists, and the Python binder.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ezdxf  # noqa: E402

from cad_auto_draft.binder import bind_dxf  # noqa: E402
from cad_auto_draft.dwg_convert import (  # noqa: E402
    DwgConversionError, convert_dwg_to_dxf, find_xref_candidates,
    load_plan_with_xrefs)


def make_room_dxf(path: Path, room_name: str = "客房") -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10000, 0), (10000, 8000), (0, 8000)],
                       close=True)
    msp.add_text(room_name, dxfattribs={"height": 500}).set_placement((1000, 1000))
    doc.saveas(str(path))


class TestXrefDiscovery(unittest.TestCase):
    def test_exact_match_wins_over_contains(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "建筑底图-旧.dxf").write_text("x")
            sub = root / "sub"
            sub.mkdir()
            make_room_dxf(sub / "建筑底图.dxf")
            found = find_xref_candidates("建筑底图", [root])
            self.assertEqual(found[0].name, "建筑底图.dxf")

    def test_load_plan_finds_xref_in_subfolder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xref_dir = root / "xref"
            xref_dir.mkdir()
            make_room_dxf(xref_dir / "建筑底图.dxf")
            host = ezdxf.new("R2010")
            # Empty block = xref in the host file.
            host.blocks.new(name="建筑底图")
            host.modelspace().add_blockref("建筑底图", (0, 0))
            host_path = root / "给排水.dxf"
            host.saveas(str(host_path))
            loaded = load_plan_with_xrefs(host_path, units="mm",
                                          work_dir=root / "_converted")
            self.assertEqual(loaded["missing"], [])
            self.assertIn("建筑底图", loaded["xref_files"])
            self.assertEqual(len(loaded["parsed"]["rooms"]), 1)
            self.assertEqual(loaded["parsed"]["rooms"][0]["name"], "客房")

    def test_dwg_without_converter_fails_helpfully(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dwg = root / "test.dwg"
            dwg.write_bytes(b"not a real dwg")
            with self.assertRaises(DwgConversionError) as ctx:
                convert_dwg_to_dxf(dwg, root / "test.dxf")
            msg = str(ctx.exception)
            self.assertIn("ODA", msg)
            self.assertIn("DXFOUT", msg)


class TestBinder(unittest.TestCase):
    def test_nested_block_and_xref_are_expanded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Xref doc: a room outline.
            make_room_dxf(root / "建筑底图.dxf")
            # Host: a nested block (outer contains inner line) + xref insert.
            host = ezdxf.new("R2010")
            inner = host.blocks.new(name="inner")
            inner.add_line((0, 0), (1000, 0))
            outer = host.blocks.new(name="outer")
            outer.add_blockref("inner", (0, 0))
            host.blocks.new(name="建筑底图")
            msp = host.modelspace()
            msp.add_blockref("outer", (0, 0))
            msp.add_blockref("建筑底图", (0, 0))
            host_path = root / "host.dxf"
            host.saveas(str(host_path))
            out = root / "bound.dxf"
            stats = bind_dxf(host_path, {"建筑底图": str(root / "建筑底图.dxf")}, out)
            self.assertEqual(stats["missing_xrefs"], [])
            bound = ezdxf.readfile(str(out))
            types = [e.dxftype() for e in bound.modelspace()]
            # 1 expanded line + 1 room polyline + 1 text = 3 entities.
            self.assertEqual(len(types), 3)
            self.assertIn("LINE", types)
            self.assertIn("LWPOLYLINE", types)


if __name__ == "__main__":
    unittest.main()
