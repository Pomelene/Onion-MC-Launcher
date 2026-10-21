# 开发与打包

项目目前面向 Windows、Python 3.13 和 PySide6 6.12。其他环境尚未充分验收。

## 源码结构

| 位置 | 内容 |
| --- | --- |
| `launcher/qtui/` | 当前 Qt 界面、后台任务及账号交互 |
| `launcher/auth/` | 微软与外置认证 |
| `launcher/install/` | 原版及加载器安装 |
| `launcher/` | 游戏库、下载、实例、模组、整合包、存档及恢复 |
| `launcher/ui/`、`main_tk.py` | 保留的历史 Tk 界面 |
| `tests/` | 模拟网络与临时目录的回归测试 |
| `scripts/` | 构建、检查及显式验收工具 |
| `packaging/` | PyInstaller 配置与 Windows 产品信息 |

历史内部名 `craftbridge` 仍用于一些目录、图标文件名及脚本路径，以兼容已有实例与恢复记录，不代表另一个产品。

## Qt 界面结构

左侧导航集中提供账户、当前实例管理、实例列表、下载与通用设置。
首页使用可自定义的本地背景，右下角的分体按钮负责启动游戏和快捷选择实例。
实例列表使用紧凑表格，支持搜索、类型筛选、排序和右键管理。
`workspace.py` 将游戏设置、模组、资源包、光影、世界、日志和维护工具绑定到同一个实例。
`settings.py` 共用全局与实例编辑器，修改保留为草稿，保存后才写入配置。
实例默认跟随全局游戏设置，开启“实例特定游戏设置”后才使用独立配置。
`installer.py` 提供版本列表、正式版 / 快照筛选与加载器选择。
自动内存分配在启动配置解析时计算，保留用户原有的手动内存设置。

交互结构参考 HMCL 与美西螈，Qt 控件、图标和首页矢量背景由本项目实现。
视觉采用深色 Liquid Glass：窗口内部的青紫光晕、半透明导航与连续设置面板、渐变主操作按钮。
背景按窗口尺寸绘制，不采集桌面；导航悬停使用 450ms 缓动，静止时不运行背景动画。
实例管理、下载和全局设置使用各自的上下文导航。设置仍以紧凑、可读的连续行呈现。
模组、资源包和光影使用 64 逻辑像素高的连续双行列表，显示已有元数据、文件名和大小，支持本地过滤。
安装、账户管理、微软授权与任务进度嵌入主窗口子界面；返回登录上一级时会取消授权轮询。
微软账户密码仍在系统浏览器的官方授权页面输入。
内容列表按显示名称排序（忽略大小写，同名按文件名），从有大小限制的归档条目读取图标，缺少有效图片时显示类型图标。
模组启用/禁用在原列表行内更新，保留滚动与搜索状态；失败恢复勾选状态。
下载及启动任务在主窗口底部持续显示当前阶段和真实计数进度，可跨页面查看与取消；无确定总量时显示忙碌状态。

## 测试

先创建 `tmp` 和 `docs/screens` 目录，再运行：

```powershell
python -X utf8 tests/run_all.py
python -X utf8 scripts/check_qt_ui.py
```

Qt 检查使用 offscreen 平台及临时实例，不操作桌面、不发起真实授权。部分后端测试会绑定本机回环端口。`tests/stress.py` 和 `scripts/validate_*.py` 等属于独立验收工具，运行前应检查其目标目录和外部网络操作；它们不是普通单元测试入口。

验收报告和本机截图默认不提交。提交新的公共文档需要在 `.gitignore` 中明确允许对应路径。

## Windows 构建

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install --target .deps/qt PySide6-Essentials==6.12.0
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_qt.ps1
```

构建脚本隔离原生 DLL 搜索路径，并运行打包后的 offscreen 自检。产物为 `dist/OnionMinecraftLauncher.exe`，运行数据和玩家账号配置不会打入 EXE。依赖不从开发者本机复制到仓库。

微软应用配置使用 `assets/microsoft-app.example.json` 模板；维护者实际配置保存在被 Git 忽略的 `assets/microsoft-app.json`。详细说明见 [微软登录](microsoft-auth.md)。
