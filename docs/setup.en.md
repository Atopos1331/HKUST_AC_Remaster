# Setup Guide

This guide covers:

1. Microsoft Authenticator setup and how to obtain `microsoft_secret`
2. QQ bot application and integration
3. Discord bot application and integration

## 1. Microsoft Authenticator Setup

Goal: obtain the `microsoft_secret` value required by `creds.json` or `creds/credentials.json`.

Steps:

1. If Microsoft Authenticator is not enabled yet, or your HKUST account is still using Duo Security, go to <https://mfa-enroll.hkust.edu.hk/> and complete the migration / activation flow first.
2. Open the Microsoft security info page: <https://mysignins.microsoft.com/security-info>
3. Add a sign-in method:
   `Add sign-in method` -> `Microsoft Authenticator` -> `I want to use a different authenticator app` / `Set up a different authenticator app` -> `Next` -> `Can't scan image?`
4. The page will display a manual setup key. Copy that key. This is the `microsoft_secret` used by the project.
5. On your phone, open Microsoft Authenticator and add an account:
   top-right `+` -> `Other account` -> `Enter code manually`
6. The account name can be anything, but the key must be pasted exactly.
7. You can also import the same key into another TOTP authenticator if you prefer.
8. Once imported, you should see a rotating 6-digit code. The project uses the shared secret to generate that code automatically during login.
9. If your Microsoft security info page contains other sign-in methods besides phone and the authenticator you just set up, remove the extra methods to reduce the chance that the login flow falls back to a different challenge type.

Suggested credentials snippet:

```json
{
  "email": "yourname@connect.ust.hk",
  "password": "your_password_here",
  "microsoft_secret": "YOUR_BASE32_SECRET"
}
```

Troubleshooting:

- If the program reports a 2FA failure, first verify that `microsoft_secret` was copied completely.
- Then verify system time on both phone and PC.
- If HKUST changes the login policy, manually sign in through the browser once to confirm the current MFA path.

## 2. QQ Bot Application and Integration

This project needs the QQ Open Platform bot `AppID` and `AppSecret`.

### What you need

- A QQ account that can access the QQ Open Platform
- The bot app `AppID`
- The bot app `AppSecret`

### Application Steps

1. Open the QQ Open Platform: <https://q.qq.com/>
2. Sign in with your QQ account and complete developer verification.
3. Create a bot application in the platform console.
4. After the app is created, open the development settings page and record the `AppID` and `AppSecret`.
5. Set up the command list, ip whitelist and corresponding permissions for chats in the platform console.
6. Put the values into your credentials file:

```json
{
  "qq_app_id": "your_qq_app_id",
  "qq_secret": "your_qq_secret"
}
```

### Mapping to This Project

- `qq_app_id` -> `Bot.APPID`
- `qq_secret` -> `Bot.SECRET`
- Runtime entry: `powers/qq_bot.py`

### Sources

- QQ Open Platform homepage: <https://q.qq.com/>
- Third-party operational guide that matches current console labels for `AppID` / `AppSecret` and message permissions: <https://docs.astrbot.app/deploy/platform/qqofficial/webhook.html>

Note: Tencent's official console is heavily JavaScript-driven, so public text extraction is limited. The steps above are a conservative synthesis from the official platform entry point plus current ecosystem docs.

## 3. Discord Bot Application and Integration

This project needs a Discord bot token. The code supports both slash commands and plain text messages that start with `/`.

### Application Steps

1. Open the Discord Developer Portal: <https://discord.com/developers/applications>
2. Click `New Application` to create an application.
3. Open the `Bot` page in the left sidebar, then click `Add Bot`.
4. In the `Bot` page, reset or copy the bot token and store it as:

```json
{
  "discord_token": "your_discord_bot_token"
}
```

5. Open `OAuth2` -> `URL Generator`:
   - select the `bot` and `applications.commands` scopes
   - choose only the minimum bot permissions needed by this project, such as sending messages, attaching files, and reading message history
6. Use the generated invite link to add the bot to your server.
7. On first startup, the project syncs slash commands automatically.

### Mapping to This Project

- `discord_token` -> `Bot.DISCORD_TOKEN`
- Runtime entry: `powers/discord_bot.py`
- Slash commands are synced automatically in `on_ready`

### Sources

- Discord Developer Portal: <https://discord.com/developers/applications>
- Discord.py intents documentation: <https://discordpy.readthedocs.io/en/stable/intents.html>

## 4. Recommended Credentials File

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
