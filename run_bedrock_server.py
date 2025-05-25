import os
import subprocess
import sys
import signal
import time
import argparse

def run_bedrock_server(server_dir, as_service=False):
    exe_path = os.path.join(server_dir, "bedrock_server.exe")
    if not os.path.isfile(exe_path):
        print(f"bedrock_server.exe not found in {server_dir}")
        return 1
    try:
        if as_service:
            # Use 'sc start' to start the service named 'bedrock_server' (service must be pre-registered)
            # You may need to adjust the service name as needed
            service_name = "bedrock_server"
            result = subprocess.run(["sc", "start", service_name], shell=True)
            return result.returncode
        else:
            # Start bedrock_server.exe as a subprocess
            process = subprocess.Popen([exe_path], cwd=server_dir)
            def handle_signal(signum, frame):
                print(f"Received signal {signum}, terminating bedrock_server.exe...")
                try:
                    process.terminate()
                except Exception:
                    pass
            # Register signal handlers for graceful shutdown
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)
            try:
                process.wait()
            except KeyboardInterrupt:
                handle_signal(signal.SIGINT, None)
                process.wait()
            return process.returncode
    except Exception as e:
        print(f"Failed to start bedrock_server.exe: {e}")
        return 2

def stop_bedrock_server():
    """Terminate all running bedrock_server.exe processes (Windows only)."""
    try:
        result = subprocess.run([
            "taskkill", "/F", "/IM", "bedrock_server.exe"
        ], capture_output=True, text=True)
        print(result.stdout)
        if result.returncode == 0:
            print("All bedrock_server.exe processes terminated.")
        else:
            print("No bedrock_server.exe process found or failed to terminate.")
        return result.returncode
    except Exception as e:
        print(f"Failed to stop bedrock_server.exe: {e}")
        return 2

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Minecraft Bedrock server process.")
    parser.add_argument("server_dir", nargs="?", help="Server directory (required for --start or --service)")
    parser.add_argument("--start", action="store_true", help="Start bedrock_server.exe in the given directory")
    parser.add_argument("--stop", action="store_true", help="Stop all running bedrock_server.exe processes")
    parser.add_argument("--service", action="store_true", help="Start as Windows service (service must be pre-registered)")
    parser.add_argument("--create", action="store_true", help="Create the bedrock_server service if it does not exist")
    parser.add_argument("--remove", action="store_true", help="Remove the bedrock_server service if it exists")
    parser.add_argument("--status", action="store_true", help="Check if bedrock_server auto-start is enabled")
    args = parser.parse_args()

    # 只有同時指定 --create 與 --service 時才自動開機啟動 bedrock_server.exe（不再建立服務）
    if args.create and args.service:
        exe_path = os.path.join(args.server_dir or os.getcwd(), "bedrock_server.exe")
        if not os.path.isfile(exe_path):
            print(f"bedrock_server.exe not found in {args.server_dir or os.getcwd()}")
            sys.exit(1)
        # 設定開機自動啟動
        import winreg
        run_key = r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"
        app_name = "bedrock_server_auto_start"
        cmd = f'"{exe_path}"'
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, run_key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            print(f"已設定開機自動啟動: {cmd}")
        except PermissionError:
            print("請以管理員身分執行本程式以設定開機自動啟動。")
            sys.exit(1)
        except Exception as e:
            print(f"設定開機自動啟動失敗: {e}")
            sys.exit(1)
        sys.exit(0)
    # 移除服務：同時指定 --remove 與 --service
    if args.remove and args.service:
        import winreg
        run_key = r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"
        app_name = "bedrock_server_auto_start"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, run_key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, app_name)
            print(f"已移除開機自動啟動: {app_name}")
        except FileNotFoundError:
            print(f"未設定開機自動啟動: {app_name}")
        except PermissionError:
            print("請以管理員身分執行本程式以移除開機自動啟動。")
            sys.exit(1)
        except Exception as e:
            print(f"移除開機自動啟動失敗: {e}")
            sys.exit(1)
        sys.exit(0)
    # --start --service: 啟動服務前先檢查服務是否存在與狀態
    if args.start and args.service:
        service_name = "bedrock_server"
        check_result = subprocess.run(["sc", "query", service_name], capture_output=True, text=True)
        if "FAILED 1060" in check_result.stdout or "does not exist" in check_result.stdout or check_result.returncode != 0:
            print(f"Service '{service_name}' does not exist. 請先建立服務。")
            sys.exit(1)
        # 服務存在，檢查狀態
        if "RUNNING" in check_result.stdout:
            print(f"Service '{service_name}' 已經在執行中。")
            sys.exit(0)
        else:
            print(f"Service '{service_name}' 尚未啟動，正在啟動...")
            start_result = subprocess.run(["sc", "start", service_name], capture_output=True, text=True)
            print(start_result.stdout)
            if start_result.returncode == 0:
                print(f"Service '{service_name}' 已成功啟動。")
                sys.exit(0)
            else:
                print(f"啟動服務 '{service_name}' 失敗: {start_result.stdout}\n{start_result.stderr}")
                sys.exit(1)
    # --stop --service: 關閉服務前先檢查服務是否存在與狀態
    if args.stop and args.service:
        service_name = "bedrock_server"
        check_result = subprocess.run(["sc", "query", service_name], capture_output=True, text=True)
        if "FAILED 1060" in check_result.stdout or "does not exist" in check_result.stdout or check_result.returncode != 0:
            print(f"Service '{service_name}' does not exist. 無法關閉。")
            sys.exit(1)
        # 服務存在，檢查狀態
        if "RUNNING" in check_result.stdout:
            print(f"Service '{service_name}' 正在執行，正在關閉...")
            stop_result = subprocess.run(["sc", "stop", service_name], capture_output=True, text=True)
            print(stop_result.stdout)
            if stop_result.returncode == 0:
                print(f"Service '{service_name}' 已成功關閉。"); sys.exit(0)
            else:
                print(f"關閉服務 '{service_name}' 失敗: {stop_result.stdout}\n{stop_result.stderr}")
                sys.exit(1)
        else:
            print(f"Service '{service_name}' 未啟動，無需關閉。")
            sys.exit(0)
    # --status --service: 檢查開機自動啟動是否已存在
    if args.status and args.service:
        import winreg
        run_key = r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"
        app_name = "bedrock_server_auto_start"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, run_key, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, app_name)
                print(f"已設定開機自動啟動: {value}")
        except FileNotFoundError:
            print("尚未設定開機自動啟動。")
        except PermissionError:
            print("請以管理員身分執行本程式以查詢開機自動啟動狀態。")
            sys.exit(1)
        except Exception as e:
            print(f"查詢開機自動啟動狀態失敗: {e}")
            sys.exit(1)
        sys.exit(0)
    if args.stop:
        sys.exit(stop_bedrock_server())
    elif args.start:
        if not args.server_dir:
            print("Error: server_dir is required for --start")
            sys.exit(1)
        # If --service is also present, start as service
        if args.service:
            sys.exit(run_bedrock_server(args.server_dir, as_service=True))
        else:
            sys.exit(run_bedrock_server(args.server_dir, as_service=False))
    elif args.service:
        if not args.server_dir:
            print("Error: server_dir is required for --service")
            sys.exit(1)
        sys.exit(run_bedrock_server(args.server_dir, as_service=True))
    else:
        parser.print_help()
        sys.exit(1)
