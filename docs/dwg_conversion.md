# DWG 转 DXF 与参照绑定：本程序怎么做

## 结论

DWG 直接给程序，不用先手动转。程序按下面顺序自动试转换工具，
试到一个能用的为止；一个都没有时，给出明确的安装指引，而不是
静默失败或假装转换成功。

## 转换工具（按尝试顺序）

1. **ODA File Converter（免费，推荐）**
   - 开源设计联盟（Open Design Alliance）的免费工具，Windows / macOS / Linux 都有。
   - 命令行格式（官方示例）：`ODAFileConverter "input_folder" "output_folder" ACAD2018 DXF 0 1`
     参数依次是输入文件夹、输出文件夹、输出版本、输出格式 DXF、
     是否递归、是否审计。它只处理文件夹，不处理单个文件，所以程序会
     先把单个 DWG 复制到临时输入文件夹再转。
   - 下载：https://www.opendesign.com/guestfiles/oda_file_converter
   - 装好后把 ODAFileConverter.exe 所在目录加到 PATH，或设环境变量 ODAFC_PATH 指向它。
   - 本程序转出的版本是 ACAD2010（R2010），和程序自己写的 DXF 版本一致。

2. **LibreDWG（免费）**
   - `dwgread -O DXF -o 输出.dxf 输入.dwg`，或 `dwg2dxf 输入.dwg`。
   - DWG 版本覆盖和天正对象处理弱于 ODA，只作备选。

3. **AutoCAD 本身（已装 AutoCAD / 天正的电脑）**
   - 用 AutoCAD 控制台 `accoreconsole.exe` 跑脚本：打开 DWG，
     `-XREF Bind` 把参照绑定成块（`-XREF` 命令的 Bind 选项就是把
     DWG 参照转成宿主图里永久的一部分），再 `DXFOUT`。
   - 这是唯一能可靠处理天正自定义对象的路，因为天正是在 AutoCAD
     里运行的；ODA / LibreDWG 看到的天正对象是代理对象。

## 参照怎么找、怎么绑

- 主图转成 DXF 后，程序列出所有空块（即参照），按这个顺序找文件：
  显式 `--xref` 映射 → `--base-plan` 同名匹配 → 自动搜索主图文件夹
  及其子文件夹 → `--base-plan` 兜底（日志写明是兜底）。
- 找到的参照如果是 DWG，同样走上面的转换流程转成 DXF 再展开，
  所以“主图 DWG + 参照 DWG”一整套不用手动逐个转。
- `--bind-out` / 界面勾选框做的绑定，是程序自己的展开器
  （`binder.py`）：把参照、嵌套块都展开成普通图元，写成一个独立 DXF。
  它只展开直线 / 多段线 / 圆 / 弧 / 文字 / 多行文字；标注、填充、
  三维、天正对象会被跳过并计数，日志里会写跳过数量。
  要字节级绑定（含天正对象）时，用 AutoCAD 的 `-XREF Bind` 那条路。

## 限制，必须说清楚

- 没有转换工具时，程序不能凭空读 DWG：DWG 是私有二进制格式，
  ezdxf 读不了，这是格式限制，不是程序 bug。装 ODA 是最快的解法。
- 天正自定义对象（墙、门窗对象）在 ODA / LibreDWG 下可能不完整：
  须在天正里先分解 / 转成普通图元，再转 DXF，或直接走 AutoCAD 路。
- 参照路径如果在别的盘、别的项目文件夹，且既没放在主图文件夹、
  也没在 `--xref-dir` / 界面“参照文件夹”里指定，程序是找不到的，
  会如实列在 `missing_xrefs` 里，不会猜一个相似名字的文件顶上。
- 转换后的 DXF 默认放在输出文件夹的 `_converted` 里，原 DWG 不动，
  你可以打开转换后的 DXF 核对一次，再决定要不要进粗稿。
