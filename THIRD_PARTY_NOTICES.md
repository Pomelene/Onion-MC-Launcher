# 第三方项目与依赖

Onion MC Launcher 是独立的 Python / Qt 启动器项目，与 Mojang、Microsoft、HMCL、PCL、Axolotl、美西螈或 PrismarineJS 没有隶属或背书关系。

开发过程中参考以下项目公开的功能流程、界面交互及认证协议实现。仓库不包含这些项目的完整源码、发布包、专有凭据或应用身份：

- [HMCL](https://github.com/HMCL-dev/HMCL)：实例管理和认证流程参考；上游使用 GPL-3.0。
- [PCL](https://github.com/Hex-Dragon/PCL)：启动器交互和认证流程参考；使用或再分发其代码时应遵循上游当前许可证。
- [Axolotl](https://github.com/Mystic-Stars/Axolotl)：认证流程及种子地图交互参考；前端上游使用 GPL-3.0。地图的瓦片、缩放和标记交互由 Onion 在 Python/Qt 中独立实现，未复制其源代码或图像；使用上游代码时仍须逐项核对适用许可证。
- [prismarine-auth](https://github.com/PrismarineJS/prismarine-auth)：Microsoft / Xbox / Minecraft 认证流程参考；上游使用 MIT。

本项目自己的代码按根目录 MIT LICENSE 发布；该许可证不改变任何第三方代码、商标或服务的权利。

## 随附的本地种子地图组件

- [cubiomes](https://github.com/Cubitect/cubiomes) 及其 [xpple 维护分支](https://github.com/xpple/cubiomes)：MIT License，Copyright (c) 2020 Cubitect。
  未修改的上游 C 源码和数据表位于 `launcher/native/cubiomes/`，提交号记于其中的 `UPSTREAM.txt`。
  Onion 自行编写的 ABI 包装位于 `launcher/native/seedmap.c`，Windows DLL 位于 `assets/native/onion_seedmap.dll`。
  发行 EXE 同时包含上游许可证。地图支持范围以工具坊中的版本列表为准，结构定位不代替游戏内实际生成校验。

运行与开发依赖由安装工具另行获取，不随源码仓库附带：

- PySide6 / Qt：遵循对应版本的 LGPL/GPL/商业许可及分发要求。
- Pillow：开发截图和历史验收工具使用，遵循 HPND 等上游适用许可；当前 Qt 发行 EXE 不包含此依赖。
- PyInstaller：遵循上游 GPL 及其引导程序分发例外。

本项目不提供 Minecraft 游戏文件、模组再分发授权或微软应用访问资格。公开仓库不包含开发者本机字体、Java 运行时或账号数据。
