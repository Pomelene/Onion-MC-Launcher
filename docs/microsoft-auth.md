# 微软正版登录

玩家使用内置应用身份，在微软官方网页完成授权。普通玩家不需要了解或填写 client_id；该配置应由启动器发布者一次完成。

## 发布者配置

1. 在 Microsoft Entra 为自己的启动器注册个人 Microsoft 账号公共客户端应用。
2. 开启并保存“允许公共客户端流”。设备码流程不需要重定向 URI，也不使用 client_secret。
3. 使用 `python scripts/configure_microsoft_app.py YOUR_APPLICATION_ID` 写入本地发布配置，再构建 EXE。
4. 真实验证 Microsoft → Xbox Live → XSTS → Minecraft 令牌交换 → Java 玩家档案及续期。

应用 ID 是公开应用标识，但本仓库仍只提供空白模板，不发布维护者本机配置、账号数据或令牌。Fork 和自行发布的版本应使用自己的应用身份。

## 应用访问资格

新应用应核查 Minecraft API 访问资格。认证库文档列出了申请入口 https://aka.ms/mce-reviewappid 。HTTP 403 的具体原因需要结合服务响应判断，不能全部归因为访问名单。更换认证库不会自动赋予应用访问资格。

临时网络错误会在设备码有效期内退避重试，继续使用同一个设备码。取消、拒绝和过期会结束会话；错误信息不回显原始认证响应。

## 参考

- https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app
- https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration
- https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code
- https://minecraft-launcher-lib.readthedocs.io/en/stable/tutorial/microsoft_login.html
- https://github.com/PrismarineJS/prismarine-auth
