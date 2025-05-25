# Minecraft Bedrock Server Manager (LilyGo)

This project provides a multi-version management tool for Minecraft Bedrock servers on Windows, featuring a Tkinter-based graphical user interface (`LilyGo.py`) for easy server administration and a helper script (`run_bedrock_server.py`) for command-line operations and NSSM-based service management.

## Features

-   **Multi-Version Management**: Auto-detect and switch between multiple Bedrock server versions located in `bedrock-server-*` directories.
-   **Symbolic Link Management**: Automatically creates and manages symlinks for the `worlds` directory and common configuration files (`allowlist.json`, `permissions.json`, `server.properties`) to a central location, allowing shared configurations and worlds across different server versions.
-   **One-Click Server Control**: Start and stop the `bedrock_server.exe` via the GUI. Integrates with NSSM service for robust server operation.
-   **NSSM Service Integration**:
    -   Enable/disable auto-start of the server on boot using NSSM (Non-Sucking Service Manager).
    -   GUI buttons to create, remove, start, and stop the NSSM service.
    -   Real-time status display of the NSSM service.
-   **Backup Functionality**: One-click button in the GUI to create a timestamped `.zip` backup of the shared `worlds` and `config` directories.
-   **Log Display**: View real-time server logs directly in the GUI when the server is started through it (either directly or via service).
-   **Process Detection**: Detects existing `bedrock_server.exe` processes on startup.
-   **Admin Privileges**: Automatically requests administrator privileges on startup, as they are required for service management and symlink creation on some systems.

## Prerequisites

-   Python 3.7+
-   Windows Operating System
-   `nssm.exe` (The Non-Sucking Service Manager) must be placed in the same directory as `LilyGo.py` and `run_bedrock_server.py`. You can download it from [nssm.cc](https://nssm.cc/download).

## Installation & Usage

 ## 1. (Optional) **Replace** the included NSSM:

If you prefer to use your own version of NSSM instead of the one provided:

- Download the latest `nssm.exe` from [nssm.cc](https://nssm.cc/download).
- Place `nssm.exe` in the root directory of the project (next to `LilyGo.py` and `run_bedrock_server.py`).

### 2. Install Python Dependencies

Open PowerShell in the project directory and run:

```powershell
pip install -r requirements.txt
```

### 3. Directory Structure

Ensure your server files are organized as follows:

```
.
├── LilyGo.py
├── run_bedrock_server.py
├── nssm.exe                 # <-- NSSM executable, v2.24, win64 version
├── requirements.txt
├── lilygo_config.ini        # (auto-generated)
├── bedrock-server-X.Y.Z.A/  # Example server version directory
│   ├── bedrock_server.exe
│   ├── ... (other server files)
│   └── worlds/              # (will be a symlink)
│   └── allowlist.json       # (will be a symlink)
│   └── permissions.json     # (will be a symlink)
│   └── server.properties    # (will be a symlink)
├── bedrock-server-A.B.C.D/  # Another server version directory
│   ├── bedrock_server.exe
│   ├── ...
├── config/                  # Central configuration files
│   ├── allowlist.json
│   ├── permissions.json
│   ├── server.properties
├── worlds/                  # Central worlds directory
│   └── (your world folders)
└── backup-YYYYMMDD-HHMMSS.zip # Example backup file (auto-generated)
```

-   The `config/` and `worlds/` directories in the root are the central storage. `LilyGo.py` will attempt to create them if they don\'t exist.
-   Symlinks will be created inside each `bedrock-server-*` directory, pointing to the central `worlds/` and `config/` files.

### 4. Launch the GUI Manager

```powershell
python LilyGo.py
```

> **Note:** The application will request administrator privileges on startup if not already elevated. This is necessary for managing NSSM services and creating symbolic links.

## Main Files

### `LilyGo.py`
-   **GUI**: Provides a user-friendly Tkinter interface for all management tasks.
-   **Server Selection**: Allows changing the active Bedrock server version.
-   **Start/Stop**: Starts or stops the Bedrock server (directly or via NSSM service).
-   **Log Display**: Shows server output.
-   **Symlink Management**: Handles creation and validation of symlinks for worlds and configuration files.
-   **Auto-Start (NSSM Service)**:
    -   Buttons to create/remove the NSSM service for the selected server.
    -   Displays the current status of the service (e.g., Running, Stopped, Not Installed).
    -   Allows toggling the auto-start behavior by managing the NSSM service.
-   **Backup**: Creates a `.zip` archive of the `worlds` and `config` directories.

### `run_bedrock_server.py`
This is a command-line helper script used by `LilyGo.py` and can also be run manually.

-   **Direct Server Control**:
    -   `--start <server_directory_path>`: Starts `bedrock_server.exe` directly from the specified path.
    -   `--stop`: Stops all running `bedrock_server.exe` instances using `psutil` and `taskkill`.
-   **NSSM Service Management**:
    -   `--create-service <server_directory_path>`: Creates and configures an NSSM service to run `bedrock_server.exe` from the specified path.
    -   `--remove-service`: Removes the NSSM service.
    -   `--start-service`: Starts the NSSM service.
    -   `--stop-service`: Stops the NSSM service.
    -   `--status-service`: Checks and returns the status of the NSSM service (Running, Stopped, Not Found, etc., via exit codes).
-   **Admin Rights**: Includes checks for administrator privileges for service-related operations and attempts to self-elevate if necessary.

## Notes
-   This tool is designed and tested for Windows.
-   Administrator privileges are generally required for full functionality (NSSM service management, symlink creation).
-   Ensure `nssm.exe` is present in the application\'s root directory.

## License

MIT License
