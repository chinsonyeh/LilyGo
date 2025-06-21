import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys # Added for sys.executable and sys.argv
import re
import subprocess
import configparser
import threading # Added import for threading
import ctypes # Added for admin check
import psutil
import shutil # Added for rmtree
from datetime import datetime # Added for backup timestamp
import zipfile # Added for backup zip creation
import ssl

# Global constants for configuration
CONFIG_FILE_NAME = "lilygo_config.ini"
CONFIG_SECTION = "ServerManager"
CONFIG_KEY_CURRENT_SERVER = "CurrentServer"
SERVER_DIR_PREFIX = "bedrock-server-"
WORLDS_DIR_NAME = "worlds"
SERVICE_NAME = "bedrock_server_nssm"

class ServerManagerApp:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Bedrock Server Manager (LilyGo)")

        # Determine script directory
        if getattr(sys, 'frozen', False): # Corrected: \'frozen\' to 'frozen'
            # If the application is run as a bundle/frozen executable
            self.script_dir = os.path.dirname(sys.executable)
        else:
            # If the application is run as a script
            self.script_dir = os.path.dirname(os.path.abspath(__file__))

        self.config_file_path = os.path.join(self.script_dir, CONFIG_FILE_NAME)
        self.base_worlds_path = os.path.join(self.script_dir, WORLDS_DIR_NAME)

        self.current_server_var = tk.StringVar()
        # self.status_var = tk.StringVar() # Removed, will use Text widget directly

        self.latest_bedrock_version = None
        self.latest_bedrock_url = None

        self.is_autostart_enabled = False  # Track autostart status

        self._setup_ui()
        self._initial_setup_and_checks(check_newer_version_prompt=True)

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Server Directory Label and Entry
        ttk.Label(main_frame, text="Selected Server Directory:").grid(row=0, column=0, columnspan=5, sticky=tk.W, pady=(0,5))
        self.server_entry = ttk.Entry(main_frame, textvariable=self.current_server_var, state="readonly", width=70)
        self.server_entry.grid(row=1, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=(0,10))

        # Start/Stop Server Button (leftmost)
        self.server_process = None
        self.server_thread = None
        self.start_server_button = ttk.Button(main_frame, text="Start Bedrock Server", command=self._toggle_bedrock_server)
        self.start_server_button.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=(0,5), pady=(0,10))

        # Auto-start Button (2nd from left)
        self.auto_start_button = ttk.Button(main_frame, text="Enable Autostart", command=self._toggle_autostart_bedrock_server)
        self.auto_start_button.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=(0,10))

        # Backup Button (shift right)
        self.backup_button = ttk.Button(main_frame, text="Backup", command=self._backup_data)
        self.backup_button.grid(row=2, column=2, sticky=(tk.W, tk.E), padx=5, pady=(0,10))

        # Change Server Button (shift right)
        self.switch_version_button = ttk.Button(main_frame, text="Switch Version", command=self._switch_version_directory)
        self.switch_version_button.grid(row=2, column=3, sticky=(tk.W, tk.E), padx=5, pady=(0,10))
        
        # Download Latest Button (layout adjusted, same row/width as others)
        self.download_latest_button = ttk.Button(main_frame, text="Download Latest Bedrock Server", command=self._download_latest_bedrock_server)
        self.download_latest_button.grid(row=2, column=4, sticky=(tk.W, tk.E), padx=(5,0), pady=(0,10))
        main_frame.columnconfigure(4, weight=1)  # Allow 5th column (download button) to expand

        # Status Label
        ttk.Label(main_frame, text="Status Log:").grid(row=3, column=0, columnspan=5, sticky=tk.W, pady=(5,0))
        
        # Status Text Area with Scrollbar
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=4, column=0, columnspan=5, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0,10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)

        self.status_text = tk.Text(status_frame, wrap=tk.WORD, height=25, state='disabled', relief=tk.SUNKEN, borderwidth=1)
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.status_text['yscrollcommand'] = scrollbar.set

        # Configure main_frame column and row weights for expansion
        for i in range(5):
            main_frame.columnconfigure(i, weight=1)
        main_frame.rowconfigure(4, weight=1)
        self._update_download_button_state()
        self._update_server_related_buttons_state()

    def _add_status_message(self, message, is_error=False, is_warning=False):
        print(f"Status: {message}")
        self.status_text.config(state='normal')
        lines = message.split('\n')
        for i, line in enumerate(lines):
            if self.status_text.index('end-1c') != '1.0' or i > 0:
                self.status_text.insert(tk.END, "\n")
            self.status_text.insert(tk.END, line)
        self.status_text.see(tk.END)
        self.status_text.config(state='disabled')
        if is_error:
            messagebox.showerror("Error", message)
        elif is_warning:
            messagebox.showwarning("Warning", message)

    def _clear_status(self):
        # Do nothing: keep log persistent and always append new messages
        pass

    def _load_config(self):
        parser = configparser.ConfigParser()
        if os.path.exists(self.config_file_path):
            parser.read(self.config_file_path)
            return parser.get(CONFIG_SECTION, CONFIG_KEY_CURRENT_SERVER, fallback=None)
        return None

    def _save_config(self, server_name):
        parser = configparser.ConfigParser()
        if os.path.exists(self.config_file_path): # Read existing to preserve other sections/keys
            parser.read(self.config_file_path)

        if not parser.has_section(CONFIG_SECTION):
            parser.add_section(CONFIG_SECTION)
        
        if server_name:
            parser.set(CONFIG_SECTION, CONFIG_KEY_CURRENT_SERVER, server_name)
        else: # If server_name is None or empty, remove the key
            if parser.has_option(CONFIG_SECTION, CONFIG_KEY_CURRENT_SERVER):
                parser.remove_option(CONFIG_SECTION, CONFIG_KEY_CURRENT_SERVER)
        
        try:
            with open(self.config_file_path, 'w') as f: # Corrected: \'w\' to 'w'
                parser.write(f)
        except IOError as e:
            self._add_status_message(f"Error saving config: {e}", is_error=True)

    def _parse_version_tuple(self, version_str):
        # Regex to match standard version numbers like 1.20.83.1 or 1.21.0
        processed_version_str = version_str.strip() # Remove leading/trailing whitespace
        print(processed_version_str)
        match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?", processed_version_str)
        if not match:
            # Include both original and processed string in error for clarity
            raise ValueError(f"Invalid version string format '{version_str}' (processed as '{processed_version_str}')")
        
        # Convert matched groups to integers, using 0 for missing minor/patch/build parts
        return tuple(int(part) if part is not None else 0 for part in match.groups())


    def _get_server_directories_info(self):
        server_dirs = []
        if not os.path.isdir(self.script_dir):
            self._add_status_message(f"Script directory '{self.script_dir}' not found.", is_error=True)
            return []
            
        for item in os.listdir(self.script_dir):
            item_path = os.path.join(self.script_dir, item)
            if os.path.isdir(item_path) and item.startswith(SERVER_DIR_PREFIX):
                version_str = item[len(SERVER_DIR_PREFIX):]
                try:
                    version_obj = self._parse_version_tuple(version_str)
                    server_dirs.append({"name": item, "version": version_obj, "path": item_path})
                except ValueError as e:
                    self._add_status_message(f"Warning: Could not parse version from '{item}': {e}. Skipping.", is_warning=True)
        
        server_dirs.sort(key=lambda x: x["version"], reverse=True) # Newest first
        return server_dirs

    def _ensure_script_worlds_dir_exists(self):
        if not os.path.exists(self.base_worlds_path):
            try:
                os.makedirs(self.base_worlds_path)
                self._add_status_message(f"Created base '{WORLDS_DIR_NAME}' directory: {self.base_worlds_path}")
            except OSError as e:
                self._add_status_message(f"Error creating base '{WORLDS_DIR_NAME}' dir: {e}", is_error=True)
                return False
        elif not os.path.isdir(self.base_worlds_path):
            self._add_status_message(f"Error: '{self.base_worlds_path}' exists but is not a directory.", is_error=True)
            return False
        return True

    def _check_and_create_worlds_link(self, server_dir_path):
        target_link_path = os.path.join(server_dir_path, WORLDS_DIR_NAME)
        server_name = os.path.basename(server_dir_path)

        if not os.path.exists(self.base_worlds_path) or not os.path.isdir(self.base_worlds_path):
            self._add_status_message(f"Source '{WORLDS_DIR_NAME}' ('{self.base_worlds_path}') not found. Cannot create link.", is_warning=True)
            return

        link_exists_correctly = False
        if os.path.lexists(target_link_path): # Use lexists for symlinks
            if os.path.islink(target_link_path):
                try:
                    link_target = os.readlink(target_link_path)
                    # Resolve both paths to be absolute for reliable comparison
                    abs_link_target = os.path.abspath(os.path.join(os.path.dirname(target_link_path), link_target))
                    abs_base_worlds = os.path.abspath(self.base_worlds_path)

                    # Remove \\?\ prefix for Windows long paths if present
                    if abs_link_target.startswith('\\\\?\\'):
                        abs_link_target = abs_link_target[4:]
                    if abs_base_worlds.startswith('\\\\?\\'):
                        abs_base_worlds = abs_base_worlds[4:]

                    if abs_link_target == abs_base_worlds:
                        self._add_status_message(f"'{WORLDS_DIR_NAME}' symlink in '{server_name}' is correct.")
                        link_exists_correctly = True
                    else:
                        msg = (f"Warning: '{WORLDS_DIR_NAME}' in '{server_name}' is a symlink but points to "
                               f"'{link_target}' (resolves to '{abs_link_target}') instead of '{abs_base_worlds}'.")
                        self._add_status_message(msg, is_warning=True)
                        if messagebox.askyesno("Fix Symlink?", f"{msg}\\n\\nDelete and attempt to recreate?"):
                            try:
                                os.unlink(target_link_path)
                                self._add_status_message(f"Removed incorrect symlink: {target_link_path}")
                            except OSError as e_unlink:
                                self._add_status_message(f"Error removing incorrect symlink '{target_link_path}': {e_unlink}", is_error=True)
                                return
                        else:
                            return # User chose not to fix
                except OSError as e: # os.readlink can fail
                    msg = f"Warning: Could not read symlink at '{target_link_path}': {e}. It might be broken."
                    self._add_status_message(msg, is_warning=True)
                    if messagebox.askyesno("Fix Broken Symlink?", f"{msg}\\n\\nDelete and attempt to recreate?"):
                        try:
                            os.unlink(target_link_path)
                            self._add_status_message(f"Removed broken symlink: {target_link_path}")
                        except OSError as e_unlink:
                            self._add_status_message(f"Error removing broken symlink '{target_link_path}': {e_unlink}", is_error=True)
                            return
                    else:
                        return
            else: # Exists but is not a symlink
                msg = (f"Warning: '{target_link_path}' exists but is not a symlink (it's a file or regular directory). "
                       f"It should be a symlink to the shared '{WORLDS_DIR_NAME}' directory.")
                self._add_status_message(msg, is_warning=True)
                if messagebox.askyesno("Resolve Conflict?", f"{msg}\\n\\nDelete the existing item and attempt to create a symlink? This will delete the item at '{target_link_path}'."):
                    try:
                        if os.path.isdir(target_link_path): # For directories
                            import shutil
                            shutil.rmtree(target_link_path)
                        else: # For files
                            os.remove(target_link_path)
                        self._add_status_message(f"Removed conflicting item: {target_link_path}")
                    except OSError as e_del:
                        self._add_status_message(f"Error removing conflicting item '{target_link_path}': {e_del}", is_error=True)
                        return
                else:
                    return # User chose not to fix
        
        if link_exists_correctly:
            return

        self._add_status_message(f"Attempting to create symlink for '{WORLDS_DIR_NAME}' in '{server_name}'...")
        try:
            os.symlink(self.base_worlds_path, target_link_path, target_is_directory=True)
            self._add_status_message(f"Successfully created symlink: '{target_link_path}' -> '{self.base_worlds_path}'.")
        except OSError as e:
            error_msg = (f"Error creating symlink '{target_link_path}': {e}. "
                         "On Windows, this may require administrator privileges or Developer Mode to be enabled.")
            self._add_status_message(error_msg, is_error=True)
        except AttributeError: 
            error_msg = ("Error: os.symlink is not available or failed. "
                         "Cannot create directory link automatically.")
            self._add_status_message(error_msg, is_error=True)

    def _ensure_config_symlinks(self, server_dir_path):
        config_files = ["allowlist.json", "permissions.json", "server.properties"]
        config_dir = os.path.join(self.script_dir, "config")
        print(f"Debug: config_dir = {config_dir}")
        for fname in config_files:
            target_link_path = os.path.join(server_dir_path, fname)
            config_file_path = os.path.join(config_dir, fname)
            
            # Only create symlink if config file exists in config_dir
            if not os.path.exists(config_file_path):
                self._add_status_message(f"Config file '{fname}' not found in config directory. Skipping symlink.", is_warning=True)
                continue
            need_symlink = True
            if os.path.lexists(target_link_path):
                if os.path.islink(target_link_path):
                    link_target = os.readlink(target_link_path)
                    abs_link_target = os.path.abspath(os.path.join(os.path.dirname(target_link_path), link_target))
                    abs_config_file = os.path.abspath(config_file_path)
                    # Remove \\?\ prefix for Windows long paths if present
                    if abs_link_target.startswith('\\\\?\\'):
                        abs_link_target = abs_link_target[4:]
                    if abs_config_file.startswith('\\\\?\\'):
                        abs_config_file = abs_config_file[4:]
                    if abs_link_target == abs_config_file:
                        self._add_status_message(f"'{fname}' symlink in '{os.path.basename(server_dir_path)}' is correct.")
                        need_symlink = False
                    else:
                        self._add_status_message(f"'{fname}' symlink in '{os.path.basename(server_dir_path)}' points to wrong target. Removing.")
                        os.unlink(target_link_path)
                else:
                    self._add_status_message(f"'{fname}' exists in '{os.path.basename(server_dir_path)}' but is not a symlink. Removing.")
                    if os.path.isdir(target_link_path):
                        import shutil
                        shutil.rmtree(target_link_path)
                    else:
                        os.remove(target_link_path)
            if need_symlink:
                try:
                    os.symlink(config_file_path, target_link_path)
                    self._add_status_message(f"Created symlink: '{target_link_path}' -> '{config_file_path}'")
                except Exception as e:
                    self._add_status_message(f"Failed to create symlink for '{fname}': {e}", is_error=True)

    def _find_existing_bedrock_server_process(self):
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                if proc.info['name'] and 'bedrock_server.exe' in proc.info['name'].lower():
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _load_existing_bedrock_log(self, proc):
        # Try to find logs/latest.log or stdout log in the process working directory
        try:
            cwd = proc.cwd()
            log_path = os.path.join(cwd, 'logs', 'latest.log')
            if os.path.isfile(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        self._add_status_message(line.rstrip())
            else:
                # If no logs/latest.log, try to find any .log file
                for fname in os.listdir(cwd):
                    if fname.lower().endswith('.log'):
                        with open(os.path.join(cwd, fname), 'r', encoding='utf-8', errors='ignore') as f:
                            for line in f:
                                self._add_status_message(line.rstrip())
                        break
        except Exception as e:
            self._add_status_message(f"Failed to load existing bedrock_server log: {e}", is_warning=True)

    def _attach_to_existing_bedrock_server(self, proc):
        # Show prompt and allow button to stop the process
        self._add_status_message(f"Detected running bedrock_server.exe (PID: {proc.pid}), cannot show real-time log, but loaded existing log.")
        self.server_process = proc  # Store psutil.Process object
        self.start_server_button.config(text="Stop Bedrock Server")
        self._load_existing_bedrock_log(proc)

    def _show_latest_bedrock_release_version(self):
        import urllib.request
        import json
        try:
            url = "https://raw.githubusercontent.com/kittizz/bedrock-server-downloads/main/bedrock-server-downloads.json"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.load(response)
            releases = data.get("release", {})
            if not releases:
                self._add_status_message("Could not get Bedrock Server release version info.", is_warning=True)
                self.latest_bedrock_version = None
                self.latest_bedrock_url = None
                self._update_download_button_state()
                return
            # Get the largest version number (string sorting is not always correct, need to convert to tuple)
            def version_tuple(v):
                return tuple(int(x) for x in v.split('.'))
            latest_version = max(releases.keys(), key=version_tuple)
            self.latest_bedrock_version = latest_version
            self.latest_bedrock_url = releases[latest_version]["windows"]["url"]
            self._add_status_message(f"Bedrock Server Latest Release：{latest_version}")
            folder_name = f"bedrock-server-{latest_version}"
            dest_dir = os.path.join(self.script_dir, folder_name)
            if os.path.exists(dest_dir):
                msg = "Latest version already downloaded."
                current_server_name = self.current_server_var.get()
                if current_server_name and current_server_name.startswith("bedrock-server-"):
                    current_version = current_server_name.replace('bedrock-server-', '')
                elif current_server_name:
                    current_version = current_server_name
                else:
                    current_version = None
                if current_server_name != folder_name:
                    if current_version:
                        msg += f" Current version is {current_version}, consider switching to latest {latest_version}."
                    else:
                        msg += f" No version selected, consider switching to latest {latest_version}."
                self._add_status_message(msg)
            else:
                self._add_status_message("Latest version not downloaded yet, please click the button to download.", is_warning=True)
        except Exception as e:
            self._add_status_message(f"Failed to fetch Bedrock Server latest release: {e}", is_warning=True)
            self.latest_bedrock_version = None
            self.latest_bedrock_url = None
        self._update_download_button_state()

    def _download_latest_bedrock_server(self):
        import threading
        import os
        import tkinter as tk
        from tkinter import ttk, filedialog
        if not self.latest_bedrock_version or not self.latest_bedrock_url:
            self._add_status_message("Could not get latest version info, please try again later.", is_error=True)
            return
        folder_name = f"bedrock-server-{self.latest_bedrock_version}"
        dest_dir = os.path.join(self.script_dir, folder_name)
        if os.path.exists(dest_dir):
            self._add_status_message(f"Directory {folder_name} already exists, no need to download.", is_warning=True)
            self._update_download_button_state()
            return
        zip_name = f"bedrock-server-{self.latest_bedrock_version}.zip"
        zip_path = os.path.join(self.script_dir, zip_name)
        def do_download():
            try:
                self._add_status_message(f"Downloading {zip_name} using PowerShell ...")
                import subprocess
                import webbrowser
                # Create progress bar window (only shows downloading)
                progress_win = tk.Toplevel(self.root)
                progress_win.title("Download Progress")
                ttk.Label(progress_win, text=f"Downloading {zip_name} (using PowerShell Invoke-WebRequest)").pack(padx=10, pady=10)
                progress_label = ttk.Label(progress_win, text="Downloading... Please wait")
                progress_label.pack(padx=10, pady=10)
                progress_win.grab_set()
                progress_win.transient(self.root)
                progress_win.resizable(False, False)
                self.root.update_idletasks()
                # Use PowerShell Invoke-WebRequest to download, force show Verbose
                ps_cmd = f"$VerbosePreference = 'Continue'; Invoke-WebRequest -Uri \"{self.latest_bedrock_url}\" -OutFile \"{zip_path}\" -UseBasicParsing -Verbose"
                full_cmd = ["powershell", "-NoProfile", "-Command", ps_cmd]
                self._add_status_message(f"PowerShell command: {ps_cmd}")
                proc = subprocess.Popen(
                    full_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    shell=False
                )
                ps_output = []
                while True:
                    line = proc.stdout.readline()
                    if not line and proc.poll() is not None:
                        break
                    if line:
                        self._add_status_message(line.rstrip())
                        ps_output.append(line.rstrip())
                rc = proc.wait()
                progress_win.destroy()
                if rc != 0:
                    self._add_status_message(f"PowerShell download failed output:\n" + '\n'.join(ps_output), is_error=True)
                    raise RuntimeError(f"PowerShell download failed, exit code {rc}")
                self._add_status_message(f"Download completed: {zip_path}, extracting...")
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(dest_dir)
                self._add_status_message(f"Extracted successfully to {dest_dir}")
                os.remove(zip_path)
                self._add_status_message(f"To switch to the new version, use the 'Switch Version' button to select {folder_name}.")
                self._update_download_button_state()
            except Exception as e:
                self._add_status_message(f"Download or extraction failed: {e}", is_error=True)
                try:
                    progress_win.destroy()
                except:
                    pass
                if messagebox.askyesno("Download Failed", "Download failed. Open download page in browser?\n\nURL:\n" + str(self.latest_bedrock_url)):
                    webbrowser.open(self.latest_bedrock_url)
                if messagebox.askyesno("Manual Extraction", "Do you want to manually select a downloaded ZIP file to extract?"):
                    zip_file = filedialog.askopenfilename(
                        title="Select downloaded Bedrock Server ZIP file",
                        filetypes=[("ZIP files", "*.zip")]
                    )
                    if zip_file:
                        try:
                            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                                zip_ref.extractall(dest_dir)
                            self._add_status_message(f"Manual extraction completed, installed to {dest_dir}")
                            self._add_status_message(f"To switch to the new version, use the 'Switch Version' button to select {folder_name}.")
                            self._update_download_button_state()
                        except Exception as e2:
                            self._add_status_message(f"Manual extraction failed: {e2}", is_error=True)
                        return
                return
        threading.Thread(target=do_download, daemon=True).start()

    def _initial_setup_and_checks(self, check_newer_version_prompt=True):
        self._clear_status()
        self._add_status_message("Starting checks...")
        
        if not self._ensure_script_worlds_dir_exists():
            self._add_status_message("Cannot proceed without base worlds directory.", is_error=True)
            return

        all_server_infos = self._get_server_directories_info()

        if not all_server_infos:
            self._add_status_message("No Bedrock server directories found (e.g., bedrock-server-X.Y.Z).", is_warning=True)
            self.current_server_var.set("")
            self._save_config(None)
            return

        latest_server_info = all_server_infos[0]
        configured_server_name = self._load_config()
        current_selected_server_info = None

        if configured_server_name:
            for s_info in all_server_infos:
                if s_info["name"] == configured_server_name:
                    current_selected_server_info = s_info
                    break
        
        final_server_to_use_info = None

        if current_selected_server_info:
            # 直接維持原本設定的 server，不再詢問是否切換新版
            final_server_to_use_info = current_selected_server_info
            if configured_server_name == final_server_to_use_info["name"]:
                self._add_status_message(f"Current server '{current_selected_server_info['name']}' is up-to-date or preferred.")
        else:
            final_server_to_use_info = latest_server_info
            if configured_server_name: 
                self._add_status_message(f"Previously configured server '{configured_server_name}' not found/valid. Defaulting to latest: {latest_server_info['name']}.", is_warning=True)
                messagebox.showinfo("Server Selection Changed", f"Previously configured server '{configured_server_name}' was not found or is no longer valid. Switched to the latest available: '{latest_server_info['name']}'.")
            else:
                self._add_status_message(f"No previous configuration. Defaulting to latest server: {latest_server_info['name']}.")
                messagebox.showinfo("Server Selection", f"Selected server set to the latest available: '{latest_server_info['name']}'.")

        if final_server_to_use_info:
            self.current_server_var.set(final_server_to_use_info["name"])
            self._save_config(final_server_to_use_info["name"])
            self._add_status_message(f"Selected server: {final_server_to_use_info['name']}.")
            self._check_and_create_worlds_link(final_server_to_use_info["path"])
            self._ensure_config_symlinks(final_server_to_use_info["path"])
            try:
                import psutil
            except ImportError:
                self._add_status_message("Missing psutil package, cannot auto-detect running bedrock_server.exe.", is_warning=True)
                return
            proc = self._find_existing_bedrock_server_process()
            if proc:
                self._attach_to_existing_bedrock_server(proc)
            self._check_autostart_status()
        else:
            self.current_server_var.set("")
            self._save_config(None)
            self._add_status_message("Could not determine a server directory to use.", is_warning=True)
            self._check_autostart_status()

        self._show_latest_bedrock_release_version()

    def _switch_version_directory(self):
        server_infos = self._get_server_directories_info()
        if not server_infos:
            messagebox.showinfo("Switch Version", "No Bedrock server directories found to select from.", parent=self.root)
            return
        select_window = tk.Toplevel(self.root)
        select_window.title("Switch Version Directory")
        select_window.transient(self.root)
        select_window.grab_set()
        ttk.Label(select_window, text="Available server directories:").pack(pady=(10,5), padx=10)
        listbox_frame = ttk.Frame(select_window)
        listbox_frame.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        listbox = tk.Listbox(listbox_frame, exportselection=False, height=10)
        for s_info in server_infos:
            listbox.insert(tk.END, s_info["name"])
        current_server_name = self.current_server_var.get()
        if current_server_name:
            try:
                names_only = [s_info["name"] for s_info in server_infos]
                current_idx = names_only.index(current_server_name)
                listbox.select_set(current_idx)
                listbox.see(current_idx)
                listbox.activate(current_idx)
            except ValueError:
                pass
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=listbox.yview)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox['yscrollcommand'] = list_scrollbar.set
        def on_select():
            selected_indices = listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("Selection Error", "Please select a server directory.", parent=select_window)
                return
            selected_server_name = listbox.get(selected_indices[0])
            self._add_status_message(f"Switching version to: {selected_server_name}...")
            self._save_config(selected_server_name)
            self._initial_setup_and_checks(check_newer_version_prompt=False)
            if self.current_server_var.get() == selected_server_name:
                self._add_status_message(f"Successfully switched and refreshed for version: {selected_server_name}.")
            else:
                self._add_status_message(f"Version switch initiated for {selected_server_name}. Check status for details.", is_warning=True)
            select_window.destroy()
        def on_cancel():
            select_window.destroy()
        button_frame = ttk.Frame(select_window)
        button_frame.pack(pady=(5,10), padx=10)
        select_button = ttk.Button(button_frame, text="Select", command=on_select)
        select_button.pack(side=tk.LEFT, padx=5)
        cancel_button = ttk.Button(button_frame, text="Cancel", command=on_cancel)
        cancel_button.pack(side=tk.LEFT, padx=5)
        select_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (select_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (select_window.winfo_height() // 2)
        select_window.geometry(f"+{x}+{y}")
        select_window.focus_set()


    def _toggle_bedrock_server(self):
        current_button_text = self.start_server_button.cget("text")
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")
        # server_dir is primarily for _start_bedrock_server direct start, 
        # but script_path is needed by _execute_stop_sequence.
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())

        if current_button_text in ("Stop Bedrock Server"):
            self._add_status_message("=== Attempting to stop Bedrock Server... ===")
            # Disable button while stopping to prevent multiple clicks
            # self.start_server_button.config(state=tk.DISABLED) 
            # Re-enabling is handled by _check_autostart_status or can be added in finally of thread
            threading.Thread(target=self._execute_stop_sequence, args=(script_path,), daemon=True).start()
        else:
            self._start_bedrock_server()

    def _execute_stop_sequence(self, script_path):
        cflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        successfully_stopped_via_service = False

        try:
            # 1. Check service status
            self._add_status_message(f"Checking status of service '{SERVICE_NAME}'...")
            status_args = [sys.executable, script_path, "--status-service"]
            status_proc = subprocess.Popen(status_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
            status_stdout, status_stderr = status_proc.communicate(timeout=20)
            service_status_rc = status_proc.returncode
            self._add_status_message(f"Service status check: RC={service_status_rc}")
            if status_stdout:
                self._add_status_message(f"Status stdout:\n{status_stdout.strip()}")
            if status_stderr:
                self._add_status_message(f"Status stderr:\n{status_stderr.strip()}", is_warning=bool(status_stderr.strip()))

            # 2. Attempt to stop via service if appropriate
            if service_status_rc in (0, 2, 3): # 0=running, 2=stopped (harmless to stop again), 3=unknown
                self._add_status_message(f"Attempting to stop service '{SERVICE_NAME}' (current status RC={service_status_rc})...")
                stop_service_args = [sys.executable, script_path, "--stop-service"]
                stop_service_proc = subprocess.Popen(stop_service_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=cflags)
                s_out, _ = stop_service_proc.communicate(timeout=30)
                self._add_status_message(f"Stop service command output:\n{s_out.strip()}")
                if stop_service_proc.returncode == 0:
                    self._add_status_message(f"Service '{SERVICE_NAME}' stop command issued successfully.")
                    successfully_stopped_via_service = True
                else:
                    self._add_status_message(f"Service '{SERVICE_NAME}' stop command failed or reported an issue (RC={stop_service_proc.returncode}).", is_warning=True)
            
            # 3. If not successfully stopped by service, or if service was not in a state to be stopped by manager, use fallback.
            if not successfully_stopped_via_service:
                if service_status_rc == 1: # Service does not exist
                    self._add_status_message(f"Service '{SERVICE_NAME}' not found. Attempting 'run_bedrock_server.py --stop'.")
                elif service_status_rc == 4: # Query failed
                    self._add_status_message(f"Service '{SERVICE_NAME}' status query failed. Attempting 'run_bedrock_server.py --stop'.", is_warning=True)
                else: # Service was 0,2,3 but --stop-service failed, or other status_rc
                    self._add_status_message("Service stop failed or not applicable. Attempting 'run_bedrock_server.py --stop' as fallback.")

                # Directly use run_bedrock_server.py --stop as the fallback
                self._add_status_message("Executing 'run_bedrock_server.py --stop' for process termination.")
                fallback_stop_args = [sys.executable, script_path, "--stop"]
                fallback_proc = subprocess.Popen(fallback_stop_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=cflags)
                f_out, _ = fallback_proc.communicate(timeout=30)
                self._add_status_message(f"'run_bedrock_server.py --stop' output:\\n{f_out.strip()}")
                if fallback_proc.returncode == 0:
                     self._add_status_message("'run_bedrock_server.py --stop' completed.")
                else:
                     self._add_status_message(f"'run_bedrock_server.py --stop' completed with issues (RC={fallback_proc.returncode}).", is_warning=True)

        except subprocess.TimeoutExpired:
            self._add_status_message("A stop operation (service status/stop, or fallback stop) timed out.", is_error=True)
        except Exception as e:
            self._add_status_message(f"Overall error during stop sequence: {e}", is_error=True)
        finally:
            self.server_process = None # Clear any Popen object from a direct start
            self.root.after(200, self._check_autostart_status)
            self._update_server_related_buttons_state()

    def _start_bedrock_server(self):
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")

        if not os.path.isfile(script_path):
            self._add_status_message("run_bedrock_server.py not found!", is_error=True)
            return
        if not os.path.isdir(server_dir):
            self._add_status_message(f"Server directory '{server_dir}' not found!", is_error=True)
            return

        # Check service status first
        try:
            status_proc = subprocess.Popen(
                [sys.executable, script_path, "--status-service"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            _, _ = status_proc.communicate()
            service_status_returncode = status_proc.returncode
        except Exception as e:
            self._add_status_message(f"Failed to check service status: {e}", is_warning=True)
            service_status_returncode = -1 # Indicate failure to check

        def run_and_capture_service_start():
            self._add_status_message("=== Starting Bedrock Server (via service) ===")
            try:
                # Use --start-service
                self.server_process = subprocess.Popen(
                    [sys.executable, script_path, "--start-service"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                # Capture and display output
                for line in self.server_process.stdout:
                    self._add_status_message(line.rstrip())
                self.server_process.wait()
                self._add_status_message(f"=== Bedrock Server service operation finished, exit code: {self.server_process.returncode} ===")
                # After service start attempt, re-check autostart status to update buttons correctly
                self.root.after(5000, self._check_autostart_status)
                # Note: self.server_process here is for the script call, not bedrock_server.exe itself
                # The actual bedrock_server.exe is managed by the service.
            except Exception as e:
                self._add_status_message(f"Failed to start Bedrock Server service: {e}", is_error=True)
            self._update_server_related_buttons_state()
        def run_and_capture_direct_start():
            self._add_status_message("=== Starting bedrock_server.exe (direct) ===")
            try:
                self.server_process = subprocess.Popen(
                    [sys.executable, script_path, "--start", server_dir],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                for line in self.server_process.stdout:
                    self._add_status_message(line.rstrip())
                self.server_process.wait()
                self._add_status_message(f"=== bedrock_server.exe finished, exit code: {self.server_process.returncode} ===")
                self.server_process = None
                self.start_server_button.config(text="Start Bedrock Server")
            except Exception as e:
                self._add_status_message(f"Failed to start or run bedrock_server.exe (direct): {e}", is_error=True)
                self.server_process = None
                self.start_server_button.config(text="Start Bedrock Server")
            self._update_server_related_buttons_state()
        if service_status_returncode in (0, 2): # Service is installed (0 = running, 2 = installed but not running)
            self._add_status_message("Service is installed. Attempting to start via service manager...")
            self.start_server_button.config(text="Stop Bedrock Server") # Assume it will start, _check_autostart_status will correct if needed
            self.server_thread = threading.Thread(target=run_and_capture_service_start, daemon=True)
            self.server_thread.start()
        else:
            self._add_status_message("Service not installed or status unknown. Attempting direct start...")
            self.start_server_button.config(text="Stop Bedrock Server") # Assume it will start
            self.server_thread = threading.Thread(target=run_and_capture_direct_start, daemon=True)
            self.server_thread.start()
        self._update_server_related_buttons_state()

    def _update_change_server_button_state(self):
        # 只有未啟動伺服器且未設定自動啟動時，才能切換版本
        btn_text = self.start_server_button.cget("text")
        if btn_text in ("Stop Bedrock Server",) or self.is_autostart_enabled:
            self.switch_version_button.config(state=tk.DISABLED)
        else:
            self.switch_version_button.config(state=tk.NORMAL)

    def _update_server_related_buttons_state(self):
        # 只有未啟動伺服器且未設定自動啟動時，才能切換版本與備份
        btn_text = self.start_server_button.cget("text")
        if self.is_autostart_enabled:
            self.switch_version_button.config(state=tk.DISABLED)
            self.backup_button.config(state=tk.DISABLED)
            self.start_server_button.config(state=tk.DISABLED)  # 設定開機自動啟動時，啟動/停止按鈕也 disable
            self.auto_start_button.config(state=tk.NORMAL)
        else:
            if btn_text in ("Stop Bedrock Server",):
                self.switch_version_button.config(state=tk.DISABLED)
                self.backup_button.config(state=tk.DISABLED)
                self.start_server_button.config(state=tk.NORMAL)
                self.auto_start_button.config(state=tk.DISABLED)
            else:
                self.switch_version_button.config(state=tk.NORMAL)
                self.backup_button.config(state=tk.NORMAL)
                self.start_server_button.config(state=tk.NORMAL)
                self.auto_start_button.config(state=tk.NORMAL)

    def _check_autostart_status(self):
        import sys
        import subprocess
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")

        if not os.path.isfile(script_path) or not os.path.isdir(server_dir):
            self.auto_start_button.config(text="Enable Autostart", command=self._toggle_autostart_bedrock_server, state=tk.DISABLED)
            self.is_autostart_enabled = False
            self._update_change_server_button_state()
            return
        try:
            proc = subprocess.Popen([
                sys.executable, script_path, "--status-service"
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _ = proc.communicate()
            status_text = output.strip().lower()
            print("status_text:", status_text)
            print("proc.returncode:", proc.returncode)
            if proc.returncode in (0, 2):
                self.auto_start_button.config(text="Disable Autostart", command=lambda: self._toggle_autostart_bedrock_server(remove=True), state=tk.NORMAL)
                self.is_autostart_enabled = True
                if proc.returncode == 0:
                    self.start_server_button.config(text="Stop Bedrock Server")
                elif "but not running" in status_text:
                    self.start_server_button.config(text="Start Bedrock Server")
            else:
                self.auto_start_button.config(text="Enable Autostart", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)
                self.is_autostart_enabled = False
            self._update_server_related_buttons_state()
        except Exception as e:
            self._add_status_message(f"Failed to check autostart status: {e}", is_warning=True)
            self.auto_start_button.config(text="Enable Autostart", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)
            self.is_autostart_enabled = False
            self._update_server_related_buttons_state()

    def _toggle_autostart_bedrock_server(self, remove=False):
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")

        if not os.path.isfile(script_path):
            self._add_status_message("run_bedrock_server.py not found!", is_error=True)
            return
        if not os.path.isdir(server_dir):
            self._add_status_message(f"Server directory \'{server_dir}\' not found!", is_error=True)
            return

        try:
            if remove:
                self._add_status_message("Stopping service (if running)...")
                stop_args = [sys.executable, script_path, "--stop-service", server_dir]
                stop_proc = subprocess.Popen(stop_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                output, _ = stop_proc.communicate()
                self._add_status_message(output.strip())
                # We don't necessarily care about the return code of stop-service here,
                # as it might not be running, which is fine. The main goal is to remove it.

                self._add_status_message("Removing autostart...")
                remove_args = [sys.executable, script_path, "--remove-service", server_dir]
                proc = subprocess.Popen(remove_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            else:
                self._add_status_message("Setting up autostart...")
                create_args = [sys.executable, script_path, "--create-service", server_dir]
                proc = subprocess.Popen(create_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            
            output, _ = proc.communicate()
            self._add_status_message(output.strip())
            if proc.returncode == 0:
                if remove:
                    self._add_status_message("Autostart removed.")
                    self.auto_start_button.config(text="Enable Autostart", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)
                    self.start_server_button.config(text="Start Bedrock Server")
                else:
                    self._add_status_message("Autostart setup complete.")
                    self.auto_start_button.config(text="Disable Autostart", command=lambda: self._toggle_autostart_bedrock_server(remove=True), state=tk.NORMAL)
                    self._start_bedrock_server()
            else:
                self._add_status_message("Autostart operation failed.", is_error=True)
        except Exception as e:
            self._add_status_message(f"Autostart operation failed: {e}", is_error=True)
        self._check_autostart_status()

    def _backup_data(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_filename = f"backup-{timestamp}.zip"
        backup_filepath = os.path.join(self.script_dir, backup_filename)
        worlds_dir_to_backup = self.base_worlds_path
        config_dir_to_backup = os.path.join(self.script_dir, "config")
        items_to_backup = {
            WORLDS_DIR_NAME: worlds_dir_to_backup,
            "config": config_dir_to_backup
        }
        try:
            self._add_status_message(f"Starting backup to {backup_filename}...")
            with zipfile.ZipFile(backup_filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
                for item_name, item_path in items_to_backup.items():
                    if os.path.exists(item_path):
                        if os.path.isdir(item_path):
                            self._add_status_message(f"Backing up '{item_name}' directory ('{item_path}')...")
                            for root, _, files in os.walk(item_path):
                                for file in files:
                                    file_abs_path = os.path.join(root, file)
                                    arcname = os.path.join(item_name, os.path.relpath(file_abs_path, item_path))
                                    zf.write(file_abs_path, arcname)
                            self._add_status_message(f"'{item_name}' directory backed up.")
                        elif os.path.isfile(item_path):
                            self._add_status_message(f"Backing up '{item_name}' file ('{item_path}')...")
                            zf.write(item_path, item_name)
                            self._add_status_message(f"'{item_name}' file backed up.")
                    else:
                        self._add_status_message(f"'{item_name}' not found at '{item_path}'. Skipping.", is_warning=True)
            self._add_status_message(f"Backup completed successfully: {backup_filepath}")
            messagebox.showinfo("Backup Complete", f"Backup created successfully at:\n{backup_filepath}", parent=self.root)
        except Exception as e:
            self._add_status_message(f"Backup failed: {e}", is_error=True)
            messagebox.showerror("Backup Failed", f"An error occurred during backup:\n{e}", parent=self.root)

    def _update_download_button_state(self):
        # 根據本地是否已有最新版自動 enable/disable 下載按鈕
        if not self.latest_bedrock_version:
            self.download_latest_button.config(state=tk.DISABLED)
            return
        folder_name = f"bedrock-server-{self.latest_bedrock_version}"
        dest_dir = os.path.join(self.script_dir, folder_name)
        if os.path.exists(dest_dir):
            self.download_latest_button.config(state=tk.DISABLED)
        else:
            self.download_latest_button.config(state=tk.NORMAL)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        # This might happen if the shell32 library or IsUserAnAdmin function is not available,
        # though it's standard on Windows.
        return False

def main():
    if not is_admin():
        # Re-run the script with admin rights
        try:
            # Parameters for ShellExecuteW:
            # None: hwnd (no parent window)
            # "runas": lpOperation (request elevation)
            # sys.executable: lpFile (the Python interpreter)
            # ' '.join(sys.argv): lpParameters (the script path and any arguments) # Corrected: \' \'.join to ' '.join
            # None: lpDirectory
            # 1: nShowCmd (SW_SHOWNORMAL)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, ' '.join(sys.argv), None, 1) # Corrected: \' \'.join to ' '.join
        except Exception as e:
            messagebox.showerror("Error", f"Failed to elevate privileges: {e}\\\\nPlease run as administrator manually.") # Corrected: \\\\\\\\n to \\n
        sys.exit(0) # Exit the non-elevated instance

    root = tk.Tk()
    app = ServerManagerApp(root)
    root.minsize(550, 250) # Adjusted minsize for better layout
    root.mainloop()

if __name__ == "__main__":
    main()
