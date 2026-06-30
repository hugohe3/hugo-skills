# Material Handling

资料处理是结构化分析的基础。只要用户提供文档、长文本、网页、表格、代码、访谈记录或其他外部材料，就必须先完成资料整理，再进入深度分析。

## `0-inputs/` 与 `0-materials/`

`0-inputs/` 放原始资料，原则是不改动、可追溯、作为证据源头。

`0-materials/` 放处理后、可用于分析的资料，是从 `0-inputs/` 派生出来的工作材料。

```text
0-inputs/     = 原始材料，不动它
0-materials/  = 分析材料，可以整理、转换、摘录、标注
```

## 资料处理流程

1. **归档原始资料**
   - 将用户提供的原始文件、粘贴文本、链接摘录或访谈记录保存到 `0-inputs/`。
   - 不改写原始资料；需要清洗时另存到 `0-materials/`。

2. **转换为可分析格式**
   - PDF / Word / Excel / PowerPoint / EPUB / HTML / 字幕 / URL 等资料，优先调用 `markdown-conversion` skill 转成 Markdown。
   - 转换结果放入 `0-materials/converted/`。
   - 如果资料已经是可读 Markdown 或纯文本，可直接复制到 `0-materials/`。

3. **建立来源索引**
   - 在 `0-materials/source-index.md` 记录资料名称、来源、日期、可信度、用途。
   - 对关键事实保留来源位置，例如文件名、章节、页码、URL 或访谈对象。

4. **提取证据**
   - 在 `0-materials/evidence.md` 中整理关键事实、数字、引用、反常点和不确定信息。
   - 每条证据都标明来源；无法溯源的信息只能作为假设或待验证项。

5. **区分事实、假设和观点**
   - 事实：有来源或可验证的数据。
   - 假设：基于有限信息的可验证猜测。
   - 观点：主观判断或解释，需要后续证据支持。

6. **形成资料盘点**
   - 在 `0-materials/material-inventory.md` 中列出已获取资料、已处理资料、可信度、覆盖的问题范围。
   - 在 `0-materials/gaps.md` 中列出继续分析所需但尚未获得的资料。
   - 如果资料缺口会影响问题定义，先输出临时定义并标注“待资料补充后复核”。

## 资料处理输出

```text
0-materials/
├── converted/              # 转换后的 Markdown 或文本
├── material-inventory.md   # 已获取资料盘点
├── source-index.md         # 来源索引
├── evidence.md             # 证据清单
└── gaps.md                 # 资料缺口和待验证问题
```

进入结构化分析前，至少要能回答：我们已经知道什么、还不知道什么、哪些信息只是猜测。

## 后续资料补充机制

当后续分析发现需要新增资料时，不要把新资料直接写进分析结论。按以下流程回填：

1. **登记缺口**
   - 在 `0-materials/gaps.md` 记录缺口、用途、影响阶段和优先级。
   - 标注缺口类型：事实缺口、数据缺口、专家判断缺口、用户偏好缺口、外部约束缺口。

2. **补充原始资料**
   - 新获得的文件、访谈、网页摘录或用户补充信息先放入 `0-inputs/`。
   - 文件名建议带日期或来源，例如 `20260630-user-interview.md`、`20260630-market-report.pdf`。

3. **处理并索引**
   - 转换或清洗后放入 `0-materials/converted/` 或 `0-materials/`。
   - 更新 `source-index.md`、`material-inventory.md`、`evidence.md`。
   - 如果缺口已解决，在 `gaps.md` 中标记状态为 `已补充`，并写明来源。

4. **回到受影响阶段**
   - 如果新资料改变问题理解，更新 `1-problem-definition/`。
   - 如果新资料改变拆解方式，更新 `2-problem-structuring/`。
   - 如果新资料改变优先级，更新 `3-prioritization/`。
   - 如果新资料验证或推翻假设，更新 `5-analysis/` 和 `6-synthesis/`。

5. **更新总控文件**
   - 每次补充资料后更新 `brief.md` 的“资料状态”“证据状态”“决策日志”和“下一步”。

资料补充是循环过程。允许阶段回退；不要为了保持流程线性而忽略新证据。
