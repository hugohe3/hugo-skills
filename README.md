# hugo-skills

个人 AI 技能集合，用于日常工作流。技能以通用 `SKILL.md` 形式组织，可迁移到支持 skill / agent skill 机制的平台使用。

## 什么是技能？

技能是可复用的独立能力包。每个技能位于 `skills/` 下的独立目录，通过 `SKILL.md` 描述适用场景、执行流程和可用资源；支持 skills 的平台可以读取这些说明，并按需调用脚本、模板和参考资料。

## 技能列表

| 技能 | 说明 |
|---|---|
| [coordinate-converter](skills/coordinate-converter/SKILL.md) | 在 WGS84 / GCJ02（高德） / BD09（百度）坐标系之间批量换算经纬度，支持单点、坐标列表，以及 CSV / TSV / GeoJSON / GPX / KML 文件原格式转换 |
| [epub-translator](skills/epub-translator/SKILL.md) | 使用当前 agent 模型将英文 EPUB 翻译为简体中文 EPUB，并保留目录、图片、样式和阅读顺序 |
| [image-local-replacer](skills/image-local-replacer/SKILL.md) | 对 PNG/JPG/WebP 位图做小范围局部覆盖、修补或文字重写，保持原图尺寸和未选中区域不变 |
| [learning-master](skills/learning-master/SKILL.md) | 六阶段学习助手，用于系统化学习课程、书籍和文章，生成学习计划、笔记、Anki 卡片和外化产出 |
| [markdown-conversion](skills/markdown-conversion/SKILL.md) | 将 PDF / Word / Excel / PowerPoint / EPUB / HTML / 字幕 / 网页 URL 转换为干净的 Markdown，供 LLM 读取 |
| [structured-problem-solving](skills/structured-problem-solving/SKILL.md) | 用麦肯锡七步问题解决法分析复杂问题，结合逐问澄清、术语统一、决策地图、MECE 拆解、优先排序、分析论证和方案呈现形成解决路径 |

## 安装

### Option A — Download ZIP

不需要 Git。在 GitHub 页面点击 **Code → Download ZIP**，解压到本地目录。

### Option B — Git clone

需要已安装 Git。

```bash
git clone https://github.com/hugohe3/hugo-skills.git
cd hugo-skills
```

之后按需安装对应技能的依赖：

```bash
# learning-master：Anki TSV 导出
pip install -r skills/learning-master/resources/requirements.txt

# markdown-conversion：文档转换
pip install -r skills/markdown-conversion/resources/requirements.txt

# image-local-replacer：图片局部替换
pip install -r skills/image-local-replacer/resources/requirements.txt

```

如果只使用不依赖脚本的纯文本流程，可以不安装 Python 依赖；一旦需要运行转换器、Anki 导出或图片局部替换脚本，就需要安装对应技能的 `requirements.txt`。

`epub-translator` 的脚本只使用 Python 标准库，不需要安装第三方依赖。

### Option C — Skill marketplace

本仓库提供 `.claude-plugin/marketplace.json`，可通过 Claude Code plugin marketplace 生态安装技能文件。

```bash
# Cross-agent CLI（Claude Code、Cursor、Codex 等支持 skills 的环境）
npx skills add hugohe3/hugo-skills
```

Claude Code 内也可以使用：

```bash
/plugin marketplace add hugohe3/hugo-skills
/plugin install hugo-skills@hugo-skills
```

说明：

- `/plugin marketplace add` 和 `/plugin install` 是 Claude Code 专用命令。
- `npx skills add ...` 是更通用的 skills 安装入口，适合支持该 CLI 的 agent 环境。
- marketplace / CLI 安装通常只获取 skill 文件，不等于安装 Python 依赖；如需运行脚本，仍需在安装后的技能目录中执行对应的 `pip install -r .../resources/requirements.txt`。
- 当前 marketplace 不写固定版本号；Git 托管安装时由 commit SHA 识别版本，适合持续迭代阶段。需要稳定发布时，再引入显式版本号和 Git tag。

## 使用

将需要的 `SKILL.md` 添加到支持 skills 的平台或 agent 配置中。推荐按文件路径引用整个技能入口，并保留同级 `scripts/`、`templates/`、`resources/` 等资源目录。

常用入口：

```text
/path/to/hugo-skills/skills/markdown-conversion/SKILL.md
/path/to/hugo-skills/skills/learning-master/SKILL.md
/path/to/hugo-skills/skills/epub-translator/SKILL.md
/path/to/hugo-skills/skills/image-local-replacer/SKILL.md
/path/to/hugo-skills/skills/structured-problem-solving/SKILL.md
```

### Claude Code 手动配置

在任意 Claude Code 项目的 `.claude/settings.json` 中引用技能：

```json
{
  "skills": [
    {
      "type": "file",
      "path": "/path/to/hugo-skills/skills/markdown-conversion/SKILL.md"
    },
    {
      "type": "file",
      "path": "/path/to/hugo-skills/skills/learning-master/SKILL.md"
    },
    {
      "type": "file",
      "path": "/path/to/hugo-skills/skills/epub-translator/SKILL.md"
    },
    {
      "type": "file",
      "path": "/path/to/hugo-skills/skills/image-local-replacer/SKILL.md"
    },
    {
      "type": "file",
      "path": "/path/to/hugo-skills/skills/structured-problem-solving/SKILL.md"
    }
  ]
}
```

也可以通过 Claude Code CLI 添加本地技能：

```bash
claude skills add /path/to/hugo-skills/skills/markdown-conversion/SKILL.md
claude skills add /path/to/hugo-skills/skills/learning-master/SKILL.md
claude skills add /path/to/hugo-skills/skills/epub-translator/SKILL.md
claude skills add /path/to/hugo-skills/skills/image-local-replacer/SKILL.md
claude skills add /path/to/hugo-skills/skills/structured-problem-solving/SKILL.md
```

添加后，支持 skills 的 agent 会在你要求转换文档、管理系统化学习项目、处理图片局部替换或结构化分析问题时自动调用相应技能。

## 仓库结构

```
skills/
  learning-master/
    SKILL.md              # 技能入口——agent 读取此文件
    scripts/              # Anki 卡片导出脚本
    templates/            # 六阶段学习模板
    resources/            # requirements.txt
  markdown-conversion/
    SKILL.md              # 技能入口——agent 读取此文件
    scripts/              # Python 转换器（每种格式一个）
    resources/            # requirements.txt、config.example.json
  epub-translator/
    SKILL.md              # 技能入口——agent 读取此文件
    scripts/              # EPUB 拆分与重打包脚本
  image-local-replacer/
    SKILL.md              # 技能入口——agent 读取此文件
    scripts/              # 位图局部替换脚本
    resources/            # requirements.txt
  structured-problem-solving/
    SKILL.md              # 技能入口——agent 读取此文件
    agents/               # UI 元数据
```

## 贡献

欢迎提交 Bug 报告和 Pull Request。
