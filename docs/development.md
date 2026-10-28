# 开发与打包

项目目前面向 Windows、Python 3.13 和 PySide6 6.12。其他环境尚未充分验收。

Qt 发行包采用有界的无损分组压缩。`packaging/qt_payload.py` 在构建时处理随附依赖，
`packaging/qt_unpack.py` 在加载 Qt 前流式恢复并校验 SHA-256；语言包和备用插件全部保留。
设置环境变量 `ONION_PACK_QT=0` 可以构建普通 PyInstaller 对照包。不要对启用 CFG 的 DLL 强行使用 UPX。

性能复算：`python scripts/benchmark_optimizations.py --baseline e219ced --output docs/performance-20261028.json`。
该工具使用隔离的合成文件、本地回环下载和固定延迟模拟服务，并比较本机 Java 枚举结果；不会修改用户游戏数据。
远程请求减少量与真实公网下载带宽应分别报告。

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
`settings.py` 共用全局与实例编辑器，修改通过校验后自动写入配置。
实例默认跟随全局游戏设置，开启“实例特定游戏设置”后才使用独立配置。
`installer.py` 提供版本列表、正式版 / 快照筛选与加载器选择。
自动内存分配在启动配置解析时计算，保留用户原有的手动内存设置。

交互结构参考 HMCL 与美西螈，Qt 控件、图标和首页矢量背景由本项目实现。
视觉采用深色 Liquid Glass：窗口内部的青紫光晕、半透明导航与连续设置面板、渐变主操作按钮。
背景按窗口尺寸绘制，不采集桌面；导航悬停使用 150ms 缓动，静止时不运行背景动画。
实例管理、下载和全局设置使用各自的上下文导航。设置仍以紧凑、可读的连续行呈现。
模组、资源包和光影使用 64 逻辑像素高的连续双行列表，显示已有元数据、文件名和大小，支持本地过滤。
安装、账户管理、微软授权与任务进度嵌入主窗口子界面；返回登录上一级时会取消授权轮询。
微软账户密码仍在系统浏览器的官方授权页面输入。
内容列表按显示名称排序（忽略大小写，同名按文件名），从有大小限制的归档条目读取图标，缺少有效图片时显示类型图标。
模组启用/禁用在原列表行内更新，保留滚动与搜索状态；失败恢复勾选状态。
下载及启动任务在主窗口底部持续显示当前阶段和真实计数进度，可跨页面查看与取消；无确定总量时显示忙碌状态。
设置行中的可编辑数值、下拉值和操作文字靠右显示，并使用可在“外观”中设置的特征色；禁用控件及说明文字保持灰色。
新安装实例默认展示名称为“Minecraft 版本号-加载器”，可在安装前编辑，实例列表提供重命名入口（仅更改元数据）。
下载中心使用紧凑项目行与主窗口内版本表，显式选择的模组版本会在安装时再次检查兼容性。
游戏安装页列出 Fabric、Quilt、Forge、NeoForge 与 OptiFine 的适用版本；加载器选择与 Minecraft 版本联动，忽略过期查询结果。
第一轮布局调整使用固定品牌区和页面路径；下载分类由侧栏统一控制，安装目标与搜索筛选固定在结果列表上方。
`browser.py` 按分类保留搜索结果、页码及滚动位置，主窗口返回历史支持恢复来源页面；搜索请求使用序号避免旧结果覆盖新结果。

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

构建脚本隔离原生 DLL 搜索路径，并运行打包后的 offscreen 自检。通过自检后的最终产物为 `release/OnionMinecraftLauncher.exe`（`dist/qt/` 仅作构建暂存），运行数据和玩家账号配置不会打入 EXE。依赖不从开发者本机复制到仓库。

构建还会运行 Windows 原生平台的隐藏窗口光栅检查和 `scripts/check_bundle.py` 的依赖体积审计，全部通过后才复制最终 EXE。Windows 检查不显示窗口，不启动游戏，仅使用临时配置。`-OutputName` 可以指定新文件名，避免覆盖正在运行的程序。

微软应用配置使用 `assets/microsoft-app.example.json` 模板；维护者实际配置保存在被 Git 忽略的 `assets/microsoft-app.json`。详细说明见 [微软登录](microsoft-auth.md)。

## 发行体积审计

