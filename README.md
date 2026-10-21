# Onion MC Launcher

**免费、开源、公益开发的 Minecraft Java 版启动器。**

程序显示名称为 **Onion Minecraft Launcher**。项目使用 Python 和 PySide6 / Qt，致力于提供简洁的实例管理、游戏安装及内容管理体验，不以售卖启动器、账号或游戏资源为开发目的。欢迎学习、反馈和贡献。

本项目代码采用 [MIT License](LICENSE)。公益定位不增加许可证之外的使用限制。本项目是独立社区项目，与 Mojang、Microsoft 或其他启动器没有隶属关系。

## 功能概览

- Qt 界面、实例选择、后台下载任务、取消及日志显示。
- 原版及 Fabric、Quilt、Forge、NeoForge、OptiFine 安装流程。
- 模组、资源包、光影、Modrinth / CurseForge 整合包管理。
- 存档备份、恢复及可恢复的文件移除机制。
- 账号管理、离线身份、外置认证及微软账号授权流程。
- 独立实例设置、Java 选择和启动参数管理。

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

当前默认游戏目录为 `F:\.minecraft`，可在设置中修改为自己的游戏目录。账号与设置保存在程序旁的 `config/`；请先确认目录及备份，再对已有游戏库进行文件管理操作。

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
