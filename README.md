# HKUST AC Remaster

Automated controller for a HKUST dorm air-conditioner, with prepaid portal integration, indoor climate polling, historical recording, and QQ/Discord/local CLI control.

Documentation:

- Chinese: [README.zh-CN.md](README.zh-CN.md)
- English: [README.en.md](README.en.md)
- Setup guide:
  - Chinese: [docs/setup.zh-CN.md](docs/setup.zh-CN.md)
  - English: [docs/setup.en.md](docs/setup.en.md)
- Detailed control strategy:
  - Chinese: [docs/control-strategy.zh-CN.md](docs/control-strategy.zh-CN.md)
  - English: [docs/control-strategy.en.md](docs/control-strategy.en.md)

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
python run_forever.py
```

Notes:

- The project is not Windows-only. It can run on Windows, Linux, or macOS as long as Python, Playwright Chromium, and the required network access are available.
- `run_forever.py` is the recommended long-running entry point. It restarts `controll_cli.py` automatically after unexpected exits.
- `start.bat` is only a Windows convenience wrapper around `python run_forever.py`.

## License

The project is licensed under the MIT License.
