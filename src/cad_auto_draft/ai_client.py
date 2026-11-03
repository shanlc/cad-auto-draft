"""Optional AI parameter planner (OpenAI-compatible API).

The AI is deliberately NOT asked for geometry. It receives the building
brief and returns only a small JSON object of design parameters. The
caller validates and clamps every field; on any error, missing key or
absent API key the deterministic rule defaults are used instead.

Environment variables:
    CAD_AI_API_KEY   -- API key, never committed, never logged
    CAD_AI_BASE_URL  -- e.g. https://api.openai.com/v1
    CAD_AI_MODEL     -- model name, default: gpt-4o-mini (change to yours)
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

DEFAULT_PARAMS = {
    "riser_strategy": "rule: riser at the core / shaft centre of the floor",
    "hazard_level": None,  # None = keep the building input value
    "danger_level": None,
    "review_notes": [],
}


def rule_params() -> dict[str, Any]:
    return {"source": "rule", **DEFAULT_PARAMS}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ai_params(building: dict[str, Any]) -> dict[str, Any]:
    """Try the AI API once. Any failure -> rule defaults, no exception."""
    key = os.environ.get("CAD_AI_API_KEY", "")
    if not key:
        return rule_params()
    base = os.environ.get("CAD_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("CAD_AI_MODEL", "gpt-4o-mini")
    prompt = (
        "你是给排水、消防粗稿的设计参数助手。只返回 JSON，不要返回坐标、"
        "不要返回绘图指令。字段：riser_x, riser_y, drainage_riser_x, "
        "drainage_riser_y（均为建筑平面内的米制坐标建议）, hazard_level "
        "（light/medium1/medium2）, danger_level（light/medium/serious）, "
        "review_notes（字符串数组，列出本方案最需要人工复核的 3-5 项）。"
        f"建筑简况：{json.dumps(building, ensure_ascii=False)[:2000]}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        data = json.loads(raw)
    except Exception:
        return rule_params()

    width = float(building.get("width", 60.0))
    depth = float(building.get("depth", 20.0))
    out: dict[str, Any] = {"source": "ai"}
    for key_name in ("riser_x", "riser_y", "drainage_riser_x", "drainage_riser_y"):
        try:
            limit = width if key_name.endswith("_x") else depth
            out[key_name] = _clamp(float(data[key_name]), 0.0, limit)
        except Exception:
            pass
    if data.get("hazard_level") in ("light", "medium1", "medium2"):
        out["hazard_level"] = data["hazard_level"]
    if data.get("danger_level") in ("light", "medium", "serious"):
        out["danger_level"] = data["danger_level"]
    notes = data.get("review_notes")
    out["review_notes"] = [str(n) for n in notes][:5] if isinstance(notes, list) else []
    return out


def apply_params(building_dict: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Merge validated AI parameters back into a building dict."""
    merged = dict(building_dict)
    if "riser_x" in params and "riser_y" in params:
        merged["riser"] = {"x": params["riser_x"], "y": params["riser_y"]}
    if "drainage_riser_x" in params and "drainage_riser_y" in params:
        merged["drainage_riser"] = {"x": params["drainage_riser_x"],
                                    "y": params["drainage_riser_y"]}
    if params.get("hazard_level"):
        merged["hazard_level"] = params["hazard_level"]
    if params.get("danger_level"):
        merged["danger_level"] = params["danger_level"]
    return merged
