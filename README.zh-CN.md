# HKUST AC Remaster

HKUST AC Remaster 是一个面向 HKUST 宿舍空调的自动控制项目。它会登录学校预付费空调门户，读取室内环境数据，执行温控或定时控制逻辑，记录历史时序数据，并通过 QQ、Discord 与本地 CLI 提供控制入口。

## 主要功能

- 使用 Playwright + Microsoft TOTP 自动登录 HKUST 空调门户
- 通过可插拔的温湿度模块读取室内环境数据
- 支持温控模式与定时模式
- 使用 SQLite 记录历史数据，支持统计与绘图导出
- 提供 QQ bot、Discord bot 和本地 Textual 控制台

## 截图

### `controll_cli.py` 交互界面

![CLI Screenshot](docs/images/cli-zh.jpg)

### `analyse.py` 分析输出

![Analysis Screenshot](docs/images/analysis.png)

### Bot 指令示例

![Bot Screenshot](docs/images/bot-discord-zh.jpg)

## 项目结构

```text
controll.py        主运行入口
run_forever.py     自动重启包装脚本，适合长期运行
controll_cli.py    本地 Textual 控制台
analyse.py         分析 CLI / shell
powers/
  auth/            HKUST 登录与空调 API 客户端
  data/            状态、设置、记录器、分析
  io/              室内传感器驱动
  services/        控制逻辑
  qq_bot.py        QQ bot 接入
  discord_bot.py   Discord bot 接入
  utils/           配置与日志
docs/              中英文配置与说明文档
```

## 环境要求

- Python 3.10+
- Windows、Linux 或 macOS
- 可访问 HKUST 空调门户的网络环境
- 可用的 Microsoft Authenticator 兼容 TOTP
- 已执行 `playwright install chromium`
- 可选：如果你想接真实温湿度设备，需要自己的本地驱动
- 可选：QQ bot 与 Discord bot 的开发者凭据

说明：

- 这个项目本身不是 Windows 专用。
- 仓库里的 `start.bat`、`debug.bat` 只是给 Windows 用户准备的便捷脚本。
- 如果你的本地传感器实现依赖串口、USB、GPIO 或 BLE，具体设备权限要求取决于你的驱动实现，而不是这个项目本身。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 凭据配置

程序会按顺序查找：

- `creds.json`
- `creds/credentials.json`

先从模板复制：

```bash
cp creds/credentials.example.json creds/credentials.json
```

Windows PowerShell：

```powershell
Copy-Item creds/credentials.example.json creds/credentials.json
```

示例：

```json
{
  "email": "yourname@connect.ust.hk",
  "password": "your_password_here",
  "microsoft_secret": "BASE32_SECRET_FROM_MICROSOFT_AUTHENTICATOR",
  "qq_app_id": "your_qq_app_id",
  "qq_secret": "your_qq_secret",
  "discord_token": "your_discord_bot_token",
  "command_language": "zh"
}
```

## 运行方式

推荐长期运行方式：

```bash
python run_forever.py
```

`run_forever.py` 会启动 `controll_cli.py`。如果主进程因为临时网络异常、登录失败、bot 连接中断或其他运行时错误退出，它会等待一小段时间后自动重新拉起，适合后台长期运行，减少掉线后的人工重启。

常用参数：

```bash
python run_forever.py --delay 10
python run_forever.py --max-restarts 3
python run_forever.py -- python controll.py
```

直接单次运行主程序：

```bash
python controll.py
```

本地控制台：

```bash
python controll_cli.py
```

分析 shell：

```bash
python analyse.py
```

## Bot 开关

`controll.py` 顶部有两个直接开关：

```python
ENABLE_QQ_BOT = True
ENABLE_DISCORD_BOT = True
```

## 传感器逻辑

项目自带默认温湿度模块，即使没有真实硬件也能跑完整控制流程。

相关入口：

- 抽象接口：`powers/io/thermometer.py`
- 默认实现：`powers/io/default_thermometer.py`
- 本地覆盖示例：`powers/io/local_thermometer.example.py`

如果你要接真实设备，创建 `powers/io/local_thermometer.py` 并实现 `Thermometer` 接口即可，系统会优先使用你的本地实现。

## 详细控制策略

详细的控制策略、冷却时间、定时模式、临时锁定、设备侧关机保护以及运行拓扑说明：

- [docs/control-strategy.zh-CN.md](docs/control-strategy.zh-CN.md)

## 控制命令

QQ、Discord 和本地 CLI 共用同一套命令处理器。常用命令：

- `/state`
- `/scheduler`
- `/timer`
- `/lock`
- `/log`
- `/stats <range>`
- `/plot <range>`
- `/settemp <temperature>`
- `/setbasis <temperature|heatindex>`
- `/settime <on_seconds> <off_seconds>`
- `/setmode <temperature|scheduler>`
- `/switchOn`
- `/switchOff`

## 运行输出

- `data/settings.json`：运行时设置
- `data/ac_history.sqlite`：历史数据
- `figure/`：导出的图像
- `log/`：运行日志

## 安全说明

- 不要提交 `creds.json`、`creds/credentials.json` 或 `creds/` 下的真实密钥。
- `data/`、`log/`、`figure/` 默认都是运行产物，已在 `.gitignore` 中忽略。

## 相关文档

- 中文配置教程：[docs/setup.zh-CN.md](docs/setup.zh-CN.md)
- English setup guide: [docs/setup.en.md](docs/setup.en.md)
- 详细控制策略：[docs/control-strategy.zh-CN.md](docs/control-strategy.zh-CN.md)
