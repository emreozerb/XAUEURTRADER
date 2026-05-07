# INSTALL — XAUEUR Trading Bot on a Windows Server VPS

This guide walks you through running the bot on a single Windows Server VPS where MetaTrader 5, the FastAPI backend, and your browser all run on the same machine. The app binds to localhost only — there is no public exposure.

## 1. Prerequisites

Install the following on the VPS:

- **MetaTrader 5** — log in to your broker account, then open `Tools → Options → Server` and tick **"Start with Windows"** so MT5 launches automatically on boot.
- **Python 3.11 or 3.12** from [python.org](https://www.python.org/downloads/) — during install, tick **"Add Python to PATH"**.
- **Node.js 20 LTS** from [nodejs.org](https://nodejs.org/).
- **Git for Windows** from [git-scm.com](https://git-scm.com/download/win).
- **NSSM (Non-Sucking Service Manager)** from [nssm.cc](https://nssm.cc/download). Extract `nssm.exe` to a directory on PATH (e.g. `C:\Windows\System32`).

## 2. First-time setup

Open PowerShell, `cd` into the project root, then run:

```powershell
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
copy .env.example .env
```

Edit `.env` and fill in:

- `ANTHROPIC_API_KEY`
- `FINNHUB_API_KEY`

## 3. Manual test run

Verify everything works before installing as a service:

```powershell
python -m backend.main
```

Open `http://localhost:8000` in the browser on the VPS. Both the API **and** the UI are served from this single port. Stop with `Ctrl+C` once you've confirmed it works.

## 4. Install as a Windows service (NSSM)

Running under NSSM means the bot auto-starts on boot and survives RDP disconnect. Open PowerShell **as Administrator** and run:

```powershell
nssm install XAUEURBot
```

In the GUI that appears, fill in:

- **Application** tab:
  - **Path**: full path to `python.exe` (e.g. `C:\Python312\python.exe`)
  - **Startup directory**: full path to the project root
  - **Arguments**: `-m backend.main`
- **I/O** tab — redirect output to log files inside the project folder:
  - **Output (stdout)**: `<project-root>\logs\service-stdout.log`
  - **Error (stderr)**: `<project-root>\logs\service-stderr.log`
  - (Create the `logs\` folder first if it doesn't exist.)
- **Exit actions** tab — leave defaults (auto-restart on crash).

Click **Install service**, then start it:

```powershell
nssm start XAUEURBot
```

## 5. Verify auto-start

Reboot the VPS, RDP back in after 2 minutes, and confirm:

- MetaTrader 5 is running and logged in.
- The `XAUEURBot` service is running — check `Services.msc` or run `nssm status XAUEURBot`.
- `http://localhost:8000` loads the dashboard.

## 6. Updating the bot

```powershell
git pull
pip install -r requirements.txt    # only if requirements.txt changed
cd frontend && npm install && npm run build && cd ..    # only if frontend changed
nssm restart XAUEURBot
```

## 7. Backups

Schedule a daily copy of `trading_bot.db` to a separate folder using **Windows Task Scheduler**. The database holds the entire trade history.

## Notes

- The app binds to **localhost only**. Do **not** open port 8000 in the Windows firewall to the public internet without first adding authentication — there is currently none.
- Logs:
  - `trading_bot.log` — application logs.
  - `logs\service-stdout.log` and `logs\service-stderr.log` — NSSM-captured stdout/stderr.
- To uninstall the service:
  ```powershell
  nssm remove XAUEURBot confirm
  ```
