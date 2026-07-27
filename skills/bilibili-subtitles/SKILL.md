---
name: bilibili-subtitles
description: >
  获取哔哩哔哩（B站）单个视频、多个 BV 号或指定 UP 主空间的公开字幕轨道，
  转换为 SRT，并保存到 PPT Master 的 projects 目录。支持 Bilibili 官方二维码登录、
  UP 主视频列表分页、并发下载、多 P 视频和无字幕清单。当用户要求“下载 B 站字幕”
  “提取 UP 主全部视频字幕”“批量导出 Bilibili AI 字幕”“把字幕保存到 projects”时使用。
---

# Bilibili 字幕下载

使用 `scripts/download.py` 调用 Bilibili 公开页面与播放器接口，下载已有字幕轨道。不要下载视频或用语音识别补造字幕。

## 快速开始

输出默认写入自动定位到的 PPT Master `projects/`：

```bash
# UP 主全部公开视频
python3 skills/bilibili-subtitles/scripts/download.py --mid 351608062 --zip

# 空间 URL
python3 skills/bilibili-subtitles/scripts/download.py \
  --space-url "https://space.bilibili.com/351608062"

# 一个或多个视频
python3 skills/bilibili-subtitles/scripts/download.py \
  --bvid BV16c3u6XEni BV1wo3M64EdV

# 已准备好的 JSON 视频清单
python3 skills/bilibili-subtitles/scripts/download.py \
  --video-list /path/to/videos.json
```

没有传入 `--cookie-file` 时，脚本生成 Bilibili 官方登录二维码并打印 `QR_CODE:` 路径。向用户展示该图片，等待用户在哔哩哔哩 App 确认；不要读取 Chrome Cookie、浏览器配置或会话存储。

如已有用户明确提供的 Netscape Cookie 文件，可传入：

```bash
python3 skills/bilibili-subtitles/scripts/download.py \
  --mid 351608062 \
  --cookie-file /path/to/cookies.txt
```

## 输出

默认项目目录：

```text
projects/bilibili-subtitles-<mid-or-bvid>/
  subtitles/                 # SRT 文件，文件名包含序号与 BV 号
  no-subtitle-videos.csv     # 没有公开字幕轨道的视频
  failed-videos.csv          # 请求或解析失败的视频（仅失败时生成）
  <project-name>.zip         # 仅传入 --zip 时生成
```

脚本按以下顺序定位 PPT Master：`--ppt-master-root`、`PPT_MASTER_ROOT`
环境变量、当前工作目录、`hugo-skills` 的同级目录。无法定位时停止并要求显式指定，
不要回退到 `hugo-skills/projects/`。

使用 `--output` 可以直接指定其它项目目录。字幕和清单属于本地项目材料；不要把登录 Cookie 写入项目或提交到 Git。

## 执行规则

1. 优先使用 `--mid` 或 `--space-url` 自动分页获取该 UP 主的视频清单。
2. 需要登录时使用脚本的官方二维码流程；二维码过期后重新运行。
3. 使用默认并发数 `8`；遇到限流时降低 `--concurrency`，不要增加浏览器视频标签页。
4. 保留 Bilibili 返回的时间轴和文字，不改写、不总结字幕正文。
5. 完成后核对脚本汇总、SRT 文件数量和 `failed-videos.csv`；无字幕不算下载失败。
6. 对已有项目重复运行时默认复用有效 SRT；只有用户明确要求刷新时传入 `--overwrite`。

## 依赖

```bash
pip install -r skills/bilibili-subtitles/resources/requirements.txt
```

除二维码图片生成外，其余功能只使用 Python 标准库。
