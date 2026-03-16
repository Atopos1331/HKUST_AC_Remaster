# HKUST AC Remaster

HKUST AC Remaster is an automated controller for a HKUST dorm air-conditioner. It logs into the campus prepaid AC portal, reads an indoor temperature/humidity sensor, applies either temperature-based or scheduler-based control, records time-series data, and exposes QQ, Discord, and local CLI control surfaces.

## Features

- HKUST login through Microsoft SSO with TOTP
- Indoor climate polling through an SHT4x serial bridge
- Temperature mode and scheduler mode control logic
- SQLite history recording, range statistics, and figure export
- QQ bot, Discord bot, and local Textual CLI interfaces

## Screenshot Slots

The sections below are intentionally reserved for GitHub screenshots. You can later place actual images under something like `docs/images/` and replace the paths.

### Runtime Overview

### `controll_cli.py` Interface

![CLI Screenshot](docs/images/cli-en.jpg)

### `analyse.py` Output

![Analysis Screenshot](docs/images/analysis.png)

### Bot Command Demo

![Bot Screenshot](docs/images/bot-discord-en.jpg)

## Layout

```text
controll.py         Main runtime entry point
controll_cli.py     Local Textual control console
analyse.py          Analysis CLI / shell
powers/
  auth/             HKUST login and AC portal API client
  data/             State, settings, recorder, and analysis
  io/               Indoor sensor drivers
  services/         Control logic
  qq_bot.py         QQ bot integration
  discord_bot.py    Discord bot integration
  utils/            Config and logging
docs/               Chinese / English setup guides
```

## Requirements

- Python 3.10+
- Access to the HKUST AC portal network path
- An available Microsoft Authenticator-compatible TOTP app
- An SHT4x serial bridge on the configured COM port
- Optional: QQ bot and Discord bot developer accounts

## Install

```bash
pip install -r requirements.txt
playwright install chromium
```

## Credentials

The program checks these files in order:

- `creds.json`
- `creds/credentials.json`

Start from the template:

```bash
copy creds\credentials.example.json creds\credentials.json
```

Template:

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

Notes:

- `microsoft_secret` is the manual setup key for Microsoft Authenticator.
- `qq_app_id` and `qq_secret` come from the QQ Open Platform bot app.
- `discord_token` comes from the Discord Developer Portal.
- `command_language` can be `zh`, `en`, or `bilingual`.

## Run

Main controller:

```bash
python controll.py
```

Local control console:

```bash
python controll_cli.py
```

Analysis shell:

```bash
python analyse.py
```

Visible-browser debug mode:

```bash
debug.bat
```

## Bot Enable / Disable Switches

At the top of `controll.py`, there are two direct runtime toggles:

```python
ENABLE_QQ_BOT = True
ENABLE_DISCORD_BOT = True
```

You can set them as needed:

- both enabled: QQ and Discord run together
- QQ only: `ENABLE_QQ_BOT = True`, `ENABLE_DISCORD_BOT = False`
- Discord only: `ENABLE_QQ_BOT = False`, `ENABLE_DISCORD_BOT = True`
- both disabled: local control, logging, and analysis only

This is useful when debugging authentication, control logic, or one bot integration at a time.

## Current Sensor Logic

The current temperature / humidity reading path is based on my own hardware setup. It is not intended as a universal off-the-shelf sensor driver.

The default implementation is split into:

- abstract interface: `powers/io/thermometer.py`
- current hardware implementation: `powers/io/sht4x_serial_sensor.py`

The `Thermometer` base class defines the core methods:

- `connect()`
- `get_climate()`
- `get_device_info()`

The default `get_thermometer()` entry point currently instantiates `SHT4xSerialThermometer(port=SERIAL_PORT)` and returns `IndoorClimateReading(temperature, humidity)` through `get_climate()`.

### How to Adapt Your Own Hardware

There are three common options:

1. Buy or build a compatible sensor setup and implement your own module against the existing `Thermometer` abstract interface.
2. Change the import / factory entry in `powers/io/thermometer.py` so `get_thermometer()` points to your own implementation.
3. If you do not have a real sensor yet, create a placeholder module that returns fixed temperature and humidity values and only use scheduler mode.

### Recommended Extension Pattern

You can create a module like:

```python
from powers.io.thermometer import IndoorClimateReading, Thermometer


class DummyThermometer(Thermometer):
    def connect(self) -> None:
        pass

    def get_climate(self) -> IndoorClimateReading:
        return IndoorClimateReading(temperature=27.0, humidity=60.0)

    def get_device_info(self) -> dict:
        return {"driver": "dummy"}
```

Then point `powers/io/thermometer.py` at that implementation. The rest of the project can remain unchanged.

### If You Do Not Have a Sensor

If you mainly want to use the project as an automated AC scheduler:

- provide a placeholder climate module
- switch the controller to `scheduler` mode
- do not depend on real indoor feedback

