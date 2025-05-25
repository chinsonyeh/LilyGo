# Minecraft Bedrock Server Manager (LilyGo)

This project provides a multi-version management tool for Minecraft Bedrock servers on Windows, including a graphical management interface (LilyGo.py) and an auto-start/process management script (run_bedrock_server.py).

## Features

- Auto-detect and switch between multiple Bedrock server versions
- Automatically create symlinks for worlds and config files (allowlist.json, permissions.json, server.properties)
- One-click start/stop for bedrock_server.exe with real-time log display
- Search for and terminate all bedrock_server.exe processes
- Support for auto-start on boot (via Windows registry Run, no Windows service required)
- Auto-detect and toggle auto-start status
- Requests administrator privileges on startup

## Installation & Usage

### 1. Install Python Dependencies

Make sure you have Python 3.7+ installed, then run in the project directory:

```powershell
pip install -r requirements.txt
```

### 2. Launch the GUI Manager

```powershell
python LilyGo.py
```

> **Note:** The first launch will automatically request administrator privileges.

### 3. Example Server Directory Structure

```
.
├── LilyGo.py
├── run_bedrock_server.py
├── requirements.txt
├── bedrock-server-1.21.83.1/
│   ├── bedrock_server.exe
│   ├── ...
├── config/
│   ├── allowlist.json
│   ├── permissions.json
│   ├── server.properties
├── worlds/
│   └── ...
```

## Main Files

### LilyGo.py
- Tkinter GUI for server directory selection, start/stop, log display, symlink management, and auto-start configuration.
- One-click button to enable/disable auto-start, with real-time status update.
- Detects running bedrock_server.exe processes on startup.

### run_bedrock_server.py
- Supports `--start`, `--stop`, `--service`, `--create`, `--remove`, `--status` arguments.
- `--create --service` sets up auto-start (writes to registry Run), `--remove --service` removes it.
- `--status --service` checks auto-start status.
- Robust process and auto-start management.

## Notes
- This tool is tested only on Windows.
- Setting/removing auto-start requires administrator privileges.
- Symlink creation requires Windows Developer Mode or running as administrator.

## License

MIT License
