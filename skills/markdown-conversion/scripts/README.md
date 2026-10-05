# 转换脚本的上游基准与本地适配

本目录从 PPT Master 的 skills/ppt-master/scripts/source_to_md/ 分叉。
2026-10-05 整体对齐其 main 提交 **2d72da61**：以下八个共享文件均以上游文件为底座，再施加 hugo 的独立运行和 CLI 适配。
其中内容修复包含 4eb7b3d6、51c2979a、13ac724c、2d72da61；此基准不代表本地专有模块来自上游。

| 文件 | 上游基准 | hugo 本地改动 |
|---|---|---|
| pdf_to_md.py | 2d72da61 | 默认全部保留图片；--filter-images / --no-images 别名接入共享尺寸过滤器；保留 --raw，关闭标题识别和页眉页脚去重；保留上游矢量图渲染和 DPI 参数，no-images 禁止渲染；移除控制台编码模块依赖 |
| doc_to_md.py | 2d72da61 | DOCX、HTML、EPUB、Jupyter、pandoc 接入图片三选一；保留独立 CLI 的 --raw 兼容参数；保留未被 Mammoth 抽取的 EMF / WMF 资产与 manifest；复用上游公式、表格、脚注、尾注、图表和 Typst 回退实现 |
| ppt_to_md.py | 2d72da61 | 图片三选一与共享尺寸过滤；保留 --raw 兼容参数；SmartArt 读取改用本目录 _smartart，不导入 PPT Master 包 |
| excel_to_md.py | 2d72da61 | 转换逻辑采用上游；仅移除控制台编码和父级脚本路径依赖；--include-hidden 可通过统一入口透传 |
| web_to_md.py | 2d72da61 | 保留 trafilatura 正文路径，并启用链接提取；raw 使用完整 HTML body；no-images 去掉引用，filter-images 接入共享过滤器；保留 hugo image_sources.json 字段；下载文档接入本地转换器并透传模式 |
| _dispatcher.py | 2d72da61 | 保留上游扩展名注册表与命令构造；加入字幕路由、PDF URL → MinerU 的入口识别、目录筛选与 SourceRoute；仅使用 Python 网页后端，不引入 Node 或项目管理器 |
| _batch.py | 2d72da61 | 采用上游多文件 / 非递归目录展开、输出命名和失败继续处理；移除项目说明 |
| _conversion_profile.py | 2d72da61 | schema 保持 markdown-conversion.conversion_profile.v1；兼容 write_source_profile 等本地 API 和 JSON source_profile 字段；保留上游 URL 来源记录与失败警告 |
| _smartart.py | 2d72da61，diagram_read.py 及其必要 OOXML 辅助函数 | 只包含读取节点与结构所需的标准库代码，不包含 PPT 生成、项目约定或完整性校验 |
| convert.py | 本地独有，无对应共享文件 | 保留统一入口、类型覆盖、批量、输出命名、JSON、未知后端参数透传、MinerU 和字幕路由；修复普通后端成功后 OUTPUT / JSON 输出的不可达分支 |
| _image_filter.py | 本地独有 | 保留尺寸 / 面积 / 页面比例 / 宽高比筛选、重复图片位置和未知格式；不按压缩率删除内容图 |
| pdf_to_md_mineru.py | 本地独有 | 保留云端 OCR、下载后图片模式处理、多份 Markdown 保留和分片提示；本次未改动 |
| subtitle_to_md.py | 本地独有 | 保留 SRT / VTT / ASS、课程目录、段落锚点、raw 拼接及 40fd234 的内容保留修复；本次未改动 |
| check_env.py | 本地独有 | 保留依赖、pandoc、MinerU token 和格式就绪诊断；本次未改动 |
| __init__.py | 本地包标记 | 保持独立技能包结构；本次未改动 |
| README.md | 本地移植登记 | 记录共享基准、适配范围与复核步骤 |

## 保留、替换与删除边界

- **保留**：统一入口的全部参数语义、图片三选一、PDF raw / 矢量渲染 / DPI、MinerU、字幕、trafilatura、网页 raw 回退、环境诊断、图片来源与转换 profile。
- **替换**：五个转换器的内容解析和三个共享辅助模块整体采用指定上游；等价的矢量渲染、Office 向量资产、图表、manifest 和批量能力复用上游。
- **删除**：上游已不使用的 starts_structural_label 及“标段编号 / 收件人”等单一文档规则。
- **排除**：attribution_guard、console_encoding、project_manager、Node 网页回退和 PPT 项目目录约定。统一入口不归档或移动原始文件；网页自动输出目录沿用 hugo 已有行为。

## 测试来源与适配

tests/ 中新增的上游回归均读取 **2d72da61** 的不可变文件，导入路径改为本技能 scripts/。
PDF 页眉页脚位置、表格续接、DOCX / PPTX / Excel / 网页内容保留测试完整保留。
混合测试模块只迁移直接覆盖这五个后端的方法，排除项目管理、SVG 导出、字体和旁白等专属测试。
上游统一入口测试中的网页遍历、编码、数值和 Typst 后端用例保留；入口专属政策改由 hugo 模式测试覆盖。
test_content_preservation.py 保留原样，继续保护字幕、共享图片筛选和 MinerU。
依赖放在 ../resources/requirements.txt；python-docx 用于上游 DOCX 回归输入。

## 后续同步

1. 用 git show 读取下一上游提交，逐文件与本表基准比较。
2. 内容修复以新上游为底座，重施本表适配；不得恢复单一文档规则或引入项目依赖。
3. 在技能目录运行 python3 -m unittest discover -s tests。
4. 在独立临时目录比较真实来源的旧新 Markdown，逐项核对正文、表格和数值；百分比和更精确数字单独计数。
5. 用 convert.py 对真实 DOCX、PPTX、XLSX、PDF、SRT 冒烟，验证图片模式和 JSON；更新本表基准及适配说明。
