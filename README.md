# 给排水 + 消防 AI 自动粗稿

在 AutoCAD / 天正环境下，用 AI 做参数建议、用确定性程序做
几何与尺寸，自动生成给排水、雨水、消火栓、喷淋、灭火器的
**平面粗稿（DXF）+ 自检报告**，目标是比人工画第一版快，
而不是替代工程师出正式施工图。

## 最优解思路（本项目采用的架构）

```
建筑输入 JSON ──► AI 参数建议（可选，只给立管位置、危险级等参数）
        │                       │ 失败 / 无 Key 时自动回落到规则
        ▼                       ▼
确定性布局引擎：给水、排水、雨水、消火栓、喷淋、灭火器
        │
        ▼
正交布线（A*，避让管井 / 柱）+ 水力初选管径 + 自检
        │
        ▼
DXF 粗稿 + 自检报告 + 统计 JSON ──► AutoCAD / 天正打开复核、转正式图
```

**关键原则：AI 不直接输出坐标。** 坐标、管径、数量全部由
程序算出来，AI 只影响可校验的参数。这样大模型的幻觉不会
悄悄变成图里的管线。

## 覆盖系统

- 给水：洁具支管、干管初选管径
- 排水：洁具排水管径、坡度初值、排水立管
- 雨水：屋面流量粗算、雨水立管数量与布置
- 消火栓：室内消火栓布置、走廊覆盖自检
- 喷淋：按危险级网格布置喷头、覆盖自检
- 灭火器：出口布点 + 走廊补点、最大保护距离自检

规范参考见 `docs/standards.md` 与 `src/cad_auto_draft/standards.py`，
包括 GB 50015、GB 50016、GB 50974、GB 50084、GB 50140、GB 50014。
参数均为保守的粗稿默认值，正式设计必须按现行规范与计算书复核。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m cad_auto_draft.cli \
  --input examples/hotel_floor.json --out output
# 需要 AI 参数建议时再加 --ai，并设置 CAD_AI_API_KEY 等环境变量
```

也可以用源码方式运行：

```bash
PYTHONPATH=src .venv/bin/python -m cad_auto_draft.cli \
  --input examples/hotel_floor.json --out output
```

输出：

- `output/draft.dxf`：可在 AutoCAD / 天正打开的粗稿
- `output/report.md`：自检结果 + 人工复核清单
- `output/summary.json`：统计与自检的机器可读结果

测试：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## AI 接入

可选，OpenAI 兼容接口：

```bash
export CAD_AI_API_KEY="你的 Key（不要提交到仓库）"
export CAD_AI_BASE_URL="https://api.openai.com/v1"
export CAD_AI_MODEL="gpt-4o-mini"
.venv/bin/python -m cad_auto_draft.cli --input examples/hotel_floor.json --out output --ai
```

AI 只返回立管位置、危险级、复核建议等参数，程序会校验并
限制在建筑范围内；无 Key 或调用失败时自动用规则默认值。

## 输入格式

见 `examples/hotel_floor.json`：建筑尺寸、层数、房间、
障碍物（管井 / 楼梯间）、洁具点位、出口、走廊位置、
降雨强度、危险级等。正式项目建议先做 DWG 解析，把建筑
底图自动转成这份 JSON，而不是手写。

## 天正 / AutoCAD 怎么用

见 `docs/tianzheng.md`。简单说：先用 DXF 粗稿在天正里
复核，再转成天正专用管线与正式标注出图。

## 免责声明

⚠️ **本项目输出的是粗稿，不是正式施工图、不是计算书、
不是合规证明。** 正式出图前必须由注册工程师复核水力计算、
规范条文、碰撞、现场条件并签字，不得直接用于施工。
