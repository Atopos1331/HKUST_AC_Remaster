# 配置指南

本文档覆盖三部分：

1. Microsoft Authenticator 配置与 `microsoft_secret` 获取
2. QQ bot 申请与接入
3. Discord bot 申请与接入

## 1. Microsoft Authenticator 配置

目标：获取 `creds.json` 或 `creds/credentials.json` 中需要的 `microsoft_secret`。

步骤：

1. 如果你还没有启用 Microsoft Authenticator，或者学校账号仍绑定在 Duo Security，先进入 <https://mfa-enroll.hkust.edu.hk/> 完成迁移/激活。
2. 进入 Microsoft 安全信息页面：<https://mysignins.microsoft.com/security-info>
3. 添加登录方法：
   `Add sign-in method` -> `Microsoft Authenticator` -> `I want to use a different authenticator app` / `Set up a different authenticator app` -> `Next` -> `Can't scan image?`
4. 页面会显示一段手动设置密钥。复制这段密钥，它就是项目中需要的 `microsoft_secret`。
5. 在手机端 Microsoft Authenticator 中添加账户：
   右上角 `+` -> `Other account` -> `Enter code manually`
6. 账户名称可以随意填写，但密钥必须准确粘贴。
7. 如果你更习惯其他 TOTP 应用，也可以把同一个密钥导入其他 authenticator。
8. 成功导入后，你会看到一个实时刷新的 6 位验证码。本项目登录时会用这个密钥自动生成验证码。
9. 如果你在 Microsoft 安全信息页面里配置了除电话和刚添加的 authenticator 之外的其他验证方式，建议删掉，避免登录流程被系统切换到别的方式。

建议在凭据文件里这样填写：

```json
{
  "email": "yourname@connect.ust.hk",
  "password": "your_password_here",
  "microsoft_secret": "YOUR_BASE32_SECRET"
}
```

排错建议：

- 如果程序提示 2FA 失败，优先检查 `microsoft_secret` 是否复制完整。
- 再检查手机端和电脑端时间是否准确。
- 如果学校账户策略变了，先在网页里手动登录一次确认当前默认 MFA 流程。

## 2. QQ bot 申请与接入

本项目需要的是 QQ 开放平台机器人的 `AppID` 和 `AppSecret`。

### 你需要准备

- 一个可登录 QQ 开放平台的 QQ 账号
- 机器人应用的 `AppID`
- 机器人应用的 `AppSecret`

### 申请步骤

1. 打开 QQ 开放平台：<https://q.qq.com/>
2. 使用 QQ 账号登录，并完成开发者认证。
3. 在平台里创建机器人应用。
4. 创建完成后，进入开发设置页，记录 `AppID` 和 `AppSecret`。
5. 按你实际使用场景打开本项目需要的消息能力，配置好指令列表。
6. 将获得的值写入：

```json
{
  "qq_app_id": "your_qq_app_id",
  "qq_secret": "your_qq_secret"
}
```

### 和本项目的对应关系

- `qq_app_id` -> `Bot.APPID`
- `qq_secret` -> `Bot.SECRET`
- 代码入口：`powers/qq_bot.py`

### 参考来源

- QQ 开放平台首页：<https://q.qq.com/>
- 第三方文档对控制台字段的整理，可用于辅助定位 `AppID` / `AppSecret` 和消息权限：<https://docs.astrbot.app/deploy/platform/qqofficial/webhook.html>

说明：腾讯官方控制台是重前端页面，公开可抓取文本有限；上面的接入步骤是基于官方平台入口和当前生态文档做的保守整理。

## 3. Discord bot 申请与接入

本项目需要的是 Discord bot token。代码同时支持 slash commands，也能响应以 `/` 开头的普通文本消息。

### 申请步骤

1. 打开 Discord Developer Portal：<https://discord.com/developers/applications>
2. 点击 `New Application` 创建一个应用。
3. 在左侧进入 `Bot` 页面，然后点击 `Add Bot`。
4. 在 `Bot` 页面里重置或复制 token，并写入：

```json
{
  "discord_token": "your_discord_bot_token"
}
```

5. 进入 `OAuth2` -> `URL Generator`：
   - Scopes 选择 `bot` 和 `applications.commands`
   - Bot Permissions 选择项目真正需要的最小权限，例如发送消息、附加文件、读取消息历史
6. 用生成的邀请链接把 bot 拉进你的服务器。
7. 首次启动后，项目会自动同步 slash commands。

### 和本项目的对应关系

- `discord_token` -> `Bot.DISCORD_TOKEN`
- 代码入口：`powers/discord_bot.py`
- slash commands 在 bot ready 后自动 `sync`

### 参考来源

- Discord Developer Portal：<https://discord.com/developers/applications>
- Discord.py intents 说明：<https://discordpy.readthedocs.io/en/stable/intents.html>

## 4. 推荐的凭据文件

```json
{
  "email": "yourname@connect.ust.hk",
  "password": "your_password_here",
  "microsoft_secret": "YOUR_BASE32_SECRET",
  "qq_app_id": "your_qq_app_id",
  "qq_secret": "your_qq_secret",
  "discord_token": "your_discord_bot_token",
  "command_language": "zh"
}
```