Qt 发行版自带 Python 解释器、Qt 动态库和 Python 绑定。不能只把 EXE 大小与依赖外部 Java 环境的启动器等同比较；参见 [HMCL 的 Java 下载说明](https://docs.hmcl.net/downloads/)。我们的界面代码本身并非主要占用。

以已发布 v0.2.1 为基线，精简构建的 EXE 从 45,338,417 字节减少到 30,530,304 字节，减少 14,808,113 字节（32.66%）；归档内文件的未压缩合计从 108,865,213 字节降到 75,446,006 字节。下表按 EXE 内的实际压缩体积统计，MB 使用十进制：

| 构成 | 原构建 MB | 精简构建 MB |
| --- | ---: | ---: |
| Qt 运行库与绑定 | 16.75 | 16.75 |
| 软件 OpenGL 实现 | 7.66 | 0 |
| Pillow 原生编解码器 | 5.69 | 0 |
| Python 模块（含原来的 Pillow 模块及测试工具） | 3.81 | 2.42 |
| Python 解释器及基础库 | 2.95 | 2.95 |
| Qt 插件（20 个） | 2.45 | 2.45 |
| Qt 多语言文件（99 个） | 2.01 | 2.01 |

`packaging/craftbridge.spec` 不再强制导入 PIL，并明确排除未用于 Qt 产品的 Pillow 与 unittest；Pillow 移至开发依赖，继续支持开发截图及历史验收工具。冻结自检使用局部替换来阻止真实登录请求，不再引入整个 unittest 工具包。

只过滤 `opengl32sw.dll`：该文件是软件 OpenGL 实现，当前产品没有 QOpenGLWidget、Qt Quick 或其他 OpenGL 表面，所有绘制使用 QPainter 的 QWidget/QImage 光栅路径。构建后的隐藏 Windows 窗口必须报告 `RasterSurface`，并实际绘制首页、实例列表和设置页。以后若新增 OpenGL/Quick 功能，需重新评估此裁剪。所有原有 Qt 语言文件与插件继续打包，包括备用平台、TLS、触摸及全部图片编解码插件。

冻结自检验证 PNG、JPEG、WebP、TIFF、SVG、GIF、ICO 读取，Python TLS 上下文和随机数接口、微软登录入口（模拟应用配置）、设置保存及便携存储。它不发起真实账号授权或游戏启动。未使用 UPX，也未启用会删除 assert 检查的 Python 优化级别。

审计命令：

```powershell
python -X utf8 scripts/check_bundle.py release/OnionMinecraftLauncher-v0.2.1-slim.exe --baseline release/OnionMinecraftLauncher-v0.2.1.exe --require-slim --output tmp/size-comparison.json
```

审计检查必要运行库及插件仍存在、未重新引入 PIL/unittest、配置等个人文件未进入归档，并在提供基线时断言所有原有语言文件和插件都保留。构建当前使用 38,000,000 字节的 EXE 体积上限，防止依赖悄然膨胀；新增必要功能导致超限时应先审计再调整。审计报告默认保存在被 Git 忽略的 `docs/bundle-audit.json`。


## UI 外观调整

`launcher/qtui/chrome.py` 为主窗口提供客户区内标题栏、最小化/最大化/关闭及八方向缩放边缘；移动与缩放交给 Qt 的 `startSystemMove/startSystemResize`。启动器独立 Qt 对话框在原布局顶部预留标题栏空间，保留消息框等控件对内部布局的所有权。文件打开、保存与文件夹选择使用系统原生弹窗，不参与自绘标题栏处理，也不强制关闭原生对话框；颜色选择器继续使用统一外观的 Qt 版本。嵌入主窗口的子页面不显示第二条标题栏，快捷菜单和弹出选择器维持原交互。

`SettingsEditor` 使用 450ms 单次定时器自动保存，通过校验后才写入。切换实例、启动、离开页面及退出时刷新待保存值；文件操作进行中延后重试。无效输入保留在编辑器并显示原因，不覆盖最后一次有效配置。仅实际修改网络/目录时重建仓库对象，仅修改特征色时刷新样式，避免普通保存引发页面闪烁。

实例编辑器的独立开关对应当前版本 ID 的覆盖项。未勾选时禁用整块设置及其说明文字，显示全局值与前往全局设置的入口。开启时从当前继承值创建局部快照；关闭时只清空当前 ID 的覆盖项。全局变更刷新继承状态的编辑器，已独立的实例不受影响。Java 管理只保留设置侧栏统一入口，选择运行时同步更新缓存中的全局编辑器，避免后续自动保存写回旧值。

`python -X utf8 scripts/check_qt_settings.py` 使用临时统一存储检查两个实例的覆盖、清除、全局变更与重启恢复，以及自动保存/校验/任务延后、标题栏操作、Qt 标准对话框返回值和嵌入页面。生成本地截图用于静态外观检查；离屏测试不证明 Windows 原生贴靠或实际显示器表现。

`launcher/qtui/theme.py` 集中维护基础配色、字体、控件和表面样式；`widgets.py` 维护原生绘制的导航、图标、开关和内容行。用户配置的特征色通过 `themed_style()` 应用到主要操作与设置值，绘制控件通过 `control_accent()` 读取。装饰背景不采集桌面，也不使用持续模糊刷新。

外观设置集中于“设置 → 外观”，使用 `color_mode`（dark/light）、`text_transparency`（0–70）、`ui_transparency`（0–90）、`background_transparency`（0–100）与 `background_mode`。透明度数值越高越淡，0 为不透明。UI 透明度通过 `WA_TranslucentBackground` 与逐像素 Alpha 控制整个窗口底图、面板、按钮和列表背景，能透出桌面或其他窗口；不调用整窗 `setWindowOpacity`，文字保持独立，由文字透明度控制。主窗口与启动器自绘对话框均采用此模式；系统文件选择器保持原生。最高 90%，避免完全隐藏非文字控件。背景图层先缓存合成，再统一施加 UI Alpha，避免底图、图片与遮罩多次叠加导致透明度失真；缓存键覆盖分辨率、DPI、主题、图片、显示模式和背景透明度。文字透明度上限保留基本可读性；无效配置在读取或绘制时回退到安全范围。

`theme.py` 的语义调色板同时供样式表和自绘控件使用，导航、列表文字、图标和开关跟随深浅模式。浅色模式下特征色的文字版本会调整对比度，主操作底色保留用户选色。外观变更只更新样式和绘制，不重建当前页面；图片路径未变时不会重新解码背景。外观设置沿用自动保存，重启后恢复。

首页背景支持五种模式：填充按比例铺满并裁切、自适应完整显示并留边、拉伸铺满、原始大小居中、平铺。小图片不再被预先放大；大图仍限制解码尺寸以控制内存。平铺通过缓存的 Qt 纹理画刷完成，避免对很小的图片运行大量 Python 绘制循环。背景透明度作用于图片及首页装饰层，首页文字和按钮独立绘制。文件选择继续使用系统弹窗。

`python -X utf8 scripts/check_qt_appearance.py` 检查双主题、透明度独立性、填充几何、平铺像素、图片原始尺寸、自动保存和重启恢复，并断言设置页对象和布局位置不变；只使用临时图片和配置。冻结自检及 Windows 隐藏窗口自检也绘制深浅两种模式。

首页隐藏左上的返回首页和页面标题，右侧保留 Onion 与版本号；其他页面恢复返回首页、页面标题和逐级返回，首页打开的内嵌子页面同样提供返回入口。内容行高为 68px，设置行最小高为 58px，开关滑动时间为 200ms。布局与导航验收使用 `scripts/check_qt_ui.py`，只操作临时实例。


## 界面动效

背景范围在“设置 → 外观 → 首页背景”中选择，配置键 `background_scope` 默认为 `content`（仅主页内容区），`window` 表示整个窗口（包括导航栏、标题栏及其他页面底层）。切换通过自动保存立即应用，不重建当前设置页。两种范围均由 `GlassBackdrop` 统一合成底图、图片和装饰，再一次性应用 UI Alpha；`HomeCanvas` 只容纳前景，不再挖空父背景或单独覆盖一层半透明图片。填充、自适应、拉伸、居中和平铺仍共享同一范围坐标系。图片只解码一份；导航栏和标题栏通过半透明底色保持文字可读，UI 透明度同时影响底色和全局背景层，背景透明度额外控制图片与装饰的显示强度。恢复内容区范围时恢复原导航栏底色与边界。

`scripts/check_qt_background_scope.py` 使用临时渐变图片与临时配置，逐像素检查五种图片模式在侧栏/内容区边界上的连续性，以及设置页身份、缓存、深浅模式、透明度、自动保存、重启恢复与非法值回退。

页面没有统一动画包装器、截图覆盖、透明度或位移。重复进入当前路由不重新构建页面；同组导航复用按钮，刷新列表等明确操作使用 `navigate(..., force=True)`。

`launcher/qtui/motion.py` 中 `NavigationSurface` 在侧栏背景层绘制单个胶囊；`SelectionRail` 保存浮点矩形，前缘以 150ms、贝塞尔曲线 `(0.4,0,0.2,1)` 移动，尾缘延迟 120ms 跟随。首次显示及尺寸校准直接定位；反向切换从当前可见形状续接；相同目标不重启动画。图标、文字和命中区域固定，不存在额外的选中行底色或亮度过渡。

按钮只在绘制层缩放到 0.97，150ms；悬停反馈 140ms。开关局部位移、颜色和滑块尺寸以 200ms 变化；模型状态与点击回调立即生效。界面动效关闭时直接显示终态。

检查：`python -X utf8 scripts/check_qt_motion.py`，使用临时实例与模拟搜索。检查页面坐标固定、侧栏控件身份不变、同页点击保持搜索/滚动/焦点、胶囊拉伸/收拢及反向连续性、输入不会引起跳位、显式刷新仍生效、关闭动效清理、按钮点击与开关状态。另采集真实事件循环中的形状状态到 `tmp/capsule-motion-samples.json`，不把离屏采样当成显示器帧率测量。

页面内容过渡留待单独原型验收；当前交付不包含全局页面淡入或滑动。完整审计在本地 `docs/ui-motion-audit.md`，不随构建打包。


## 统一便携存储

程序同目录的 `onionmcl.json` 使用版本化 JSON：`format_version`、`settings`、`accounts`、`instances`、`version_settings`。Windows 下由文件属性隐藏，文件名本身不以点开头。隐藏属性用于整洁显示；账号访问令牌、续期令牌及外置登录令牌继续由 Windows DPAPI 加密，CurseForge 私有 Key 同样加密。

`launcher/storage.py` 为四个模型提供分区读写；更新时在路径锁内重新读取整个文档，只替换自己的分区，保留其他分区。Windows 使用命名互斥量协调多个进程，临时文件 flush/fsync 后以 ReplaceFileW 原子替换，短暂文件占用时重试，不以删除原文件作为回退。隐藏属性在临时文件上设置，以便替换后保留。测试覆盖重复保存后的隐藏属性和多进程写入。

第一次创建新文件时读取同目录 `config/settings.json`、`accounts.json`、`instances.json`、`version_settings.json`。先收集所有旧文件，再加密旧明文凭据并一次性提交。旧文件不删除、不改写；新文件已经存在后不再从旧数据导入，避免已删除的账号复活。损坏 JSON 或不支持的版本会停止加载，保留原文件。迁移原件仍可能包含旧明文信息，应按个人数据管理。

显式传入旧文件路径的测试和兼容调用仍支持原有独立 JSON；Qt、旧 Tk 入口及默认 CLI 使用统一文件。实例隔离读取也使用统一的 `version_settings` 分区。临时缓存、日志、游戏内容及 Java 运行时不放进该 JSON。

`release/` 和所有 `onionmcl.json` 均被 Git 忽略，不打入 EXE。构建脚本先在 `dist/qt/` 暂存并完成离屏自检，再将 EXE 放入 `release/`。自检使用临时统一数据文件，不读取开发者账号或游戏库。


`scripts/check_qt_transparency.py` 检查 UI 90% 时首页背景像素约 10% 不透明、文字仍有完全不透明像素、文字透明度单独生效、背景范围切换、主题切换、恢复默认、对话框和原生文件选择器。加 `--native` 使用 Windows 原生 QPA 和隐藏窗口验证 Alpha 表面，检查不显示任何桌面窗口。


## 透明度输入、缩放与快捷实例弹层

三个透明度设置均使用同一行内的滑条和百分比数值框，双向联动，步进为 1%。滑条键盘方向键微调，数值框支持直接输入。参考本地 HMCL 的 `PersonalizationPage.java` 百分比滑条及 `GameSettingsPage.java` 的滑条与数字输入布局；未复制 Java 控件代码。预览按 33ms 合并更新，持续拖动也能预览；持久化沿用 450ms 自动保存，预览值不写入配置数据。数值与预览都使用 `1 - 百分比 / 100`，文字只受文字透明度控制，不改变整窗 `windowOpacity`。

“下载与网络”的并发下载数同样提供 1–32 的滑条和数字框，单位“个”。下载限速保留精确数值输入，单位 `KiB/s`。数字框只显示数字，零值旁边单独提示“不限速”；单位固定显示在框外，不依赖悬停。不更改已有的限速算法或配置单位。内存输入标明 `MiB`，游戏窗口宽高标明 `px`。输入单位不参与保存的整数值。

旧绘制路径在父窗口上裁空主页区域，再由子控件单独画半透明背景；新路径改为根背景单层合成。缓存缓冲区在缩小时复用容量，重新绘制前清空，避免反复分配及旧像素残留。`ChromeMainWindow` 在缩放/布局结束后合并一次全区域更新，包含缩小，不在 resize 回调里同步 repaint。`InlineSpinBox` 的编辑区位置只在尺寸或样式变化时更新，绘制过程不再修改几何，避免绘制/布局反馈。

快捷实例选择器为 400px 宽的圆角弹层，按行数调整高度，最多 460px，并限制在屏幕可用区域。单列 64px 双行项目显示实例名、版本标识、加载器和分组，长文本省略且可悬停查看完整标识；保留当前实例标记、字典序、搜索空态、方向键/Enter、单击选择与管理实例入口。选择仅更新实例，不启动游戏。

`python -X utf8 scripts/check_qt_polish.py` 覆盖 0/1/2/5/10/50/90% 实际 Alpha、滑条拖动及数字输入、增长/缩小后的几何与绘制收敛、缓存容量复用、首页导航可见性以及实例弹层。加 `--native` 使用隐藏的 Windows 原生窗口，不干扰桌面。隐藏窗口测试用于验证绘制与事件收敛，不能当作显示器上的逐帧拖动测量。Qt 对透明窗口和双缓冲的说明见 [QWidget 文档](https://doc.qt.io/qt-6/qwidget.html#transparency-and-double-buffering)。

## 统一选择控件与文字粗体

`launcher/qtui/choices.py` 为设置、安装、下载等页面提供共享的圆角下拉弹层和菜单。保留 QComboBox 数据模型、选项数据、禁用状态与选择信号；当前项带勾选标记，超过 12 项显示搜索，支持方向键、Enter、Escape，并限制在屏幕可用区域内。原生系统文件选择器保持不变。

设置行统一左右内边距和控件基线；路径及长文本输入自适应扩展，路径最小宽度 360px，动作文字靠右显示。数字框与单位分离，滑条、数值和单位在同一行对齐。首页的 Onion 与版本移到左上，离开首页及打开子页面后回到右上。

“设置 → 外观 → 粗体文字”通过 `bold_text` 保存，默认关闭。开启后立即更新文字，包括导航、下拉列表、实例选择器和启动按钮的自绘文字；关闭后恢复原有的标题与正文层级。沿用外观预览合并与自动保存，不改变文字透明度。

`scripts/check_qt_choices.py` 使用临时配置检查下拉模型/信号/搜索/禁用项/键盘、深浅主题弹层透明边角、1100/1440 窗口路径宽度、数值框外单位、粗体即时生效及重启恢复、主页与子页面品牌位置。

## 自绘颜色选择器

`launcher/qtui/color_picker.py` 替换外观设置中的标准 QColorDialog：540px 宽的紧凑无边框面板、HSV 色板、水平色相条、常用色、原色/新色预览及 HEX/RGB 双向输入。色板采用白色到纯色横向渐变叠加透明到黑色纵向渐变；所有取色坐标约束在有效区域，按下与拖动只更新本地选择，不修改全局主题。HEX 校验失败时禁止应用；点击原色恢复初始值，取消不保存，仅确认后交给现有设置自动保存。保留深浅主题、文字粗体和独立透明度模型。支持色板方向键/Shift 加速与色相条键盘调整，不新增页面动画。

`scripts/check_qt_color_picker.py` 使用临时配置验证 HSV 交互、无彩色色相保留、HEX/RGB 同步与错误处理、预设/恢复、真实设置入口的确认/取消与保存，以及深浅主题下的无边框布局；构建自检包含新模块导入与绘制。

## 隐藏的启动器日志目录

启动器自身日志统一通过 `launcher.paths.default_log_dir()` 写入程序目录的 `.onion/logs/launcher.log`。Qt 与历史 Tk 入口均使用这个默认路径。Windows 会设置 `.onion` 的隐藏属性，每次初始化也会修复已有目录的属性；设置和账号仍使用原来的 `onionmcl.json`。日志仍按天轮转并保留 7 份备份，游戏日志位置不变。

首次初始化时，只迁移旧 `logs/` 内的 `launcher.log` 和 `launcher.log.YYYY-MM-DD`。文件归档到独立创建的 `.onion/logs/legacy-*` 目录，避免覆盖新日志或先前迁移内容；不跟随旧日志目录的符号链接/目录联接，不移动文件链接。被占用、无权访问的文件保留并记录警告；仅用非递归 `rmdir` 清理空目录，其他文件、子目录均保留。隐藏属性设置失败时继续记录日志，不阻断启动。

`tests/test_logging.py` 使用临时目录验证默认位置、Windows 隐藏属性、轮转与重复初始化、旧日志归档、目标冲突、未知文件、锁定文件、链接跳过及显式目录兼容。打包自检额外验证冻结 EXE 的日志写入位置和隐藏属性，不读取真实旧日志。

## 原理图、截图与工具坊（开发预览）

- `launcher/file_library.py` 与 `launcher/qtui/file_library.py`：按实际实例运行目录管理 `schematics/` 和 `screenshots/`。不跟随链接或越出根目录；支持原理图子目录、导入、文件夹创建、重命名及恢复区移除/撤销。原理图保留分页；截图优先使用标准文件名的拍摄时间，其他名称使用文件修改时间，倒序连续显示。`launcher/qtui/screenshot_gallery.py` 使用 QListView 模型和委托绘制自适应网格，全部条目可连续滚动；只在可见区域及相邻行按批次解码缩略图，缓存按视口限制容量，避免创建成千上万个子控件或全量加载图片。文件导入使用排他创建，避免覆盖原文件。
- `launcher/skins.py`：皮肤文件存放于 `.onion/skins/`，按内容哈希区分同名导入，账户 UUID 对应文件名及模型选择保存在其中的 `selections.json`。皮肤限制为最多 1 MiB 的 64×64 或 64×32 PNG。`launcher/qtui/skin_preview.py` 在 Qt raster 上将纹理投影到六个长方体与外层，不依赖浏览器、WebGL 或新的图形运行时；拖动旋转，双击复位。
- 正版皮肤上传使用已有账户续期机制与固定 Minecraft HTTPS multipart 端点，只有用户点击上传按钮才执行，错误信息不包含响应体或令牌。离线选择通过 `launcher/offline_skin.py` 的回环服务器及已固定校验的 authlib-injector 在启动时接入：只提供当前账户的签名纹理档案，绑定 127.0.0.1、随机端口与随机路径，临时 RSA 密钥只在内存中，游戏退出后停止。不会上传离线皮肤，也不提供 Mojang 身份验证能力。
- `launcher/seedmap.py` 调用随包附带的 `assets/native/onion_seedmap.dll`，本地生成生物群系图和结构预测，明确列出支持版本（最高 26.3）、维度及高度。支持拖动平移、滚轮缩放、悬停坐标/生物群系、读取存档种子；文本种子遵循 Java UTF-16 String.hashCode。结构有地形条件限制，每次视野最多返回 512 个标记。引擎升级为 xpple/cubiomes 的固定提交，包含 1.21.5、26.2、26.3 的真实生物群系树和颜色、新版末地规则及废弃营地；Python 适配层检查引擎版本，防止新版界面误配旧 DLL。负数高度采样向下取整。
- 未修改的 MIT cubiomes 源码及许可证位于 `launcher/native/cubiomes/`，提交号记于 `UPSTREAM.txt`；自有 ABI 包装为 `launcher/native/seedmap.c`。重建命令：`python -m pip install --target .deps/buildtools ziglang==0.16.0` 后运行 `python scripts/build_seedmap.py`。现有 DLL 已随源码提供，因此一般 Qt 构建不需要安装 C 编译器。

`tests/test_workshop.py` 覆盖路径边界、导入冲突、恢复、截图排序、账户隔离、上传 multipart、离线端点与 RSA 签名，以及真实 cubiomes 已知种子的结果。`scripts/check_qt_workshop.py` 使用一次性实例和合成图片验证新页面、子目录、分页、选择皮肤、地图平移及深浅主题多尺寸渲染。真实账户上传和离线游戏内显示需另行人工验收，自动检查不执行真实账号修改或游戏启动。

## 种子地图交互重构（开发预览）

参考 Axolotl `Mystic-Stars/Axolotl` 提交 `3d5d0b07b2d53534d206b42d40f85d283b751f4c` 的 `apps/app-frontend/src/pages/LabSeedMap.vue`、`lab/seed-map/tile-layer.ts`、`marker-rendering.ts`：借鉴地图优先布局、光标锚定缩放、连续平移、分层瓦片缓存及结构详情的交互路径。未复制 GPL 源码或图像；Onion 以 Python/Qt 独立实现，不引入浏览器运行时。

- `launcher/map_view.py` 负责浮点世界坐标投影、缩放锚点和矩形视口瓦片规划。瓦片按世界网格对齐、中心优先；原生采样层级为 1/4/16/64/256，单次计划最多 48 块。负坐标始终向下取整，避免跨原点接缝。
- `launcher/qtui/seed_map.py` 使用全区域地图、紧凑坐标工具栏及可折叠结构图层。鼠标移动直接改变视口；缩放对每像素方块数的 log2 值做 200ms OutCubic 插值，每帧保持鼠标下的世界坐标不变。缓存图片通过世界投影重画，不改变窗口透明度或布局；遵循关闭动效设置。
- 平移防抖 130ms 后后台补瓦片；最多两个地形任务并行。先以 64 像素和四倍采样间隔覆盖同一区域，再补 256 像素细节；最粗层不再生成预览。缓存使用 QImage 和 16 位生物群系数组，总预算 32 MiB。切换种子/版本/维度/高度递增 epoch，旧结果丢弃；移动视口会丢弃未开始的旧任务计划。结构查询独立执行，筛选不触发地形重算。
- 生物群系采用自然配色及中文名称。结构标记以颜色、简称及放大后的全称区分；单击显示详情、复制坐标/传送命令，右键可直接复制当前位置。附网格、北向及动态比例尺。结构视野过大时提示放大，并暂时隐藏结构；每次查询最多 512 个预测位置，不代表所有地形条件已验证。默认不展示数量密集的试炼密室和废弃营地，可在图层中开启。
- `tests/test_map_view.py` 验证锚点、矩形覆盖、负坐标、全部声明版本和维度的新采样层级，以及 block 采样高度与原生单点的一致性。Qt 工作坊检查还验证松开前即时平移、单调多帧缩放、锚点不漂移、筛选不重算、坐标复制、过期结果丢弃、缓存预算及深浅主题 1100/1440/1920 宽度布局。

## 多游戏目录与内嵌 Java 管理（开发预览）

实例列表使用 HMCL 类似的上下文侧栏：左侧保存游戏文件夹，右侧显示当前目录的实例。可添加、设置显示名称、从列表移除；移除不会删除或移动磁盘文件。首页快捷实例选择器也提供文件夹选择。目录按规范化绝对路径区分，重复路径合并；每个目录保存自己的上次实例。目录离线时仍保留记录，不会清空其上次选择。

`launcher/game_libraries.py` 维护 settings 内的 `game_libraries`（path/name/selected_version）及 `library_legacy_root`。`launcher/qtui/library_actions.py` 将仓库、实例元数据、独立设置及页面上下文一起切换，安装或启动准备期间暂缓切换；版本扫描沿用仓库身份检查，旧扫描不覆盖新目录。切换不影响已运行的游戏，退出统计仍写回启动时的目录；先重新加载该目录元数据，保留切走期间修改的实例名称。

`onionmcl.json` 格式升级至 2，可读取并在保存时升级格式 1，旧记录与加密账户分区保留。升级前先将原文件的完整字节保存在隐藏的 `.onion/backups/onionmcl-format1-<摘要>.json`；备份失败则不替换旧配置。实例元数据和独立设置在各自分区的 `__directories__` 中按规范化目录分组；旧扁平记录只对首次迁移时的当前游戏目录生效，不套用到其他目录。空的目录级覆盖明确表示恢复全局设置，不会重新启用旧覆盖。目录级写入复用同一路径锁、跨进程互斥及原子替换，只替换目标目录的数据。旧版程序因不支持格式 2 会拒绝读取，避免将目录结构扁平化而破坏数据；回退旧版时可从上述备份恢复 onionmcl.json 或使用独立目录。

`launcher/qtui/java_manager.py` 是设置中的普通 QWidget 页，不再使用 Java 管理 QDialog。首次进入后台检测，支持重新检测、系统文件选择器添加、全局 Java 选择/恢复自动选择。Java 下载在本页显示进度、失败和取消状态，不切入任务子页；扫描和下载互斥，下载成功刷新列表并保存所选运行时。实例级 Java 设置仍在各实例独立设置内管理。

`tests/test_game_libraries.py` 验证旧格式保留、同名实例隔离、目录去重与选择恢复、移除不删除文件、并发目录写入及实际运行路径。`scripts/check_qt_libraries_java.py` 使用临时双目录、模拟 Java 和模拟游戏进程，验证真实页面按钮、重启恢复、任务切换保护、运行中切目录后的统计归属、全局设置目录入口、Java 内嵌状态与下载成功/失败/取消；生成深浅主题多尺寸截图。不会运行真实游戏、Java 或进行真实下载。

## THUnion 特供版：社团服务

独立分支 `for_thunion`，当前版本 `0.3.0-T`，Windows 数字版本为 0.3.0.0，文件和产品版本字符串包含 `-T`。公众版 main 不含社团服务入口。

工具坊新增“社团服务”。首次进入显示与主题一致的无边框确认面板；取消不请求目录。每次启动仅在首次确认后通过 GitHub Contents API 同步一次 main/webapp.json，校验后原子写入 `.onion/services/thunion/webapp.json`。会话状态归主窗口持有，重建页面、切换工具或离开时正在同步均不重复确认/下载；后续进入读取本地 JSON。同步失败保留并使用上次有效缓存，无缓存则显示失败；下次启动重新确认并同步。请求不带微软令牌、Cookie 或 GitHub 凭据，使用唯一 freshness 参数及 no-cache。

配置为 schema_version=1 的声明式目录，只读取 title/categories/id/description/tools/url；最多 256 KiB、24 个分类、128 个工具。目录和工具必须说明用途；页面先展示说明与网址，用户点击打开才导航。配置不能下发命令、脚本或本地路径。网页入口支持公共 HTTP(S)，拒绝 file/javascript/data、内嵌凭据、本机和显式内网地址。实验 Wiki 和在线地图实际提供 HTTP：Wiki 跳转到维护者站点，地图使用指向维护者地图的 frame。配置本身始终通过 GitHub HTTPS 获取。

`launcher/qtui/web_tools.py` 用 Qt 6.12 QWebView（QWindow）及 QWidget.createWindowContainer 承载系统 WebView2；地址只读、提供后退/刷新/停止/回到目录和加载状态。无 Python/系统命令桥接，不将启动器账户令牌或客户端配置传给网页；禁用本地文件访问。网页浏览资料目录独立于启动器账户，位于 `.onion/webview/thunion`。原生窗口不能用 Qt raster 抓取网页，验证采用真实 DOM 与 WebGL 查询。

源码运行可安装 requirements-thunion.txt。隔离打包运行 scripts/install_webview.py，只从固定 SHA-256 的官方 PySide6-Addons wheel 提取约 320 KiB 绑定和 WebView2 插件，不引入 WebEngine/完整 Chromium。构建增加隐藏原生窗口 WebView2 DOM 检查，失败时不覆盖 release EXE。

tests/test_club_services.py 检查目录格式、网址、请求刷新与无令牌，以及拒绝可执行配置。scripts/check_qt_club_services.py 验证确认/取消、每次启动确认及同步一次、本地缓存与离线回退、说明先于跳转、两个网页的内嵌路由及失败状态；scripts/check_thunion_native_web.py 从已推送的真实 JSON 读取两个服务，在隐藏原生 WebView2 内检查导航、DOM 和 WebGL，不使用账户或桌面输入。


社团网页统一使用紧凑单行工具栏；成功加载时隐藏状态行和进度条。打开网页默认收起主侧栏，移除工具坊外边距、社团目录标题和说明栏，将空间留给网页。可通过“显示导航 / 展开网页”切换；返回目录或切到其他工具恢复侧栏和边距。在线地图目录增加 THUnion Atlas（https://atlas.thunion.net/），入口说明其站内提供离线导航模组下载。


社团服务接口 v2：兼容 v1，目录和条目的数量、顺序由 categories/tools 数组决定；支持默认栏目、visible、icon、show_urls、cards/list 布局及 button_text/badge。web/external/copy/download 操作由严格枚举分派，未知字段不执行；仅允许 HTTPS、256 MiB 以内、固定文件名与 SHA-256 的 mrpack 下载，存放 .onion/downloads，显式导入前再次校验。独立仓库 API.md 和 webapp.schema.json 定义完整协议。部员分享置顶，包含基础包、Atlas 指引和作者项目链接。


## Local appearance preview (2026-10-25)

- Color generation uses a small, independent Oklab/Oklch implementation in `launcher/qtui/color_science.py`. References: [Oklab](https://bottosson.github.io/posts/oklab/), [Material extraction pipeline](https://github.com/material-foundation/material-color-utilities/blob/main/concepts/color_extraction.md). The six styles express similar visual directions, not exact HCT/Material replicas.
- Wallpaper extraction decodes at most a 64×64 sample, bins into at most 512 RGB cells, scores population and perceptual chroma, ignores transparent/near-black/near-white candidates, and falls back to purple. Cache: 4 path/mtime entries; palette cache: 96 entries. No new runtime package, bundled font or remote service.
- Base text, secondary text and actionable foreground target >=4.5:1 against their generated surface. User-selected text/background transparency can reduce the final contrast; a translucent surface over an arbitrary wallpaper cannot promise a fixed final contrast.
- Blur uses existing Qt Widgets' native blur filter on a bounded working image, then caches the result. It applies only to wallpaper, never to text/controls, and is not desktop/acrylic blur. Original image is retained for color extraction and zero-blur restoration. UI, text and wallpaper opacity remain independent.
- Font family, interface size (12–18 logical px), log family/size, antialiasing preference, system light/dark following, titlebar transparency, relative control corner scale (0–24), background blur (0–40), animation duration (0–600 ms) share automatic saving, live previews and default reset.
- System appearance uses Qt `QStyleHints.colorSchemeChanged`; antialiasing remains subject to Qt, font and display/platform capabilities. Reduced motion or duration 0 settles animations immediately.
- Main and for_thunion are built separately. Preserve the THUnion-only WebView entry initialization and service navigation; never replace app.py wholesale across editions.
- Checks: tests/test_color_science.py, scripts/check_qt_appearance_next.py, scripts/check_qt_wallpaper_opacity.py, scripts/check_qt_choices.py, scripts/check_qt_motion.py, existing background/transparency checks, and each frozen build's real-entry startup/raster/edition-specific checks.


### Exact opacity encoding and incremental updates

Qt QSS interprets `rgba(r,g,b,1)` as fully opaque, not 1/255. A 7/255 hover overlay scaled by 21% rounded to integer 1, reproducing the sudden white setting-row highlight at 79% UI transparency. All generated style colors now use Qt-native `#AARRGGBB` through `launcher/qtui/opacity.py`, avoiding both that ambiguity and fractional-alpha truncation. Ratios are clamped once and byte alpha is quantized only at the renderer boundary; authored byte-alpha tokens are parsed explicitly.

Opaque style templates are cached separately from UI/text opacity (24 bounded entries). Alpha-only changes do not reload fonts, change density/layout, reset animations or recolor icons. Wallpaper alpha changes reuse the painted wallpaper layer without decoding or filtering it again. The system uses one snapshot to skip unchanged appearance applications. `scripts/check_qt_opacity_boundary.py` proves the old Qt behavior, checks 182 actual dark/light alpha renders including 78→79%, and checks image/cache/font/geometry stability. No EXE is rebuilt or uploaded as part of this source-only correction.


### Wallpaper source switching and popup sizing

Choice popups measure actual delegate row heights, including font size, instead of multiplying a fixed 42 px. Short lists show all rows when screen space permits; long lists retain scrolling to the selected row. This fixes clipped source choices after selecting wallpaper colors.

Appearance settings show the extracted wallpaper seed and final scheme color, explicitly report default-purple fallback for unreadable/achromatic wallpaper, disable the inactive manual seed editor without deleting its saved value, and allow an accepted color-picker selection to switch back to custom. Wallpaper content is not recolored; very transparent UI fills make the theme change less prominent. `scripts/check_qt_wallpaper_source.py` tests 24 actual-click source round trips across font sizes, distinct wallpaper hues, manual-value preservation, picker recovery and missing/grayscale wallpaper fallback. This correction is source-only until another local build is requested.


### Background picker callback binding regression

The appearance preview subscription loop reused the constructor-local `field` variable captured by the picture-picker and reset closures. Depending on hash iteration order, button callbacks targeted an unrelated field, sometimes a spin box without `setText`. Both callbacks now capture their intended background editor explicitly; the subscription loop has a separate local name. `scripts/check_qt_background_picker.py` clicks the actual buttons with only the OS file dialog mocked, checks unrelated fields, cancellation, default reset, Unicode paths, persistence, home and restart, and is run with multiple `PYTHONHASHSEED` values. Frozen self-checks also exercise these actual button callbacks. Real user preferences are never used in these checks.


## Interaction reliability pass

Unfocused choice boxes, numeric editors and settings sliders leave wheel events to their surrounding scroll area. Explicitly focused editors retain keyboard and wheel input. Catalog version refresh disables installation while pending, preserves the selected release ID when it remains present, and restores retry controls after failure. Closed catalog pages do not start a delayed fetch; completed callbacks do not touch closed pages. Compatibility and missing-file guards apply both to buttons and direct install calls.

The instance library exposes a clear-search action, complete cell tooltips, and disables selection-dependent actions when no row is available. `python scripts/check_qt_usability.py` covers wheel/keyboard behavior, refresh success/failure/close, release selection preservation, incompatible or empty releases, and empty/filtered instance lists using isolated fixtures.
