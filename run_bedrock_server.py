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
        import psutil
        found = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and 'bedrock_server.exe' in proc.info['name'].lower():
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                        print(f"Terminated bedrock_server.exe (PID: {proc.pid})")
                    except Exception:
                        print(f"Force killing bedrock_server.exe (PID: {proc.pid})")
                        proc.kill()
                    found = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if found:
            print("All bedrock_server.exe processes terminated.")
            return 0
        else:
            print("No bedrock_server.exe process found or failed to terminate.")
            return 1
    except ImportError:
        # Fallback to taskkill if psutil is not available
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
    parser.add_argument("server_dir", nargs="?", help="Server directory (required for --start, --create-service)")
    parser.add_argument("--start", action="store_true", help="Start bedrock_server.exe in the given directory")
    parser.add_argument("--stop", action="store_true", help="Stop all running bedrock_server.exe processes")
    parser.add_argument("--create-service", action="store_true", help="Register bedrock_server.exe as a Windows service using NSSM (auto-start at boot, even before login)")
    parser.add_argument("--remove-service", action="store_true", help="Remove the Windows service registered by NSSM")
    parser.add_argument("--status-service", action="store_true", help="Check if the Windows service is registered and running")
    parser.add_argument("--start-service", action="store_true", help="Start the Windows service for bedrock_server.exe via NSSM")
    parser.add_argument("--stop-service", action="store_true", help="Stop the Windows service for bedrock_server.exe via NSSM")
    args = parser.parse_args()

    nssm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nssm.exe")
    service_name = "bedrock_server_nssm"

    # Common administrator rights check for service modification operations
    needs_admin = args.create_service or args.remove_service or args.start_service or args.stop_service
    if needs_admin and sys.platform == "win32":
        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("Requesting administrator privileges for service operation...")
                
                script_path = os.path.abspath(sys.argv[0])
                # Construct parameters: script path and its original arguments, quoting if spaces are present
                params_list = [f'"{script_path}"'] 
                for arg_val in sys.argv[1:]:
                    params_list.append(f'"{arg_val}"' if ' ' in arg_val else arg_val)
                params_str = ' '.join(params_list)
                
                # SW_SHOWNORMAL is 1
                ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params_str, None, 1)
                
                if ret <= 32: # ShellExecuteW returns a value > 32 on success
                    print(f"Failed to elevate privileges (ShellExecuteW error code: {ret}). Please run as administrator.")
                    sys.exit(1)
                sys.exit(0) # Exit current non-admin instance; admin instance will run with original args
        except ImportError:
            print("Warning: 'ctypes' module not available. Cannot check/elevate admin rights in Windows.")
        except Exception as e:
            print(f"Warning: Could not check or elevate admin rights: {e}. Service operation may fail if not run as administrator.")

    cflags = 0
    if sys.platform == "win32":
        cflags = subprocess.CREATE_NO_WINDOW

    if args.create_service:
        if not args.server_dir:
            print("Error: --server_dir is required for --create-service.")
            sys.exit(1)
        
        abs_server_dir = os.path.abspath(args.server_dir)
        exe_path = os.path.join(abs_server_dir, "bedrock_server.exe")

        if not os.path.isfile(exe_path):
            print(f"bedrock_server.exe not found in {abs_server_dir}")
            sys.exit(1)
        if not os.path.isfile(nssm_path):
            print(f"nssm.exe not found in script directory. Please download NSSM and place nssm.exe here: {nssm_path}")
            sys.exit(1)

        # Check if service already exists
        query_cmd = ["sc", "query", service_name]
        query_process = subprocess.Popen(query_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
        query_stdout, query_stderr = query_process.communicate()
        query_returncode = query_process.returncode

        if query_returncode == 0: # Service exists
            print(f"Service '{service_name}' already exists. Skipping creation.")
            sys.exit(0)
        elif query_returncode == 1060: # Service does not exist (SC_STATUS_SERVICE_DOES_NOT_EXIST)
            print(f"Service '{service_name}' does not exist. Proceeding with creation.")
            # Proceed to create
        else: # Some other error
            print(f"Error checking service status for '{service_name}'.")
            print(f"SC query return code: {query_returncode}")
            print(f"STDOUT:\n{query_stdout}")
            print(f"STDERR:\n{query_stderr}")
            sys.exit(1)
        
        print(f"Attempting to create and configure service '{service_name}'...")

        # Install service
        install_cmd = [nssm_path, "install", service_name, exe_path]
        result = subprocess.run(install_cmd, capture_output=True, text=True, creationflags=cflags)
        if result.returncode != 0:
            print(f"Failed to install service '{service_name}' with NSSM.")
            print(f"NSSM output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
            sys.exit(1)
        print(f"Service '{service_name}' installed successfully.")

        # Configure AppDirectory
        appdir_cmd = [nssm_path, "set", service_name, "AppDirectory", abs_server_dir]
        result = subprocess.run(appdir_cmd, capture_output=True, text=True, creationflags=cflags)
        if result.returncode != 0:
            print(f"Failed to set AppDirectory for '{service_name}'. Attempting to remove partially configured service.")
            print(f"NSSM output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
            subprocess.run([nssm_path, "remove", service_name, "confirm"], capture_output=True, text=True, creationflags=cflags)
            sys.exit(1)
        print(f"AppDirectory for '{service_name}' set to '{abs_server_dir}'.")

        # Configure Start type
        start_cmd = [nssm_path, "set", service_name, "Start", "SERVICE_AUTO_START"]
        result = subprocess.run(start_cmd, capture_output=True, text=True, creationflags=cflags)
        if result.returncode != 0:
            print(f"Failed to set Start type for '{service_name}'. Attempting to remove partially configured service.")
            print(f"NSSM output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
            subprocess.run([nssm_path, "remove", service_name, "confirm"], capture_output=True, text=True, creationflags=cflags)
            sys.exit(1)
        print(f"Start type for '{service_name}' set to SERVICE_AUTO_START.")

        # Configure DisplayName
        display_name_str = f"Bedrock Server ({service_name})"
        displayname_cmd = [nssm_path, "set", service_name, "DisplayName", display_name_str]
        result = subprocess.run(displayname_cmd, capture_output=True, text=True, creationflags=cflags)
        if result.returncode != 0:
            print(f"Warning: Failed to set DisplayName for '{service_name}'.")
            print(f"NSSM output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        else:
            print(f"DisplayName for '{service_name}' set to '{display_name_str}'.")

        # Configure Description
        description_str = f"Minecraft Bedrock Edition server ({exe_path}) managed by NSSM."
        description_cmd = [nssm_path, "set", service_name, "Description", description_str]
        result = subprocess.run(description_cmd, capture_output=True, text=True, creationflags=cflags)
        if result.returncode != 0:
            print(f"Warning: Failed to set Description for '{service_name}'.")
            print(f"NSSM output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        else:
            print(f"Description for '{service_name}' set to '{description_str}'.")
            
        print(f"Service '{service_name}' created and configured successfully.")
        sys.exit(0)

    if args.remove_service:
        if not os.path.isfile(nssm_path):
            print(f"nssm.exe not found in script directory. Please download NSSM and place nssm.exe here: {nssm_path}")
            sys.exit(1)
        # Admin check is now done globally if needed_admin is true
        print(f"Attempting to remove service '{service_name}'...")
        remove_cmd = [nssm_path, "remove", service_name, "confirm"]
        result = subprocess.run(remove_cmd, capture_output=True, text=True, creationflags=cflags)
        if result.returncode == 0 or "Service " + service_name + " removed" in result.stdout : # NSSM remove can return non-zero even on success if service was already gone
            # A more robust check might be to query service status after attempting removal
            query_cmd_after_remove = ["sc", "query", service_name]
            query_proc_after_remove = subprocess.Popen(query_cmd_after_remove, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
            _, _ = query_proc_after_remove.communicate()
            if query_proc_after_remove.returncode == 1060: # Service does not exist
                 print(f"Service '{service_name}' removed successfully or was not found.")
                 sys.exit(0)
            else:
                 print(f"Service '{service_name}' removal command executed, but service might still exist or state is unclear.")
                 print(f"NSSM output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
                 sys.exit(1)

        else:
            print(f"Failed to remove service '{service_name}'.")
            print(f"NSSM output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
            # Check if service still exists
            query_cmd_check = ["sc", "query", service_name]
            query_proc_check = subprocess.Popen(query_cmd_check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
            _, _ = query_proc_check.communicate()
            if query_proc_check.returncode == 1060: # Service does not exist
                 print(f"Service '{service_name}' was already not present.")
            sys.exit(1)
        sys.exit(0) # Should be handled by above logic

    if args.status_service:
        query_cmd = ["sc", "query", service_name]
        result = subprocess.run(query_cmd, capture_output=True, text=True, creationflags=cflags)
        
        if result.returncode == 1060:
            print(f"Service '{service_name}' does not exist.")
            sys.exit(1) # Not found
        elif result.returncode == 0:
            print(f"Status for service '{service_name}':")
            print(result.stdout)
            if "RUNNING" in result.stdout:
                print(f"Service '{service_name}' is running.")
                sys.exit(0) # Running
            elif "STOPPED" in result.stdout:
                print(f"Service '{service_name}' is installed but not running (STOPPED).")
                sys.exit(2) # Installed but not running
            else:
                print(f"Service '{service_name}' is in an unknown state.")
                sys.exit(3) # Unknown state
        else:
            print(f"Failed to query service status for '{service_name}'.")
            print(f"SC query return code: {result.returncode}")
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            sys.exit(4) # Query failed

    if args.stop:
        sys.exit(stop_bedrock_server())
    elif args.start:
        if not args.server_dir:
            print("Error: server_dir is required for --start")
            sys.exit(1)
        sys.exit(run_bedrock_server(args.server_dir, as_service=False))
    elif args.start_service or args.stop_service:
        # Admin rights check is now handled globally if needs_admin is true
        action = "start" if args.start_service else "stop"
        print(f"Attempting to {action} service '{service_name}'...")
        result = subprocess.run(["sc", action, service_name], capture_output=True, text=True, creationflags=cflags)
        print(result.stdout) # SC usually prints status to stdout
        if result.returncode == 0:
            # SC start/stop might return 0 even if the state doesn't change immediately or if already in desired state.
            # e.g. starting an already started service, or stopping an already stopped service.
            # Check stderr for specific common errors like "service has not been started" (1062 for stop)
            # or "service is already running" (1056 for start)
            if "1062" in result.stderr and action == "stop": # ERROR_SERVICE_NOT_ACTIVE
                 print(f"Service '{service_name}' was not running.")
            elif "1056" in result.stderr and action == "start": # ERROR_SERVICE_ALREADY_RUNNING
                 print(f"Service '{service_name}' was already running.")
            else:
                 print(f"Service '{service_name}' {action} command issued successfully.")
            sys.exit(0)
        else:
            print(f"Failed to {action} service '{service_name}'.")
            if result.stderr:
                print(f"Error: {result.stderr.strip()}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)
