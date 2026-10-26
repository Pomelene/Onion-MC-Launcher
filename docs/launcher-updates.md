# 启动器更新

公众版与 THUnion 版从独立公开仓库的 `updates.json` 获取版本信息：

`https://github.com/Pomelene/OnionService4THUnion/blob/main/updates.json`

每次启动 Windows EXE 后，默认在后台检查一次。网络失败、JSON 无效、没有当前系列更新时不显示提示。源码运行不自动检查；设置 → 启动器行为中可以关闭自动检查或手动检查。检查不使用游戏账号令牌，也不需要确认社团服务。

## 版本选择

- `series`: `public`（公众版）或 `thunion`（特供版）。特供版版本号以 `-T` 结尾。
- `version`: 界面显示版本，如 `0.3.3` / `0.3.3-T`。
- `order`: 每个系列独立递增的整数排序；不依赖字符串排序。
- `platform`: 当前支持 `windows-x64`。
- `url`: 对应 EXE 的 GitHub Release 下载地址，必须位于本启动器仓库。
- `size` / `sha256`: 实际 EXE 的字节数和 SHA256，均必填。
- `notes`: 可选纯文本更新说明。

客户端仅比较同系列的最大 `order`，必须严格大于本地 `LAUNCHER_UPDATE_ORDER` 且版本号不同时才提示，不根据其它系列切换，也不自动降序更新。

## 下载与替换

用户确认后才开始下载，并可取消。暂存目录为当前 EXE 同目录的 `.onion/updates/pending-*`。下载完成后检查文件大小、SHA256、PE 格式与 x64 架构；校验通过才保存设置并启动本机的隐藏更新辅助进程。

辅助进程等待原启动器退出，再次校验暂存文件，使用 Windows `File.Replace` 原子替换原路径下的 EXE，并从同一目录重新启动。EXE 文件名保持不变，`onionmcl.json`、账号数据和游戏目录不参与替换。杀毒软件短暂占用时有限重试；替换后新程序立即异常退出时尝试恢复旧程序。备份、失败记录都在 `.onion/updates` 内，成功记录在下次启动后清理。

公开元数据和更新下载支持代理失败后的直连尝试；HTTPS 验证保持开启。不对登录请求、上传或含账号凭据的请求添加自动直连重试。

## 发布新版本

1. 在两个分支分别修改 `launcher/paths.py` 的版本号和 `LAUNCHER_UPDATE_ORDER`，同步修改 Windows 版本资源。排序必须大于对应系列已发布版本；初始 `0.3.2` / `0.3.2-T` 的排序均为 `32`。
2. 完成测试、构建，并上传两个系列各自的 GitHub Release EXE。
3. 使用已上传 EXE 的真实字节数、SHA256 和下载链接更新独立仓库的 `updates.json`。同系列可只保留最新版，也可保留历史记录；排序不能重复。
4. 最后推送数据库。不要先公布尚未上传的下载地址或临时占位摘要。

现有 v0.3.2 EXE 本身没有更新器，第一次启用本功能仍需用户手动下载包含此功能的新版。之后可通过数据库推送后续版本。

## 验证

- `tests/test_launcher_updates.py`: 系列、排序、远端 JSON、下载校验、取消、路径与缓存回归。
- `scripts/check_qt_updates.py`: 静默失败、确认、繁忙延后、设置保存、取消和交接测试。
- `scripts/check_update_replacement.py`: Windows 上运行临时无窗口测试程序，实际验证原子替换、特殊字符路径、损坏拒绝及启动失败回退；不构建或更新真实启动器。

本实现参考 HMCL 的公开更新流程，代码独立编写，没有复制其 Java 实现。
