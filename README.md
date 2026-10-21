# Free Search

[下载 v0.1.0-preview](https://github.com/Misaka-11736/Free-Search/releases/tag/v0.1.0-preview) · [验证记录](docs/VALIDATION.md) · [问题反馈](https://github.com/Misaka-11736/Free-Search/issues) · [第三方源码](docs/third_party/BINARY_SOURCES.md)

Windows 11 本机语义文件搜索工具。用一句描述查找文档正文、截图文字、图片场景或音视频中的讲话，也可以选择图片、录音文件作为查询输入。

一个安装包提供 **完全离线版** 和 **API 版** 两个入口，共用本地模型和索引。默认全部在本机处理；API 版经当前会话的目录和内容类型授权后，才会发送有限文字片段进行远程重排。

> 当前是 `v0.1.0-preview` 预览版。已有真实文档试点评测和本机 EXE 推理检查，仍缺干净 Windows 环境的完整验证、多模态质量验收、GPU 加速及真实付费 API 服务验证。建议先选择小目录试用。程序只读访问原始文件，索引和预览存入本地数据目录。

## 下载与安装

打开 [Release 页面](https://github.com/Misaka-11736/Free-Search/releases/tag/v0.1.0-preview)，展开 **Assets**，下载同版本的：

- `FreeSearch-Setup-0.1.0-preview.exe`；
- 所有以 `FreeSearch-Setup-0.1.0-preview-` 开头、以 `.bin` 结尾的数据分卷；
- `SHA256SUMS.txt`，用于检查下载完整性。

将 EXE 和全部 BIN 放在同一目录，保留原始文件名，运行 EXE。**只有 EXE 无法安装**，BIN 无须解压。GitHub 自动生成的 `Source code (zip)` 不包含程序或模型；第三方源码附件供修改及再分发使用，普通安装不需要下载。

安装包包含四组本地模型及 OCR 模型，安装和首次推理不需要下载。可在 PowerShell 核对每个文件的 SHA256：

```powershell
Get-FileHash .\FreeSearch-Setup-0.1.0-preview.exe -Algorithm SHA256
Get-ChildItem .\FreeSearch-Setup-0.1.0-preview-*.bin | Get-FileHash -Algorithm SHA256
```

与清单逐项比较。本预览版未购买代码签名证书，Windows 可能提示未知发布者；请核对仓库、版本和校验值后决定是否运行。

默认安装到当前用户，无需管理员权限：

| 项目 | 默认位置 |
| --- | --- |
| 程序、共用模型 | `%LOCALAPPDATA%\Programs\FreeSearch` |
| 索引、预览、临时文件、目录设置 | `%LOCALAPPDATA%\FreeSearch\data` |
| 开始菜单 | `Free Search - 完全离线版`、`Free Search - API 版` |
| API 密钥（选择记住时） | Windows 凭据管理器 |

卸载会删除安装器管理的程序和模型，保留索引数据及已保存凭据。确认不需要后，可关闭两个入口再手动删除数据目录。升级前建议备份该目录；预览版尚未承诺跨版本索引兼容，模型或解析配置变化时须更新索引。

## 运行要求

- Windows 11 x64，建议至少 16GB 内存和 SSD；目前只提供 x64 安装包。
- 为安装器、程序和模型预留约 10GB 空间，内容索引另计；扫描 PDF 和长视频会产生额外预览、转写和向量数据。
- 首次索引和查询需加载模型，建议接通电源，先扫描小目录，再扩展至固定磁盘。
- 当前发行锁定 **CPU 推理**，不需要 NVIDIA 显卡，也不会自动使用 CUDA。GPU 加速尚未验收。

开发试用机器为 Ryzen 7 7840H、16GB 内存、RTX 4060 Laptop 8GB、Windows 11，实际使用 CPU。该机器的结果不能代表其他硬件或十万真实多模态文件。

## 第一次使用

1. 启动“完全离线版”，等待本地模型与索引检查结束。
2. 点击 **添加目录**，先选择少量文档或截图。需要全盘搜索时点击 **添加所有固定磁盘**；其他位置也可逐个添加。
3. 点击 **建立／增量更新索引**，查看发现、处理、未变化和失败数量。**暂停索引**在当前文件结束后停止，再次更新会复用已完成文件。
4. 描述目标内容并搜索。选中结果查看原路径、片段及页码、幻灯片、段落或秒数等位置。
5. 双击或点击 **打开文件**、**打开所在目录**，调用系统关联应用。目前页码和秒数只提供定位线索，不自动跳转播放器。
6. 文件变化后手动增量更新。本版没有实时监听，程序关闭时不继续扫描。

示例描述：“讨论电池散热和冷却结构的方案”“带有 Python 报错的截图”“讲到项目进度的录音”“蓝色天空和建筑物的照片”。这是用法示例，不是全部通过验证的查询。具体术语、文件名关键词、过滤条件也有帮助。

**过滤条件需在左侧控件填写**：扩展名如 `.pdf,.docx`、绝对目录前缀、修改时间上下界。自然语言中的“上周”“PDF”不会自动变成过滤器；日期按本机时间解释，多个已填条件共同生效。

**以图搜图**：选择图片，匹配已索引图片、文档画面和视频采样帧。可同时保留文字作为额外信号，使用“取消图片”清除。

**语音文件提问**：选择已有录音，本地转写后查询。尚无麦克风实时录制。API 版保留录音来源信息，来源目录与音视频类型也须获外发授权；清空查询会移除其来源关联。

## 支持格式与边界

| 类型 | 当前能力 | 边界 |
| --- | --- | --- |
| PDF | 按页正文、渲染画面；文字少的页做 OCR | 加密、损坏文件会失败，扫描质量影响 OCR |
| DOCX | 段落、表格、页眉页脚、脚注尾注、内嵌位图 | 无稳定页码，以部件和段落定位；不执行宏 |
| PPTX | 幻灯片文字、备注、内嵌位图 | 不完整解释动画或全部图表语义 |
| 文本、日志、配置 | 分段正文；UTF-8、带 BOM UTF-16、GB18030 | 二进制不强行作为文本解析 |
| 源码和项目文本 | `.py`、`.cpp`、`.h`、`.js`、`.ts`、`.java`、`.cs`、`.go`、`.rs`、`.sln`、`.vcxproj` 等 | 不执行源码；不做编译器符号及工程依赖分析 |
| 图片 | PNG、JPG、JPEG、BMP、TIF、TIFF、WEBP：OCR + 视觉向量 | 动画、多页图片不保证逐帧覆盖 |
| 录音 | WAV、MP3、M4A、AAC、FLAC、OGG、WMA：讲话转写 + 秒数 | 不检索环境声、音乐或身份；编码影响解码 |
| 视频 | MP4、MKV、MOV、AVI、WEBM、WMV、M4V：采样画面、OCR、讲话 | 每 10 秒抽帧，短事件可能遗漏；默认主音轨 |
| 其他格式 | 文件名、元数据，明确标记“仅元数据” | DWG、STEP、RVT、PSD、旧 DOC/PPT、XLSX 等未实现内部解析 |

完整清单见 [extractors.py](src/free_search/extractors.py)，细节见 [模型与解析](docs/LOCAL_MODELS.md)。本版没有集成本机 CAD 或 Office 自动转换。权限不足记录枚举错误，损坏或受保护文件计入失败；GUI 提供汇总，详细状态在本地 SQLite 的 `files` 表中。

## 检索和增量更新

```text
文件 → 解析 / OCR / 讲话转写 → 内容块、位置、指纹
                            ├─ SQLite FTS5 + 中文 BM25
                            └─ LanceDB 文字 / 视觉向量
查询 + 时间 / 类型 / 路径过滤 → 多路召回 → RRF 融合 → 文字重排 → 文件去重
```

文字向量使用 multilingual E5 small，图文空间使用 ChineseCLIP。BGE 重排文字、OCR 和转写；纯视觉候选保留视觉排序，**尚无视觉交叉编码器重排**。分数是排序信号，不是正确概率；没有可靠的“本机不存在该文件”判断。

增量更新先枚举目录，比较路径、大小、修改时间和模型状态。变化文件再核对 SHA256，按文件更新内容块及向量，内容相同时复用已有版本。只有完整成功枚举的目录才触发删除同步；移动视为旧路径删除、新路径加入。

“只改三个”仍需遍历目录，但不用重解析十万份内容或重算全部向量。向量存储维护仍可能产生额外工作，增量不等于没有目录扫描。

两个入口共用索引，同一数据目录只允许一个进程更新。建议同时只开一个入口以节省内存。移除界面目录只影响后续扫描，已有索引仍可搜索；尚无单目录清除按钮。若需彻底重建，先关闭程序，备份并删除整个数据目录，再索引保留目录。

## API 授权与隐私

离线入口在 Python 层阻止普通网络连接、DNS 和 UDP 外发；数据库内部事件循环必需的 socketpair 有受限例外。需要系统级隔离时可另用防火墙或物理断网。

API 入口默认本地处理。进入 **API 设置**，填写服务基础地址、重排模型及密钥，检查授权目录，勾选文本授权；按需授权图片 OCR、音视频转写及画面文字。确认预算后启用，点击 **恢复本地** 停止远程重排；重启后须重新授权。

| 项目 | 行为 |
| --- | --- |
| 发送内容 | 查询 + 获授权候选文字，不上传原始图片、音视频或完整文档 |
| 每请求上限 | 查询 4,000 字符；20 个候选，各 2,000 字符 |
| 会话预算 | 默认 100 次，可调整；正文总量 10 MiB |
| 失败请求 | 也消耗预算，不自动重试 |
| 授权 | 目录 + 文本 / 图片衍生文字 / 音视频衍生文字，仅当前运行 |
| 密钥 | 默认内存；记住时用 Windows 凭据管理器，不写索引 |
| 网络 | HTTPS，仅回环可 HTTP；不跟随重定向，不读取代理环境变量 |
| 索引和向量 | 始终本地，不调用云端嵌入 |

文档授权包含获准文档内提取的文字；图片和媒体授权只控制对应来源的衍生文字。片段可能含敏感信息，请按目录内容授权。索引、转写和预览未加密，源文件删除后也不会清除全部历史缓存。没有遥测或自动上传错误日志。

协议为 **`POST <基础地址>/rerank`**，不支持任意聊天接口。请求：

```json
{"model":"your-rerank-model","query":"...","documents":["..."],"top_n":1,"return_documents":false}
```

响应为 `{"results":[{"index":0,"relevance_score":0.9}]}`，须完整覆盖候选且编号不重复。服务出错可恢复本地。已完成模拟 HTTP 授权、预算和响应测试，真实付费服务尚未联调；请求数和字节预算不等于金额上限。

## 验证结果

| 验证 | 结果 | 范围 |
| --- | --- | --- |
| 真实文档试点 | 52 条依据真实正文编写的查询、65 个真实候选；混合重排 Hit@5 为 47/52（90.38%） | 开发者编写，未逐条用户复核；不是全盘或多模态准确率 |
| 查询耗时 | 混合重排中位 8.254 秒，P95 13.471 秒 | CPU 试点，含可能的首次加载；非性能承诺 |
| 十万文件修改三个 | 3 个重解析、99,997 个复用、3 个计数向量输入 | 合成磁盘文件、预置索引、计数模型，禁用 ANN 维护 |
| 媒体通路 | 8 图、1 录音、1 视频成功索引；原图回查 8/8 首位 | 功能检查，不是视觉语义质量评测 |
| 自动化回归 | 45 项通过 | 含跨进程写锁、双入口数据目录、授权、增量与离线保护 |
| 冻结 EXE | 两版完成文字、图片、语音的本地索引和查询 | 本机检查，未替代干净 Windows 验收 |
| 分卷安装器 | 实际安装、两个入口、共享索引、卸载保留数据均通过 | 临时目录，本机验证，未替代干净虚拟机 |

方法、四种检索模式对比、资源采样和缺口见 [VALIDATION.md](docs/VALIDATION.md)。真实查询、期望文件、证据和逐条报告只留开发机器，公开仓库不含私有语料。

## 命令行

窗口版 EXE 无终端输出，用 `--output` 保存 JSON：

```powershell
$program = "$env:LOCALAPPDATA\Programs\FreeSearch\FreeSearch-offline.exe"
Start-Process -FilePath $program -ArgumentList '--diagnose --output "D:\SearchReports\diagnostics.json"' -Wait
Start-Process -FilePath $program -ArgumentList '--index "D:\MyDocuments" --output "D:\SearchReports\index.json"' -Wait
Start-Process -FilePath $program -ArgumentList '--query "电池冷却结构" --output "D:\SearchReports\results.json"' -Wait
Start-Process -FilePath $program -ArgumentList '--transcribe "D:\Audio\question.wav" --output "D:\SearchReports\speech.json"' -Wait
```

还支持 `--data-dir`、`--model-dir`、`--mode bm25|vector|hybrid_no_rerank|hybrid`。默认 hybrid 含重排；CPU 过慢时可在 CLI 选无重排模式，GUI 暂无模式切换。自定义共享索引需给两个快捷方式加相同 `--data-dir`。

安装版使用用户数据目录；没有 `installed.json` 的普通便携构建沿用 EXE 同级 `runtime-data/`。CLI 的 API 入口也默认本地，远程授权通过 GUI 完成。

## 源码运行与构建

需要 Python 3.12、Windows 11 x64；安装器使用 [Inno Setup 6.7.3](https://github.com/jrsoftware/issrc/releases/tag/is-6_7_3)。准备依赖和模型需联网，运行不下载模型。

```powershell
git clone https://github.com/Misaka-11736/Free-Search.git
cd Free-Search
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe scripts/download_models.py
.\.venv\Scripts\python.exe -m free_search
```

模型下载按 [模型锁](packaging/models.lock.json) 固定修订并检查 SHA256。完整 `models/` 可以复制至断网电脑；只有源码和下载脚本不构成离线安装。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\build.ps1 -Edition offline -OutputRoot dist/release-build
.\.venv\Scripts\python.exe scripts/collect_licenses.py --output dist/licenses
.\.venv\Scripts\python.exe scripts/stage_installer.py
.\scripts\build_installer.ps1 -IsccPath 'C:\Tools\Inno Setup 6\ISCC.exe'
.\.venv\Scripts\python.exe scripts/package_source.py
# 再分发时还需准备精确版本的第三方对应源码（此步骤联网）
.\.venv\Scripts\python.exe scripts/package_dependency_sources.py --download
```

Staging 目录 `dist/installer-stage/FreeSearch/` 必须为空，避免旧文件混入。重复制作前先检查并移走旧 staging。`build.ps1 -Edition api` 仍支持单独便携构建。脚本隔离 DLL 搜索路径，移除误收录 ICU 及未使用插件；第三方源码、补丁与构建材料见 [BINARY_SOURCES.md](docs/third_party/BINARY_SOURCES.md)。不承诺不同工具链得到逐字节相同二进制。

## 私有评测与项目结构

```text
src/free_search/  解析、模型、索引、搜索、授权、Qt 界面
packaging/       模型锁、启动器和安装器
scripts/         准备、构建、许可收集、评测、增量验证
tests/           自动化测试
evaluation/      评测协议与格式示例
docs/            使用、验证、模型和第三方来源
```

Git 排除 private、models、runtime-data、虚拟环境及构建产物。源码上传包使用显式允许列表，不要将索引、密钥或原文件提交至 Issues。

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_incremental.py
.\.venv\Scripts\python.exe scripts/evaluate.py --validate-only
.\.venv\Scripts\python.exe scripts/evaluate.py --index
```

真实评测不公开。克隆后按 [评测说明](evaluation/README.zh-CN.md) 本地准备至少 50 条查询及期望文件，示例不能代替验收。评测按文件去重，对比 BM25、向量、混合无重排、混合重排，计算 Hit、MRR、Recall 和耗时。

## 常见问题

| 问题 | 处理 |
| --- | --- |
| 缺少安装数据分卷 | 下载同版本全部 BIN，与 EXE 同目录，不重命名 |
| 模型缺失 | 检查完整安装和诊断 JSON；不自动补下载 |
| 仍搜到旧内容 | 手动增量更新，本版没有实时监听 |
| 查询慢 | 等待首次加载；CLI 可选无重排模式 |
| 找不到文件 | 检查是否已索引、格式支持、失败数量及过滤条件 |
| 工程文件只能搜名称 | 本版未实现其内部解析 |
| OCR / 转写不准确 | 检查源质量和采样范围，增加文字线索或缩小目录 |
| API 失败 | 检查 /rerank 协议、地址、模型、授权与预算，可恢复本地 |
| 索引被占用 | 等待其他实例完成，不删除活跃进程的锁文件 |
| 空间不足 | 自定义安装目录；两个入口设置相同 --data-dir |
| QtCore / DLL 失败 | 核对完整安装和哈希，反馈系统与错误，不下载随机 DLL |

反馈时提供系统版本、入口、步骤、扩展名及脱敏诊断；日志可能含本机路径，发送前请检查。

## 许可与再分发

原创源码为 [MIT](LICENSE)。二进制组合含 GPLv3 媒体组件，按 [BINARY_LICENSE.txt](BINARY_LICENSE.txt) 的 GNU GPLv3 条款分发；Qt、模型及其他组件保留各自许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。包含全部依赖的安装包不能标为“全部 MIT”。

同一 Release 提供应用源码、精确版本第三方源码、补丁与构建材料及 SHA256。动态库保留在 `_internal/`，允许替换兼容修改版本，没有签名锁定。再分发应保留适用许可、版权及对应源码获取方式。
