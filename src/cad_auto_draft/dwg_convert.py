"""DWG -> DXF conversion, xref auto-discovery and binding helpers.

Why this module exists:
    CAD drawings are DWG by default, and ezdxf cannot read DWG at all.
    The old behaviour was to reject DWG and tell the user to convert
    it by hand. That is the opposite of what Walter wants, so this
    module tries to convert for him, in this order:

    1. ODA File Converter (free, from the Open Design Alliance).
       Command line, from the ODA docs / public examples:
           ODAFileConverter "input_folder" "output_folder" ACAD2018 DXF 0 1
       i.e. input directory, output directory, output version,
       output format (DXF), recurse (0/1), audit (0/1). It works on
       folders, not single files, so a single DWG is copied to a
       temporary input folder first. This is the recommended route:
       it handles modern DWG versions and is the tool ezdxf itself
       wraps in ezdxf.addons.odafc.
    2. LibreDWG: dwgread -O DXF -o output.dxf input.dwg
       (dwg2dxf is the same idea). Free, but DWG version coverage
       and Tianzheng custom objects are weaker than ODA.
    3. AutoCAD itself, if it is installed on this Windows machine:
       accoreconsole.exe (AutoCAD's console) with a script that
       binds xrefs (-XREF Bind, which converts a DWG reference into
       a block, making it a permanent part of the drawing) and then
       DXFOUTs. This is the only route that reliably expands
       Tianzheng custom objects, because Tianzheng runs inside
       AutoCAD; ODA/LibreDWG see Tianzheng objects as proxies.

    If none of those tools is available, conversion fails with a
    clear, actionable error (install ODA, or DXFOUT in AutoCAD),
    never silently. The error message, not a guess, is the contract.

Xref / base-plan discovery:
    A host drawing usually does NOT contain the base plan as
    geometry: it contains an empty block whose name is the xref.
    The parser can only expand it if it can find the xref file.
    This module searches, in order: explicit --xref mappings,
    an explicit --base-plan file, the host file's folder, and any
    user-supplied --xref-dir folders (recursively). A DWG xref
    found this way is itself converted to DXF first, so a whole
    DWG project (host DWG + xref DWGs) can be parsed without the
    user converting each file by hand.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ODA_DOWNLOAD = "https://www.opendesign.com/guestfiles/oda_file_converter"


class DwgConversionError(ValueError):
    """DWG could not be converted because no converter was found."""


def _oda_candidates() -> list[Path]:
    found: list[Path] = []
    for exe in ("ODAFileConverter", "ODAFileConverter.exe"):
        which = shutil.which(exe)
        if which:
            found.append(Path(which))
    if sys.platform.startswith("win"):
        program_files = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                         os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        for base in program_files:
            for rel in (
                r"ODA\ODAFileConverter\ODAFileConverter.exe",
                r"ODA File Converter\ODAFileConverter.exe",
            ):
                p = Path(base) / rel
                if p.is_file():
                    found.append(p)
    env = os.environ.get("ODAFC_PATH") or os.environ.get("CAD_ODAF C_PATH")
    if env and Path(env).is_file():
        found.append(Path(env))
    # Deduplicate, preserving order.
    seen: set[str] = set()
    out: list[Path] = []
    for p in found:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def find_converter() -> tuple[str, str] | None:
    """Return (tool_name, executable_path) for the first usable tool."""
    oda = _oda_candidates()
    if oda:
        return ("oda", str(oda[0]))
    for exe in ("dwgread", "dwg2dxf"):
        which = shutil.which(exe)
        if which:
            return ("libredwg", which)
    if sys.platform.startswith("win"):
        accore = _find_accoreconsole()
        if accore:
            return ("autocad", accore)
    return None


def _find_accoreconsole() -> str | None:
    which = shutil.which("accoreconsole.exe")
    if which:
        return which
    if not sys.platform.startswith("win"):
        return None
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        root = Path(base) / "Autodesk"
        if not root.is_dir():
            continue
        for p in root.rglob("accoreconsole.exe"):
            return str(p)
    return None


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, errors="replace")


def _convert_with_oda(dwg: Path, dxf_out: Path, oda_exe: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="cad_oda_") as tmp:
        in_dir = Path(tmp) / "in"
        out_dir = Path(tmp) / "out"
        in_dir.mkdir()
        out_dir.mkdir()
        shutil.copyfile(dwg, in_dir / dwg.name)
        # ACAD2010 matches the R2010 DXF this project writes/reads.
        result = _run([oda_exe, str(in_dir), str(out_dir), "ACAD2010", "DXF", "0", "1"])
        candidate = out_dir / (dwg.stem + ".dxf")
        if candidate.is_file():
            dxf_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, dxf_out)
            return True
        # ODA may keep the original case / name; take any single DXF.
        dxfs = list(out_dir.glob("*.dxf"))
        if len(dxfs) == 1:
            dxf_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dxfs[0], dxf_out)
            return True
        return False


def _convert_with_dwgread(dwg: Path, dxf_out: Path, exe: str) -> bool:
    if Path(exe).name.lower().startswith("dwgread"):
        result = _run([exe, "-O", "DXF", "-o", str(dxf_out), str(dwg)])
        return dxf_out.is_file() and dxf_out.stat().st_size > 0
    # dwg2dxf: writes a .dxf next to the input or to stdout, depending
    # on build; try both, in a temp copy so we never overwrite the input.
    with tempfile.TemporaryDirectory(prefix="cad_dwg2dxf_") as tmp:
        copy = Path(tmp) / dwg.name
        shutil.copyfile(dwg, copy)
        result = _run([exe, str(copy)], timeout=300)
        candidate = Path(tmp) / (dwg.stem + ".dxf")
        if candidate.is_file():
            dxf_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, dxf_out)
            return True
        if result.stdout and result.stdout.lstrip().startswith("0"):
            dxf_out.parent.mkdir(parents=True, exist_ok=True)
            dxf_out.write_text(result.stdout, encoding="utf-8", errors="replace")
            return True
    return False


def _convert_with_autocad(dwg: Path, dxf_out: Path, accore: str) -> bool:
    """Best-effort AutoCAD console conversion, including xref binding.

    Script: open the DWG, bind all xrefs (-XREF Bind * Bind: the
    first Bind is the -XREF option, * is every reference, the second
    Bind is the bind type as opposed to Insert), then DXFOUT to the
    target, then quit without saving the bound DWG back over the
    original. If AutoCAD rejects any step, the DXFOUT still runs and
    the parser's own binder (binder.py) expands what is left, so a
    partial bind is not a hard failure here.
    """
    with tempfile.TemporaryDirectory(prefix="cad_acad_") as tmp:
        script = Path(tmp) / "convert.scr"
        # AutoCAD script lines: one command per line, blank line = Enter.
        script.write_text(
            f'_OPEN "{dwg}"\n'
            "_-XREF\n_Bind\n*\n_Bind\n"
            f'_DXFOUT "{dxf_out}"\n16\n\n_QUIT\n_N\n',
            encoding="utf-8")
        result = _run([accore, "/i", str(dwg), "/s", str(script)], timeout=600)
        return dxf_out.is_file() and dxf_out.stat().st_size > 0


def convert_dwg_to_dxf(dwg_path: str | Path, dxf_out: str | Path,
                       tool: str | None = None) -> str:
    """Convert one DWG to DXF, trying ODA, then LibreDWG, then AutoCAD.

    Returns the DXF path. Raises DwgConversionError with install
    instructions if no converter is available or all of them fail.
    """
    dwg = Path(dwg_path)
    dxf = Path(dxf_out)
    if not dwg.is_file():
        raise DwgConversionError(f"DWG 文件不存在：{dwg}")
    tried: list[str] = []
    converters = find_converter()
    # Try the detected tool first, then the other families in order,
    # so a broken ODA install does not block a working dwgread.
    order: list[tuple[str, str]] = []
    if converters:
        order.append(converters)
    for exe in _oda_candidates():
        if ("oda", str(exe)) not in order:
            order.append(("oda", str(exe)))
    for exe_name in ("dwgread", "dwg2dxf"):
        which = shutil.which(exe_name)
        if which and ("libredwg", which) not in order:
            order.append(("libredwg", which))
    accore = _find_accoreconsole() if sys.platform.startswith("win") else None
    if accore and ("autocad", accore) not in order:
        order.append(("autocad", accore))
    for name, exe in order:
        if tool and name != tool:
            continue
        tried.append(name)
        try:
            if name == "oda":
                if _convert_with_oda(dwg, dxf, exe):
                    return str(dxf)
            elif name == "libredwg":
                if _convert_with_dwgread(dwg, dxf, exe):
                    return str(dxf)
            elif name == "autocad":
                if _convert_with_autocad(dwg, dxf, exe):
                    return str(dxf)
        except Exception:
            continue
    raise DwgConversionError(
        "无法转换 DWG：本机没有可用的转换工具"
        + (f"（已尝试：{', '.join(tried) or '无'}）" if tried else "。")
        + "\n请任选其一后重试：\n"
        "  1. 安装免费的 ODA File Converter（推荐，能处理现代 DWG 版本）：\n"
        f"     {ODA_DOWNLOAD}\n"
        "     装好后把 ODAFileConverter.exe 所在目录加到 PATH，或直接放在程序同目录。\n"
        "  2. 在已装 AutoCAD / 天正的电脑上，用 DXFOUT 把 DWG 另存为 DXF 再导入。\n"
        "     天正自定义对象只能走这条路：ODA / LibreDWG 看到的天正对象是代理对象，\n"
        "     墙、门窗等可能不完整，须在天正里先分解 / 转成普通图元再转 DXF。\n"
        "  3. 安装 LibreDWG（dwgread），再重试。\n"
        "原 DWG 文件没有被修改，转换只写出一个新的 DXF 文件。")


# -- xref discovery -----------------------------------------------------

def _score_candidate(block_name: str, candidate: Path) -> int | None:
    name = block_name.lower().strip()
    stem = candidate.stem.lower().strip()
    if stem == name:
        return 0
    if name and name in stem:
        return 1
    if stem and stem in name:
        return 2
    # Common institute suffixes: 建筑底图-1F, 平面_标准层, etc.
    if name and stem and (name.split("-")[0] == stem.split("-")[0]):
        return 3
    return None


def find_xref_candidates(block_name: str, search_dirs: list[str | Path]) -> list[Path]:
    """Find files that could be the xref for block_name, best first.

    Searches each directory recursively (skipping hidden folders),
    for .dxf and .dwg files, scored by exact stem match first.
    """
    results: list[tuple[int, int, Path]] = []
    for base in search_dirs:
        root = Path(base)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".dxf", ".dwg"):
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            score = _score_candidate(block_name, path)
            if score is not None:
                # Prefer files closer to the search root, then shorter names.
                depth = len(path.relative_to(root).parts)
                results.append((score, depth, path))
    results.sort(key=lambda item: (item[0], item[1], str(item[2]).lower()))
    seen: set[str] = set()
    out: list[Path] = []
    for _, _, path in results:
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def empty_block_names(dxf_path: str | Path) -> list[str]:
    """Block names in a DXF that have no geometry (typical xrefs)."""
    import ezdxf
    doc = ezdxf.readfile(str(dxf_path))
    names: list[str] = []
    for block in doc.blocks:
        if block.name.startswith("*"):
            continue
        try:
            count = len(list(block))
        except Exception:
            count = 0
        if count == 0:
            names.append(block.name)
    # Also: INSERTs whose block is not defined at all.
    defined = {b.name for b in doc.blocks}
    for ent in doc.modelspace():
        if ent.dxftype() == "INSERT" and str(ent.dxf.name) not in defined:
            if str(ent.dxf.name) not in names:
                names.append(str(ent.dxf.name))
    return names


def resolve_xrefs(host_dxf: str | Path,
                  explicit_xref_files: dict[str, str] | None = None,
                  xref_dirs: list[str | Path] | None = None,
                  base_plan: str | Path | None = None,
                  work_dir: str | Path | None = None) -> dict[str, Any]:
    """Resolve every empty/xref block in host_dxf to a DXF file.

    Returns {"xref_files": {block: dxf_path}, "missing": [blocks],
    "converted": [dxf_paths created from DWG], "warnings": [...]}.
    DWG candidates are converted to DXF in work_dir (or a temp dir
    under the host folder) so parse_plan() only ever sees DXF.
    """
    host = Path(host_dxf)
    explicit = dict(explicit_xref_files or {})
    search_dirs: list[Path] = []
    for d in [host.parent] + list(xref_dirs or []):
        p = Path(d)
        if p.is_dir() and p not in search_dirs:
            search_dirs.append(p)
    work = Path(work_dir) if work_dir else host.parent / "_converted"
    work.mkdir(parents=True, exist_ok=True)

    xref_files: dict[str, str] = {}
    missing: list[str] = []
    converted: list[str] = []
    warnings: list[str] = []
    base_path = Path(base_plan) if base_plan else None
    if base_path and not base_path.is_file():
        warnings.append(f"指定的建筑底图文件不存在，已忽略：{base_path}")
        base_path = None

    for name in empty_block_names(host):
        # 1. Explicit mapping wins.
        if name in explicit:
            candidate = Path(explicit[name])
            if candidate.is_file():
                xref_files[name] = _ensure_dxf(candidate, work, converted, warnings)
                continue
            warnings.append(f"指定的参照文件不存在：{name} = {candidate}")
        # 2. Base-plan file whose stem matches the block name.
        if base_path and _score_candidate(name, base_path) is not None:
            xref_files[name] = _ensure_dxf(base_path, work, converted, warnings)
            continue
        # 3. Auto-search in host folder + xref dirs.
        candidates = find_xref_candidates(name, search_dirs)
        # Never pick the host file itself as its own xref.
        candidates = [c for c in candidates if c.resolve() != host.resolve()]
        if candidates:
            xref_files[name] = _ensure_dxf(candidates[0], work, converted, warnings)
            if len(candidates) > 1:
                warnings.append(f"参照 {name} 找到多个候选，已用第一个：{candidates[0]}")
            continue
        # 4. Explicit base plan as a last-resort fallback: the user
        # said "this file IS the base plan", even if its name does
        # not match the xref block name. Only use it once, for the
        # first still-missing block, and say so in the log.
        if base_path and name not in xref_files.values():
            xref_files[name] = _ensure_dxf(base_path, work, converted, warnings)
            warnings.append(f"参照 {name} 未找到同名文件，已用指定的建筑底图作兜底：{base_path}")
            continue
        missing.append(name)
    return {"xref_files": xref_files, "missing": missing,
            "converted": converted, "warnings": warnings}


def _ensure_dxf(candidate: Path, work: Path, converted: list[str],
                warnings: list[str]) -> str:
    if candidate.suffix.lower() == ".dxf":
        return str(candidate)
    # DWG xref -> convert to DXF in the work dir, named after the file.
    out = work / (candidate.stem + ".dxf")
    if not out.is_file():
        convert_dwg_to_dxf(candidate, out)
        converted.append(str(out))
    return str(out)


def load_plan_with_xrefs(input_path: str | Path, units: str = "mm",
                         xref_files: dict[str, str] | None = None,
                         xref_dirs: list[str | Path] | None = None,
                         base_plan: str | Path | None = None,
                         work_dir: str | Path | None = None,
                         bind_out: str | Path | None = None) -> dict[str, Any]:
    """Full pipeline: DWG->DXF, xref auto-discovery, parse, optional bind.

    Returns {"parsed": <parse_plan dict>, "dxf_path": ..., "xref_files": ...,
    "missing": [...], "converted": [...], "warnings": [...],
    "bind_path": <str|None>, "bind_stats": <dict|None>}.
    If base_plan is given and the host parse yields no rooms, the base
    plan is parsed on its own and its rooms/fixtures/obstacles are
    merged in (the host's own values, if any, win). This covers the
    case where the user hands over a plumbing drawing that does not
    reference the base plan at all, plus the base plan separately.
    """
    from .binder import bind_dxf
    from .plan_parser import parse_plan

    prepared = prepare_plan_input(input_path, xref_files, xref_dirs,
                                  base_plan, work_dir)
    parsed = parse_plan(prepared["dxf_path"], units=units,
                        xref_files=prepared["xref_files"])
    warnings = list(prepared["warnings"])
    warnings.extend(parsed.get("warnings", []))
    # Merge a standalone base plan when the host gave us nothing.
    if base_plan and not parsed.get("rooms"):
        base_path = Path(base_plan)
        if base_path.is_file():
            try:
                base_prepared = prepare_plan_input(
                    base_path, xref_files, xref_dirs, None,
                    Path(work_dir) if work_dir else None)
                base_parsed = parse_plan(base_prepared["dxf_path"], units=units,
                                         xref_files=base_prepared["xref_files"])
                for key in ("rooms", "fixtures", "obstacles", "exits"):
                    if not parsed.get(key) and base_parsed.get(key):
                        parsed[key] = base_parsed[key]
                if not parsed.get("width") and base_parsed.get("width"):
                    parsed["width"] = base_parsed["width"]
                    parsed["depth"] = base_parsed["depth"]
                warnings.append(f"主图未识别到房间，已并入指定的建筑底图：{base_path}")
            except Exception as exc:
                warnings.append(f"指定的建筑底图解析失败，已忽略：{exc}")
    bind_path = None
    bind_stats = None
    if bind_out:
        bind_path = str(bind_out)
        bind_stats = bind_dxf(prepared["dxf_path"], prepared["xref_files"], bind_path)
        if bind_stats["missing_xrefs"]:
            warnings.append(f"绑定后仍缺参照：{bind_stats['missing_xrefs']}")
        if bind_stats["skipped"]:
            warnings.append(f"绑定时跳过 {bind_stats['skipped']} 个不支持的图元（标注/填充/三维等）")
    return {"parsed": parsed, "dxf_path": prepared["dxf_path"],
            "xref_files": prepared["xref_files"], "missing": prepared["missing"],
            "converted": prepared["converted"], "warnings": warnings,
            "bind_path": bind_path, "bind_stats": bind_stats}


def prepare_plan_input(input_path: str | Path,
                       xref_files: dict[str, str] | None = None,
                       xref_dirs: list[str | Path] | None = None,
                       base_plan: str | Path | None = None,
                       work_dir: str | Path | None = None) -> dict[str, Any]:
    """Turn a DWG or DXF input into (dxf_path, xref_files, info).

    If the input is DWG it is converted first; its xrefs are then
    resolved (see resolve_xrefs). The original files are never
    modified; converted DXFs go to work_dir (default: a _converted
    folder next to the input, so the user can inspect them).
    """
    src = Path(input_path)
    if not src.is_file():
        raise ValueError(f"输入文件不存在：{src}")
    work = Path(work_dir) if work_dir else src.parent / "_converted"
    work.mkdir(parents=True, exist_ok=True)
    converted: list[str] = []
    warnings: list[str] = []
    if src.suffix.lower() == ".dwg":
        dxf_path = work / (src.stem + ".dxf")
        convert_dwg_to_dxf(src, dxf_path)
        converted.append(str(dxf_path))
        warnings.append(f"DWG 已自动转成 DXF：{dxf_path}")
    elif src.suffix.lower() == ".dxf":
        dxf_path = src
    else:
        raise ValueError(f"只支持 DWG / DXF 文件，当前文件：{src.suffix}")
    resolved = resolve_xrefs(dxf_path, xref_files, xref_dirs, base_plan, work)
    warnings.extend(resolved["warnings"])
    converted.extend(resolved["converted"])
    return {"dxf_path": str(dxf_path), "xref_files": resolved["xref_files"],
            "missing": resolved["missing"], "converted": converted,
            "warnings": warnings}
