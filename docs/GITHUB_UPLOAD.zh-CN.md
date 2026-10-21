# 仓库与发行材料

本项目公开仓库：[Misaka-11736/Free-Search](https://github.com/Misaka-11736/Free-Search)。
预览版：[v0.1.0-preview](https://github.com/Misaka-11736/Free-Search/releases/tag/v0.1.0-preview)。

源码根目录应直接包含 README、src、tests、packaging 和 .github。
`scripts/package_source.py` 采用显式允许列表生成 `FreeSearch-source.zip`。
不要上传整个开发目录：其中可能包含真实文件副本、私有评测、索引和凭据。
Git 忽略 private、runtime-data、models、.venv、build 和 dist；发行附件独立于 Git。

## Release 附件

- 一个完整离线安装器 EXE + 全部 BIN 数据分卷，安装后提供两个入口、共用模型。
- 应用源码 ZIP。
- 第三方对应源码 ZIP，含精确修订、上游补丁、构建材料与来源映射。
- SHA256SUMS.txt，逐项记录附件校验值。

应用原创源码为 MIT；含 GPL 媒体组件的二进制组合按 GPLv3 分发。
不要把整个安装包标记为 MIT。模型、Qt 及其他依赖保留各自许可，详见根目录通知和
[二进制对应源码说明](third_party/BINARY_SOURCES.md)。

## 再制作

先按 README 安装锁定依赖、下载并验证模型，再执行测试、build.ps1、
collect_licenses.py、stage_installer.py、build_installer.ps1 和 package_source.py。
制作第三方源码附件使用对应源码说明中的脚本。每个 GitHub 附件须小于 2 GiB；
安装器分卷设为 1,800,000,000 字节。上传后再核对服务器附件大小和 SHA256。

真实评测查询、期望文件、证据与逐条结果只留本机；公开报告是汇总，并披露未完成人工
复核与多模态质量验收。CI 在 Windows 运行测试，结果以 GitHub 实际执行为准。
