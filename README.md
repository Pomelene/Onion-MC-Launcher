# Onion MC Launcher

**免费、开源、公益开发的 Minecraft Java 版启动器。**

本地开发版本：**v0.2.2（暂未发布）**。已发布版本：[v0.2.1](https://github.com/Pomelene/Onion-MC-Launcher/releases/tag/v0.2.1)。Windows 用户可下载 Release 中的 ZIP，解压后运行。

v0.2.2 正在优化发行体积，并增加深色／浅色、文字与面板透明度、首页背景透明度和图片显示方式设置。精简构建保留全部多国语言文件与 Qt 插件，并增加打包依赖审计和隐藏窗口绘制检查。

程序显示名称为 **Onion Minecraft Launcher**。项目使用 Python 和 PySide6 / Qt，致力于提供简洁的实例管理、游戏安装及内容管理体验，不以售卖启动器、账号或游戏资源为开发目的。欢迎学习、反馈和贡献。

本项目代码采用 [MIT License](LICENSE)。公益定位不增加许可证之外的使用限制。本项目是独立社区项目，与 Mojang、Microsoft 或其他启动器没有隶属关系。

## 功能概览

- Qt 界面、实例选择、后台下载任务、取消及日志显示。
- 原版及 Fabric、Quilt、Forge、NeoForge、OptiFine 安装流程。
- 模组、资源包、光影、Modrinth / CurseForge 整合包管理。
- 存档备份、恢复及可恢复的文件移除机制。
- 账号管理、离线身份、外置认证及微软账号授权流程。
- 独立实例设置、Java 选择和启动参数管理。
- 设置自动保存、恢复上次选择的实例；主窗口与独立对话框统一使用深色自绘标题栏。

账号授权与发布者应用配置见 [微软登录说明](docs/microsoft-auth.md)。

## 从源码运行

当前主要开发环境：Windows、Python 3.13。

```powershell
git clone https://github.com/Pomelene/Onion-MC-Launcher.git
cd Onion-MC-Launcher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

当前默认游戏目录为 `F:\.minecraft`，可在设置中修改为自己的游戏目录。设置、账户资料、实例名称和独立设置统一保存在程序同目录的 `onionmcl.json`，Windows 下自动设为隐藏文件；账号令牌继续使用 Windows 用户级加密。首次运行会迁移同目录旧 `config/` 中的四份配置，原文件保留。游戏、存档、Java 和日志仍独立存放。

后续构建的 EXE 输出到项目根目录 `release/`。只复制 EXE 到新目录且不携带 `onionmcl.json` 时，会使用默认配置；需要保留设置时应连同该隐藏文件一起备份。

设置修改后会自动保存，无需点击保存按钮。实例默认跟随“设置 → 全局游戏设置”，下方以灰色展示继承值；勾选“仅为当前实例启用独立设置”后，修改只对该实例生效，不影响全局配置或其他实例。取消勾选会清除当前实例的覆盖项并恢复跟随全局。Java 检测与下载统一位于设置侧栏的“Java 管理”，游戏设置中的“Java 路径”用于指定所用运行时。

仓库不包含 Minecraft 游戏文件、Java 运行时、账号、访问令牌或开发者本机配置。游戏使用权与第三方内容许可需要用户自行合法取得；开源许可证不提供游戏授权。

## 测试与打包

```powershell
New-Item -ItemType Directory -Force tmp,docs/screens
python -X utf8 tests/run_all.py
python -X utf8 scripts/check_qt_ui.py
```

Windows 打包、目录结构及依赖说明见 [开发文档](docs/development.md)。微软发布配置仅提供空白模板，不包含开发者的应用配置和认证数据。

## 开源与贡献

- 本项目以免费、开源、公益为开发定位，代码可按 MIT 许可证使用与修改。
- 欢迎提交 Issue 和 Pull Request，参见 [贡献指南](CONTRIBUTING.md)。
- HMCL、PCL、美西螈等项目用于功能流程和交互参考，详见 [第三方说明](THIRD_PARTY_NOTICES.md)。
- 不要在 Issue、Pull Request 或提交记录中上传账号、密码、令牌、私有配置或未脱敏日志。