In that configuration you can still use:

- automatic login and AC control
- bot commands
- logging
- electrical / balance / outdoor weather recording

## Control Strategy

The main loop is started by `controll.py` and currently runs:

- indoor sensor thread
- control logic thread
- indoor / electrical recorder thread
- outdoor weather recorder thread
- QQ bot
- Discord bot

The control core lives in `powers/services/control_service.py`.

### Temperature Mode

Temperature mode uses these settings:

- `target_temp`
- `temperature_control_basis`
- `temp_threshold_high`
- `temp_threshold_low`
- `cooldown_time`

The `temperature_control_basis` can be:

- `temperature`
- `heat_index`

So the controller can operate either on dry-bulb temperature or on heat index.

The temperature-mode behavior is:

- if AC is off and current value is above `target_temp + temp_threshold_high`, request AC on
- if AC is on and current value is below `target_temp - temp_threshold_low`, request AC off
- otherwise keep the current state

This is a hysteresis-based strategy intended to reduce state flapping around the target point.

### Cooldown

`cooldown_time` is one of the most important temperature-mode parameters.

It defines the minimum delay between two state transitions. While the controller is still inside the cooldown window, it does not immediately toggle again even if the metric crosses a threshold.

This helps:

- prevent rapid toggling
- reduce short-cycling
- allow the room and the AC to reflect the previous action before another one is issued

### Scheduler Mode

Scheduler mode ignores live indoor feedback and only uses:

- `ontime`
- `offtime`

Based on the current AC state and `last_switch`:

- if AC is currently on, it turns off after `ontime`
- if AC is currently off, it turns on after `offtime`

This mode is useful when:

- you do not have a reliable temperature/humidity sensor
- your room has relatively stable thermal inertia
- you already know a workable duty cycle

### Temporary Lock

The controller also supports a temporary lock:

- `lock_status`
- `lock_end_time`

If the lock is still active, the control logic obeys the lock state before normal temperature-mode or scheduler-mode decisions.

This is useful for:

- forcing AC on before sleep for a fixed period
- forcing AC off temporarily
- overriding automatic logic for a short window

### Device Off-Timer as a Safety Guard

When the controller decides to turn the AC on, `ControlService.action()` also synchronizes the device-side off-timer.

That means the system does not only remember the intended next stop locally. It also writes a shutoff time into the AC-side timer. If the process exits unexpectedly, a thread hangs, or connectivity breaks, the hardware still has a fallback off-time to reduce the chance of the AC running longer than intended.

### Master Switch and Balance Guard

Every control cycle in `controll.py` first checks:

- the master `switch`
- the prepaid `balance`

If:

- the master switch is off, control actions are skipped
- the balance is depleted, control actions are skipped

This prevents unnecessary AC operations in states that are clearly invalid for control.

## Entry Scripts

### `controll.py`

This is the main runtime entry. It is responsible for:

- starting all worker threads
- initializing QQ / Discord bots
- polling the indoor sensor
- making control decisions
- recording runtime data
- handling graceful shutdown

If you want the whole system to keep running, this is the primary entry point.

### `controll_cli.py`

This is a Textual-based local operator console. It is useful for:

- viewing runtime logs locally
- issuing commands and getting immediate responses
- testing the command handler without QQ / Discord
- debugging control logic, bot commands, and analysis commands

It shares the same `BotMessageHandler` as the bots, so it acts as a direct local debug front-end for the command system.

### `analyse.py`

This is the historical analysis entry point. It supports:

- listing available metrics
- building range summaries
- generating AI prompts
- exporting figures
- launching an interactive shell

Typical uses:

- reviewing the last few hours or days of runtime behavior
- checking AC runtime, power, and balance changes
- comparing indoor and outdoor temperature / humidity / heat index
- exporting plots for reporting or tuning
- generating analysis context for future parameter adjustment

## Shared Commands

QQ, Discord, and the local CLI all route into the same command handler. Common commands:

- `/state`
- `/scheduler`
- `/timer`
- `/lock`
- `/log`
- `/stats 24h`
- `/plot 6h`
- `/settemp 28.5`
- `/setbasis temperature|heatindex`
- `/settime 300 1200`
- `/setmode temperature|scheduler`
- `/switchOn`
- `/switchOff`

## Runtime Outputs

- `data/settings.json`: persisted runtime settings
- `data/ac_history.sqlite`: measurement database
- `figure/`: exported figures
- `log/`: runtime and warning logs

## Security

- Never commit `creds.json`, `creds/credentials.json`, or any real secrets under `creds/`.
- `data/`, `log/`, and `figure/` are runtime artifacts and are git-ignored by default.
- Keep QQ and Discord bot permissions minimal and enable only the events this project actually consumes.

## Guides

- Chinese setup guide: [docs/setup.zh-CN.md](docs/setup.zh-CN.md)
- English setup guide: [docs/setup.en.md](docs/setup.en.md)
