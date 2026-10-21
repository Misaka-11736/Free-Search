# 本地检索评测

真实文件、路径、正文证据和查询集保存在 `private/evaluation/`，该目录被 Git 忽略，
也应从源码上传包中排除。公开仓库仅包含协议、评测程序和指标单元测试。
不将真实用户文件随仓库分发，不调用模型 API。

首轮私有集包含 **52 条中文文字查询、52 个期望目标文件、65 个候选文件**，
覆盖 PDF、DOCX、PPTX 的正文。查询由开发代理阅读真实文件内容后编写，使用语义改写，
并记录 SHA256、页码/段落/幻灯片位置及正文证据；它们不是用户历史搜索记录，也未经过用户人工审定。
评测集在检索测试前冻结，校验和保存在私有 `FROZEN.sha256` 中。

这份集用于文档试点，不代表全盘、多模态或十万文件准确率。
音频、视频、图片输入、语音提问、源码、元数据过滤的质量验收需增加对应数据；
增量正确性另由索引测试验证。10 条无答案探针单独保存，尚待人工审定；
仅报告返回空结果的比例，不把向量相似度当成有答案概率。

## 重现

在仓库根目录、项目虚拟环境中执行：

```powershell
python scripts/evaluate.py --validate-only
python scripts/evaluate.py --index --modes bm25 vector hybrid_no_rerank hybrid
```

评测默认使用独立的 `private/evaluation/index`，报告写入
`private/evaluation/report.json`。必须使用固定候选全集；程序拒绝混入其他文件的索引。
任何原文件 SHA256 变化都会使验证失败，应重新审定相关条目并记录数据集版本，
不能直接忽略散列错误后比较分数。模型缺失的模式明确标记跳过，不以 BM25 回退冒充向量或重排结果。

若需运行无答案探针：

```powershell
python scripts/evaluate.py --modes hybrid --no-answer-probes private/evaluation/no-answer-probes.json
```

## 数据格式

`queries.json` 顶层包含 `schema_version`、`candidate_pool`（相对于数据集的语料清单路径）、
`status`、`provenance`、`limitations` 和 `queries`。
每条查询包含唯一 `id`、`query`、`input_modality`、`target_modality`、
`filters`、`human_reviewed` 和非空 `expected`。
每个期望文件包含真实绝对 `path`、`sha256`、`locator`、`evidence_anchor` 和 `evidence`。
`corpus.json` 为候选文件列表，每项包含 `id`、`path`、`sha256`。
多格式副本可作为多个合法目标；判断以文件为单位，重复内容块只计算一次。

## 指标解释

- Hit@1 / Hit@5：前 1 / 5 个文件是否包含至少一个已标注相关文件。
- MRR@10：首个相关文件在前十名中的排名倒数，无命中为 0。
- Recall@10：前十个文件覆盖已标注相关文件的比例。它受标注完整性影响。
- 延迟：顺序查询的中位数和 P95，包含首个查询可能发生的模型加载，不伪称纯热查询耗时。
- 四种对照：BM25、向量、混合无重排、混合加文字重排。当前向量模式同时启用文字和视觉向量召回（模型及对应画面可用时），不是纯文字向量的单独消融。

结果必须同时公布数据集版本、候选文件数、模型状态、失败解析文件数和各模式状态。
模型/参数调试使用另设开发集；如果使用本试点结果调整过参数，必须披露并另建最终验收集。
真实查询结果与路径留在私有报告，公开时只摘录数值和覆盖范围。

运行指标测试：`python -m unittest discover -s evaluation -p "test_*.py"`。
