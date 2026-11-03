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

## 图形界面（推荐：双击就能用，不用记命令）

**直接双击 `cad-auto-draft.exe` 就会打开图形界面**，不会再像
以前那样因为没有命令行参数就报错退出。界面里点一点就能完成
全部流程：

1. 选输入：内置酒店标准层示例（不用准备文件，直接试）、
   建筑输入 JSON、或建筑底图 DXF（自动识别块 / 外部参照）
2. 参数留空就是按输入文件来，想改建筑类型、喷淋 / 灭火器
   危险级、层数、降雨强度再选
3. 选输出文件夹，点“生成粗稿”，日志里会显示统计和自检结果，
   PASS 是绿色、WARN 是黄色、FAIL 是红色
4. 点“打开输出文件夹”，把 `draft.dxf` 拿到 AutoCAD / 天正里
   打开复核，再转成天正专用管线和正式标注出图

命令行仍然可用：`cad-auto-draft.exe --gui` 打开界面，
带 `--input` / `--plan` 参数时走原来的命令行模式。

## Windows exe（不用装 Python）

每次推送到 main 分支，GitHub Actions 都会在 Windows 上自动
打包出 `cad-auto-draft.exe`。

工作流文件在 `.github/workflows/build-exe.yml`（因 GitHub App
没有 workflow 写入权限，该文件是经 GitHub 网页手动建立的，
后续代码推送不会覆盖它），每次推送都会自动打包：

1. 打开仓库的 Actions 页面，找到最新一次成功的
   `Build Windows exe` 运行
2. 下载 Artifacts 里的 `cad-auto-draft-windows`
3. 在 Windows 命令行里直接运行，不用装 Python，也不用装 AutoCAD
   就能出粗稿（AutoCAD / 天正只在复核、转正式图时才需要）：

```bat
cad-auto-draft.exe --input examples/hotel_floor.json --out output
cad-auto-draft.exe --plan 建筑底图.dxf --plan-out 解析结果.json --out output
```

打了 `v*` 标签时，exe 还会挂到 GitHub Release 附件里。
本地打包 Windows exe 的方法：见 `cad-auto-draft.spec`，
在 Windows 上 `pip install pyinstaller` 后运行
`pyinstaller cad-auto-draft.spec`。

## 建筑底图识图（块 / 外部参照）

不用手写 JSON 了，先把底图转成 DXF，再直接解析：

```bash
.venv/bin/python -m cad_auto_draft.cli \
  --plan 建筑底图.dxf --plan-units mm \
  --plan-out 解析结果.json --out output
# 外部参照缺文件时显式指定，可重复：
#   --xref 参照块名=参照文件.dxf
```

- DWG 不能直接读：先在 AutoCAD / 天正用 DXFOUT，
  或用 ODA File Converter 转成 DXF（程序遇到 DWG 会直接报错并提示）
- 块会递归展开（含嵌套块），块名含马桶 / 洗脸盆等关键词的
  识别为洁具，管井 / 楼梯 / 电梯 / 柱识别为障碍物
- 外部参照找不到文件时，不会静默丢掉，会在输出里列出
  `missing_xrefs`，必须补齐参照再正式使用
- 详细复核方法、常见漏认原因见 `docs/plan_recognition.md`

## 快速开始（源码）

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
降雨强度、危险级等。也可以用 `--plan` 直接解析建筑底图 DXF，
再用 `--input` 覆盖层数、危险级、立管位置等设计参数。

## 天正 / AutoCAD 怎么用

见 `docs/tianzheng.md`。简单说：先用 DXF 粗稿在天正里
复核，再转成天正专用管线与正式标注出图。

## 免责声明

⚠️ **本项目输出的是粗稿，不是正式施工图、不是计算书、
不是合规证明。** 正式出图前必须由注册工程师复核水力计算、
规范条文、碰撞、现场条件并签字，不得直接用于施工。
