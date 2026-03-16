# HKUST AC Remaster

Automated controller for a HKUST dorm air-conditioner, with local sensor polling, prepaid AC portal integration, historical data recording, and QQ/Discord bot control.

Documentation:

- Chinese: [README.zh-CN.md](README.zh-CN.md)
- English: [README.en.md](README.en.md)
- Setup guide with Microsoft MFA, QQ bot, and Discord bot instructions:
  - Chinese: [docs/setup.zh-CN.md](docs/setup.zh-CN.md)
  - English: [docs/setup.en.md](docs/setup.en.md)

## Highlights

- HKUST SSO login with Microsoft TOTP
- Indoor climate polling through an SHT4x serial bridge
- Automatic temperature-mode and scheduler-mode control
- Local SQLite history recording and figure export
- QQ bot, Discord bot, and local Textual CLI interfaces

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
python controll.py
```

Credentials can be stored in either `creds.json` or `creds/credentials.json`. Start from `creds/credentials.example.json`.

## License

The project is licensed under the MIT License.