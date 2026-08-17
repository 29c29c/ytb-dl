# yt-dlp 频道 / 播放列表下载器

一个面向 Windows 10/11 的 PySide6 桌面 GUI。输入 YouTube 频道或播放列表网址后，它会渐进显示视频名称、上传者、上传日期和链接，并允许搜索、批量勾选、选择格式后顺序下载。

> 请只下载你有权保存的内容，并遵守 YouTube 服务条款、内容授权和所在地法律。

## 功能

- 渐进扫描频道和播放列表；大型频道无需等待全部完成才看到结果，并在后台按扫描时的格式规则补充预期文件大小。
- 对标题、上传者、日期、链接进行即时搜索；全选和取消只作用于当前过滤结果。
- 支持 Chrome / Edge / Firefox 浏览器 Cookie，不保存或导出 Cookie 内容。
- 支持最佳质量、分辨率上限、编码偏好、MP4/MKV/WebM、纯音频、字幕和高级 yt-dlp 格式表达式。
- 可按视频查看全部格式，选择单一复合格式或组合视频流与纯音频流。
- 单任务顺序队列、进度/速度/ETA、暂停后续任务、取消当前任务、失败重试和 `.part` 续传。
- SQLite 保存成功下载历史；已下载项默认不会被批量重新勾选。

## Windows 安装

1. 安装 64 位 [Python 3.11](https://www.python.org/downloads/windows/)（最低 3.10），安装时勾选加入 `PATH`。
2. 安装 [ffmpeg/ffprobe](https://github.com/yt-dlp/FFmpeg-Builds) 并将其 `bin` 目录加入 `PATH`。
3. 安装 [Deno](https://docs.deno.com/runtime/getting_started/installation/) 并确保 `deno --version` 可用。yt-dlp 使用 Deno 和 `yt-dlp-ejs` 处理 YouTube JavaScript 挑战。
4. 在 PowerShell 中进入项目目录并运行：

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\setup.ps1
   .\run.ps1
   ```

调试时使用 `.\run-debug.ps1`，错误会直接显示在终端。应用内的“帮助 → 环境诊断”会检查 Python 包和外部程序。

## 使用

1. 粘贴完整频道网址（如 `/@handle/videos`、`/channel/...`）或播放列表网址，然后点击“开始扫描”。单视频网址会被拒绝。
2. 会员、年龄限制等内容可在“登录态”选择 Chrome、Edge 或 Firefox。配置栏可填写 Profile 名称或目录；读取失败时先关闭对应浏览器再重试。Windows 上 Chrome/Edge 的加密 Cookie 无法解密时，优先使用 Firefox。
3. 在搜索框输入关键词，用“勾选匹配”或“全选当前结果”选中当前可见项。
4. 设置保存目录和全局格式。需要单独覆盖时，选中表格行后点击“所选视频格式”。
5. 点击“下载已勾选项目”。暂停只会阻止下一项启动，不会挂起当前文件写入；取消会尽量保留 `.part` 文件。

默认路径模板为：

```text
<下载目录>/<上传者>/<上传日期> - <标题> [视频ID].<扩展名>
```

文件名最终由 yt-dlp 按 Windows 规则清理。上传日期来自 yt-dlp 的 UTC 元数据；无法取得时显示“未知”。

## 更新与故障排查

YouTube 会频繁改变页面和提取逻辑。扫描突然失效时，先更新 yt-dlp：

```powershell
.\.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]"
```

- “需要登录或 Cookie 已失效”：确认浏览器中已登录，选择正确 Profile；关闭浏览器后重试。
- “缺少 ffmpeg”：确认 `ffmpeg -version` 和 `ffprobe -version` 在新 PowerShell 窗口中可用。
- “缺少 Deno 或 yt-dlp-ejs”：重新运行 `setup.ps1`，并确认 `deno --version` 可用。
- “格式不可用”：恢复全局“最佳视频 + 音频”，或重新获取该视频的格式列表。
- 地区限制、私密、删除和账号权限问题不能由应用绕过。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall -q src
```

核心模块位于 `src/ytb_gui`：数据模型、yt-dlp 后端、后台工作线程、SQLite 历史、Qt 表格模型和界面相互分离。联网集成测试默认关闭，可通过环境变量显式提供测试频道或播放列表。

技术依据：[yt-dlp 官方 README（嵌入 API、依赖、格式选择）](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)。PySide6 使用 LGPLv3/GPL/商业三许可；yt-dlp 及其依赖保留各自许可证。
