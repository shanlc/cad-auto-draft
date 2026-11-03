"""Graphical interface for cad-auto-draft (tkinter, stdlib only).

Why this exists: double-clicking the exe used to print a command-line
error ("must provide --input or --plan") and exit. Walter prefers
toolbar / UI clicks over remembering command-line commands, so the
exe now opens this window when it is double-clicked (no arguments)
or run with --gui, and the command line still works unchanged.

The GUI does no drawing logic itself: it collects inputs, then calls
the same cli.run_build() the command line uses, in a worker thread so
the window never freezes. All geometry, pipe sizes and checks are
therefore identical to the CLI output.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from copy import deepcopy
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception as exc:  # pragma: no cover - tkinter missing on some builds
    raise RuntimeError(
        "图形界面需要 tkinter（Windows 自带 Python 已包含）。"
        "如果是在精简 Python 环境下，请改用命令行模式。"
    ) from exc

from .ai_client import ai_params, rule_params
from .cli import run_build
from .plan_parser import parse_plan

# Built-in example, identical to examples/hotel_floor.json, embedded so
# the frozen exe works even though examples/ is not bundled with it.
EXAMPLE_BUILDING: dict = {
    "building_type": "hotel", "corridor_y": 10, "danger_level": "medium",
    "depth": 20, "drainage_outlet": {"x": 60, "y": 0},
    "drainage_riser": {"x": 30, "y": 10},
    "exits": [{"x": 2, "y": 10}, {"x": 58, "y": 10}],
    "fixtures": [
        {"id": "F1-洗脸盆", "kind": "washbasin", "room": "卫生间", "x": 29, "y": 14},
        {"id": "F1-马桶", "kind": "toilet", "room": "卫生间", "x": 31, "y": 14},
        {"id": "F1-淋浴", "kind": "shower", "room": "卫生间", "x": 29, "y": 16},
        {"id": "K1-洗菜盆", "kind": "kitchen_sink", "room": "客房1", "x": 8, "y": 14},
        {"id": "W1-洗衣机", "kind": "washing_machine", "room": "客房4", "x": 52, "y": 14},
    ],
    "floor_height": 3.3, "floors": 10, "hazard_level": "light",
    "name": "酒店标准层示例",
    "obstacles": [
        {"d": 2, "name": "管井", "w": 2, "x": 29, "y": 9},
        {"d": 6, "name": "楼梯间", "w": 6, "x": 0, "y": 0},
    ],
    "rainfall_intensity_mm_h": 180, "riser": {"x": 30, "y": 10},
    "rooms": [
        {"d": 8, "name": "客房1", "w": 10, "x": 0, "y": 12},
        {"d": 8, "name": "客房2", "w": 10, "x": 10, "y": 12},
        {"d": 8, "name": "客房3", "w": 10, "x": 40, "y": 12},
        {"d": 8, "name": "客房4", "w": 10, "x": 50, "y": 12},
        {"d": 6, "name": "卫生间", "w": 4, "x": 28, "y": 12},
    ],
    "water_inlet": {"x": 0, "y": 0}, "width": 60,
}

PRIMARY = "#0F4C81"
ACCENT = "#2563EB"
BG = "#EEF2F7"
CARD = "#FFFFFF"
MUTED = "#64748B"


def _code(value: str) -> str:
    """'hotel（酒店）' -> 'hotel'; '' stays ''."""
    return value.split("（")[0].strip() if value else ""


def _open_path(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("给排水 + 消防 AI 自动粗稿")
        self.root.geometry("960x780")
        self.root.minsize(860, 640)
        self.root.configure(bg=BG)
        self.queue: queue.Queue = queue.Queue()
        self.result: dict | None = None
        self._setup_style()
        self._build()
        self.root.after(100, self._poll_queue)

    # -- layout -------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        font = ("Microsoft YaHei", 10)
        style.configure(".", font=font, background=BG)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG)
        style.configure("Card.TLabel", background=CARD)
        style.configure("TLabelframe", background=CARD, padding=12)
        style.configure("TLabelframe.Label", background=CARD, font=("Microsoft YaHei", 11, "bold"))
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=("Microsoft YaHei", 11, "bold"), padding=(16, 8))
        style.configure("TButton", padding=(10, 6))

    def _build(self) -> None:
        header = tk.Frame(self.root, bg=PRIMARY, height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="给排水 + 消防 AI 自动粗稿", bg=PRIMARY, fg="white",
                 font=("Microsoft YaHei", 17, "bold")).pack(anchor="w", padx=18, pady=(12, 0))
        tk.Label(header, text="给水 · 排水 · 雨水 · 消火栓 · 喷淋 · 灭火器  —  点一点就出 DXF 粗稿",
                 bg=PRIMARY, fg="#DCE8F5", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=18)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        # --- Step 1: input ---
        self.mode = tk.StringVar(value="example")
        card1 = ttk.Labelframe(main, text="①  选择输入")
        card1.pack(fill="x", pady=(0, 10))
        for value, label in (("example", "内置示例：酒店标准层（不用准备文件，直接点生成就能试）"),
                             ("json", "建筑输入 JSON 文件"),
                             ("dxf", "建筑底图 DXF 文件（自动识别块 / 外部参照）")):
            ttk.Radiobutton(card1, text=label, variable=self.mode, value=value,
                            command=self._update_mode).pack(anchor="w", pady=2)

        row = ttk.Frame(card1)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="JSON 文件：").pack(side="left")
        self.json_var = tk.StringVar()
        self.json_entry = ttk.Entry(row, textvariable=self.json_var, width=62)
        self.json_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.json_btn = ttk.Button(row, text="浏览…", command=self._browse_json)
        self.json_btn.pack(side="left")

        row = ttk.Frame(card1)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="DXF 文件：").pack(side="left")
        self.dxf_var = tk.StringVar()
        self.dxf_entry = ttk.Entry(row, textvariable=self.dxf_var, width=62)
        self.dxf_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.dxf_btn = ttk.Button(row, text="浏览…", command=self._browse_dxf)
        self.dxf_btn.pack(side="left")
        ttk.Label(row, text="单位：").pack(side="left", padx=(8, 2))
        self.units_var = tk.StringVar(value="mm")
        self.units_combo = ttk.Combobox(row, textvariable=self.units_var,
                                        values=["mm", "m", "auto"], width=7, state="readonly")
        self.units_combo.pack(side="left")

        # --- Step 2: optional overrides ---
        card2 = ttk.Labelframe(main, text="②  参数（留空 = 按输入文件，不覆盖）")
        card2.pack(fill="x", pady=(0, 10))
        self.building_var = tk.StringVar()
        self.hazard_var = tk.StringVar()
        self.danger_var = tk.StringVar()
        self.floors_var = tk.StringVar()
        self.rain_var = tk.StringVar()
        fields = [
            ("建筑类型：", self.building_var, ["residential（住宅）", "hotel（酒店）", "office（办公）", "school（学校）"]),
            ("喷淋危险级：", self.hazard_var, ["light（轻危险级）", "medium1（中危险级 I）", "medium2（中危险级 II）"]),
            ("灭火器危险级：", self.danger_var, ["light（轻危险级）", "medium（中危险级）", "serious（严重危险级）"]),
        ]
        for label, var, values in fields:
            r = ttk.Frame(card2)
            r.pack(side="left", padx=(0, 14), pady=2)
            ttk.Label(r, text=label).pack(side="left")
            ttk.Combobox(r, textvariable=var, values=values, width=18).pack(side="left")
        r = ttk.Frame(card2)
        r.pack(side="left", padx=(0, 14), pady=2)
        ttk.Label(r, text="层数：").pack(side="left")
        ttk.Entry(r, textvariable=self.floors_var, width=6).pack(side="left")
        r = ttk.Frame(card2)
        r.pack(side="left", pady=2)
        ttk.Label(r, text="降雨强度 mm/h：").pack(side="left")
        ttk.Entry(r, textvariable=self.rain_var, width=8).pack(side="left")

        # --- Step 3: output + run ---
        card3 = ttk.Labelframe(main, text="③  输出与生成")
        card3.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(card3)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="输出文件夹：").pack(side="left")
        self.out_var = tk.StringVar(value=str(Path.cwd() / "output"))
        ttk.Entry(row, textvariable=self.out_var, width=62).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row, text="浏览…", command=self._browse_out).pack(side="left")
        row = ttk.Frame(card3)
        row.pack(fill="x", pady=6)
        self.ai_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="调用 AI API 做参数建议（需设置 CAD_AI_API_KEY，否则自动回落规则）",
                        variable=self.ai_var).pack(side="left")
        ttk.Button(row, text="使用说明", command=self._show_help).pack(side="right")
        row = ttk.Frame(card3)
        row.pack(fill="x", pady=4)
        self.run_btn = ttk.Button(row, text="▶  生成粗稿", style="Accent.TButton",
                                  command=self._on_run)
        self.run_btn.pack(side="left", padx=(0, 8))
        self.open_dir_btn = ttk.Button(row, text="打开输出文件夹", command=self._open_out, state="disabled")
        self.open_dir_btn.pack(side="left", padx=4)
        self.open_report_btn = ttk.Button(row, text="打开自检报告", command=self._open_report, state="disabled")
        self.open_report_btn.pack(side="left", padx=4)
        self.open_dxf_btn = ttk.Button(row, text="打开 DXF 所在文件夹", command=self._open_out, state="disabled")
        self.open_dxf_btn.pack(side="left", padx=4)

        # --- Log ---
        card4 = ttk.Labelframe(main, text="生成日志与自检结果")
        card4.pack(fill="both", expand=True)
        self.log = tk.Text(card4, height=16, wrap="word", font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(card4, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.tag_config("pass", foreground="#15803D")
        self.log.tag_config("warn", foreground="#B45309")
        self.log.tag_config("fail", foreground="#DC2626", font=("Consolas", 10, "bold"))
        self.log.tag_config("info", foreground="#334155")

        self.status_var = tk.StringVar(value="就绪：选好输入后点“生成粗稿”。双击 exe 打开就是这个界面，不用记命令。")
        ttk.Label(self.root, textvariable=self.status_var, foreground=MUTED,
                  wraplength=940).pack(fill="x", padx=12, pady=(0, 8))
        self._update_mode()
        self._log("提示：本程序输出的是 AI 粗稿，仅供工程师复核修改，非正式施工图，不得直接用于施工。", "info")

    # -- helpers ------------------------------------------------------
    def _update_mode(self) -> None:
        mode = self.mode.get()
        self.json_entry.configure(state="normal" if mode == "json" else "disabled")
        self.json_btn.configure(state="normal" if mode == "json" else "disabled")
        self.dxf_entry.configure(state="normal" if mode == "dxf" else "disabled")
        self.dxf_btn.configure(state="normal" if mode == "dxf" else "disabled")
        self.units_combo.configure(state="readonly" if mode == "dxf" else "disabled")

    def _browse_json(self) -> None:
        path = filedialog.askopenfilename(title="选择建筑输入 JSON",
                                          filetypes=[("JSON", "*.json"), ("全部文件", "*.*")])
        if path:
            self.json_var.set(path)

    def _browse_dxf(self) -> None:
        path = filedialog.askopenfilename(title="选择建筑底图 DXF",
                                          filetypes=[("DXF", "*.dxf"), ("全部文件", "*.*")])
        if path:
            self.dxf_var.set(path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.out_var.set(path)

    def _show_help(self) -> None:
        messagebox.showinfo(
            "使用说明",
            "1. 选输入：内置示例可直接试；有自己的图就选 JSON 或 DXF。\n"
            "2. 参数留空就是按输入文件来，想改再选。\n"
            "3. 点“生成粗稿”，等日志里出现自检结果。\n"
            "4. 点“打开输出文件夹”，把 draft.dxf 拿到 AutoCAD / 天正里打开复核，\n"
            "   再转成天正专用管线和正式标注出图。\n"
            "5. DXF 不能直接读 DWG：先在 AutoCAD / 天正用 DXFOUT 转成 DXF。\n"
            "注意：输出是粗稿，不是正式施工图，须经注册工程师复核签字。")

    def _log(self, text: str, tag: str = "info") -> None:
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")

    def _open_out(self) -> None:
        if self.result:
            _open_path(str(Path(self.result["dxf"]).parent))

    def _open_report(self) -> None:
        if self.result:
            _open_path(self.result["report"])

    # -- run ----------------------------------------------------------
    def _collect_raw(self) -> dict:
        mode = self.mode.get()
        if mode == "json":
            path = self.json_var.get().strip()
            if not path:
                raise ValueError("请先选择一个 JSON 输入文件，或改选内置示例。")
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        elif mode == "dxf":
            path = self.dxf_var.get().strip()
            if not path:
                raise ValueError("请先选择一个 DXF 底图文件，或改选内置示例。")
            parsed = parse_plan(path, units=self.units_var.get())
            raw = dict(parsed)
            if parsed.get("missing_xrefs"):
                self.queue.put(("log", f"警告：缺失外部参照（未展开）：{parsed['missing_xrefs']}", "warn"))
            for warning in parsed.get("warnings", []):
                self.queue.put(("log", f"底图提示：{warning}", "warn"))
        else:
            raw = deepcopy(EXAMPLE_BUILDING)
        # Optional overrides, only when the user actually filled them in.
        if _code(self.building_var.get()):
            raw["building_type"] = _code(self.building_var.get())
        if _code(self.hazard_var.get()):
            raw["hazard_level"] = _code(self.hazard_var.get())
        if _code(self.danger_var.get()):
            raw["danger_level"] = _code(self.danger_var.get())
        if self.floors_var.get().strip():
            raw["floors"] = int(self.floors_var.get().strip())
        if self.rain_var.get().strip():
            raw["rainfall_intensity_mm_h"] = float(self.rain_var.get().strip())
        return raw

    def _on_run(self) -> None:
        self.run_btn.configure(state="disabled")
        for btn in (self.open_dir_btn, self.open_report_btn, self.open_dxf_btn):
            btn.configure(state="disabled")
        self.result = None
        self.log.delete("1.0", "end")
        self.status_var.set("正在生成，请稍候…")
        self._log("开始生成…", "info")

        def worker() -> None:
            try:
                raw = self._collect_raw()
                params = ai_params(raw) if self.ai_var.get() else rule_params()
                result = run_build(raw, self.out_var.get().strip() or "output", params)
                self.queue.put(("done", result, None))
            except Exception:
                self.queue.put(("error", None, traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._log(item[1], item[2])
                elif kind == "done":
                    self._finish(item[1])
                elif kind == "error":
                    self._log("生成失败：", "fail")
                    self._log(item[2], "fail")
                    self.status_var.set("生成失败，见日志里的报错。")
                    self.run_btn.configure(state="normal")
                    messagebox.showerror("生成失败", "生成失败，详细报错见日志。")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _finish(self, result: dict) -> None:
        self.result = result
        layout = result["layout"]
        self._log(f"DXF：{result['dxf']}", "info")
        self._log(f"自检报告：{result['report']}", "info")
        self._log(f"统计：{layout.summary['counts']}", "info")
        for check in result["checks"]:
            tag = {"PASS": "pass", "WARN": "warn", "FAIL": "fail"}.get(check["level"], "info")
            self._log(f"[{check['level']}] {check['system']}：{check['message']}", tag)
        for btn in (self.open_dir_btn, self.open_report_btn, self.open_dxf_btn):
            btn.configure(state="normal")
        self.run_btn.configure(state="normal")
        if result["failed"]:
            self.status_var.set("生成完成，但有 FAIL 项，须人工处理后再使用本粗稿。")
            messagebox.showwarning("有 FAIL 项", "生成完成，但有 FAIL 项，须人工处理后再使用本粗稿。")
        else:
            self.status_var.set("生成完成：DXF 和自检报告已在输出文件夹，可点上方按钮打开。")


def launch_gui() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
