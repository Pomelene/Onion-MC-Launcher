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

构建脚本隔离原生 DLL 搜索路径，并运行打包后的 offscreen 自检。产物为 `dist/OnionMinecraftLauncher.exe`，源码、运行数据和账号配置不会打入 EXE。依赖不从开发者本机复制到仓库。

微软应用配置使用 `assets/microsoft-app.example.json` 模板；维护者实际配置保存在被 Git 忽略的 `assets/microsoft-app.json`。详细说明见 [微软登录](microsoft-auth.md)。
