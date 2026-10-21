# 离线模型和内容解析

运行程序不会下载模型。模型准备脚本只在开发／制作模型包时联网。
`LocalModels` 始终使用本地绝对路径及 `local_files_only=True`，禁用 Hugging Face 联网与遥测。
缺失文件或依赖会显式报错；没有语音模型不能把音频文件名当作转写成功。

模型目录：

```text
models/
  text-embedding/   intfloat/multilingual-e5-small (384 维)
  text-reranker/    BAAI/bge-reranker-base
  vision/           OFA-Sys/chinese-clip-vit-base-patch16 (512 维)
  speech/           Systran/faster-whisper-small (CTranslate2)
```

每个目录保留完整配置、分词器、模型权重及其许可证。下载脚本须固定来源、版本，并生成文件哈希清单。
OCR 使用 `rapidocr-onnxruntime` 发行包自带的 ONNX 模型；打包时必须包含该包的模型与配置文件。

- 文本向量使用 E5 的平均池化、L2 归一化；文档前缀 `passage: `，查询前缀 `query: `。
- 图文向量使用 ChineseCLIP。文本查询图片和以图搜图均在同一 512 维空间内进行。
- 重排使用 BGE 的查询／文本联合输入评分；分数是排序信号，不是置信概率。
- 语音使用 faster-whisper CPU int8 转写，并保留开始／结束秒数。
- CPU 默认限制计算线程。已用模型在进程内复用，避免逐文件重新加载；首次使用各模型有加载开销，关闭程序后释放。

接口：`embed_text(list[str])`、`embed_query(str)`、`embed_images(list[str])`、
`embed_vision_text(list[str])`、`rerank(query, texts)`、`transcribe(path)`、`ocr(path)`。
`availability()` 检查本地文件及依赖存在，不代表推理已通过测试；实际执行仍可能发现损坏文件。

## 内容范围和限制

| 格式 | 提取内容及定位 |
| --- | --- |
| TXT／源码／常见文本配置 | UTF-8、带 BOM 的 UTF-16、GB18030；420 字符分段，60 字符重叠 |
| DOCX | 段落、表格、页眉页脚、脚注尾注；内嵌位图的 OCR 和视觉索引。DOCX 不保存可靠页码，显示正文／部件定位 |
| PPTX | 幻灯片文字、备注、内嵌位图；根据 presentation 与关系文件还原幻灯片显示顺序及备注所属页 |
| PDF | 按页提取文本及渲染画面；文字少于 20 字符的页进行 OCR；加密文件明确失败 |
| PNG／JPG 等 | OCR 文字和完整画面向量 |
| 录音 | 讲话转写及秒数；不做环境声音／音乐分类 |
| 视频 | 每 10 秒采样画面，加 OCR 和视觉向量；存在音轨时转写讲话 |

视频采样可能遗漏短于采样间隔的事件；不是逐帧识别。当前所有音轨默认只处理解码器选中的主音轨。
扫描页、截图和字体会影响 OCR；PDF 中已有足够文本的页面不会再次 OCR，图中文字仍可通过视觉向量召回。
Office 解析不运行宏，不执行源码。专有工程文件（例如 DWG）当前明确标为内容不支持，不能视作语义解析完成。

## 上游参考

- [E5 模型卡](https://huggingface.co/intfloat/multilingual-e5-small)
- [BGE 重排模型卡](https://huggingface.co/BAAI/bge-reranker-base)
- [ChineseCLIP 模型卡与官方推理示例](https://huggingface.co/OFA-Sys/chinese-clip-vit-base-patch16)
- [faster-whisper 实现与本地模型加载](https://github.com/SYSTRAN/faster-whisper)
