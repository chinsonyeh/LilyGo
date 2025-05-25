import tkinter as tk
from tkinter import ttk, messagebox
import os
import re
import configparser
import sys # For determining if running as a script or frozen
import ctypes # For checking admin rights and re-launching
import subprocess # Fallback or alternative for re-launching if needed

# Constants
CONFIG_FILE_NAME = "lilygo_config.ini"
SERVER_DIR_PREFIX = "bedrock-server-"
WORLDS_DIR_NAME = "worlds"
CONFIG_SECTION = "Settings"
CONFIG_KEY_CURRENT_SERVER = "current_server_directory"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

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

        self._setup_ui()
        self._initial_setup_and_checks()

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Server Directory Label and Entry
        ttk.Label(main_frame, text="Selected Server Directory:").grid(row=0, column=0, sticky=tk.W, pady=(0,5))
        self.server_entry = ttk.Entry(main_frame, textvariable=self.current_server_var, state="readonly", width=70)
        self.server_entry.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0,10))

        # Refresh Button
        self.refresh_button = ttk.Button(main_frame, text="Re-scan and Check Server", command=self._initial_setup_and_checks)
        self.refresh_button.grid(row=2, column=0, sticky=tk.W, pady=(0,10))
        
        # 開機自動啟動按鈕（中間）
        self.auto_start_button = ttk.Button(main_frame, text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server)
        self.auto_start_button.grid(row=2, column=1, sticky=tk.E, pady=(0,10))

        # 啟動 Bedrock Server 按鈕（最右側）
        self.server_process = None
        self.server_thread = None
        self.start_server_button = ttk.Button(main_frame, text="啟動 Bedrock Server", command=self._toggle_bedrock_server)
        self.start_server_button.grid(row=2, column=2, sticky=tk.E, pady=(0,10))

        # Status Label
        ttk.Label(main_frame, text="Status Log:").grid(row=3, column=0, sticky=tk.W, pady=(5,0))
        
        # Status Text Area with Scrollbar
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0,10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)

        self.status_text = tk.Text(status_frame, wrap=tk.WORD, height=10, state='disabled', relief=tk.SUNKEN, borderwidth=1)
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.status_text['yscrollcommand'] = scrollbar.set

        # Configure main_frame column and row weights for expansion
        main_frame.columnconfigure(0, weight=0)
        main_frame.columnconfigure(1, weight=0)
        main_frame.columnconfigure(2, weight=1)  # 讓最右側按鈕與 text box 右側對齊
        main_frame.rowconfigure(4, weight=1) # Allow status_frame (and Text widget) to expand vertically

    def _add_status_message(self, message, is_error=False, is_warning=False):
        print(f"Status: {message}") # Log to console as well
        self.status_text.config(state='normal') # Enable editing to insert text
        # Split message by \n and insert each line as a new line
        lines = message.split('\n')
        for i, line in enumerate(lines):
            if self.status_text.index('end-1c') != '1.0' or i > 0:
                self.status_text.insert(tk.END, "\n")
            self.status_text.insert(tk.END, line)
        self.status_text.see(tk.END) # Scroll to the end
        self.status_text.config(state='disabled') # Disable editing again

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
            self._add_status_message(f"Script directory '{self.script_dir}' not found.", is_error=True) # Corrected: \'{self.script_dir}\' to '{self.script_dir}'
            return []
            
        for item in os.listdir(self.script_dir):
            item_path = os.path.join(self.script_dir, item)
            if os.path.isdir(item_path) and item.startswith(SERVER_DIR_PREFIX):
                version_str = item[len(SERVER_DIR_PREFIX):]
                try:
                    version_obj = self._parse_version_tuple(version_str)
                    server_dirs.append({"name": item, "version": version_obj, "path": item_path})
                except ValueError as e:
                    self._add_status_message(f"Warning: Could not parse version from '{item}': {e}. Skipping.", is_warning=True) # Corrected: \'{item}\' to '{item}'
        
        server_dirs.sort(key=lambda x: x["version"], reverse=True) # Newest first
        return server_dirs

    def _ensure_script_worlds_dir_exists(self):
        if not os.path.exists(self.base_worlds_path):
            try:
                os.makedirs(self.base_worlds_path)
                self._add_status_message(f"Created base '{WORLDS_DIR_NAME}' directory: {self.base_worlds_path}") # Corrected: \'{WORLDS_DIR_NAME}\' to '{WORLDS_DIR_NAME}'
            except OSError as e:
                self._add_status_message(f"Error creating base '{WORLDS_DIR_NAME}' dir: {e}", is_error=True) # Corrected: \'{WORLDS_DIR_NAME}\' to '{WORLDS_DIR_NAME}'
                return False
        elif not os.path.isdir(self.base_worlds_path):
            self._add_status_message(f"Error: '{self.base_worlds_path}' exists but is not a directory.", is_error=True) # Corrected: \'{self.base_worlds_path}\' to '{self.base_worlds_path}'
            return False
        return True

    def _check_and_create_worlds_link(self, server_dir_path):
        target_link_path = os.path.join(server_dir_path, WORLDS_DIR_NAME)
        server_name = os.path.basename(server_dir_path)

        if not os.path.exists(self.base_worlds_path) or not os.path.isdir(self.base_worlds_path):
            self._add_status_message(f"Source '{WORLDS_DIR_NAME}' ('{self.base_worlds_path}') not found. Cannot create link.", is_warning=True) # Corrected: \'{WORLDS_DIR_NAME}\' (\'{self.base_worlds_path}\') to '{WORLDS_DIR_NAME}' ('{self.base_worlds_path}')
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
                        msg = (f"Warning: '{WORLDS_DIR_NAME}' in '{server_name}' is a symlink but points to " # Corrected quotes
                               f"'{link_target}' (resolves to '{abs_link_target}') instead of '{abs_base_worlds}'.") # Corrected quotes
                        self._add_status_message(msg, is_warning=True)
                        if messagebox.askyesno("Fix Symlink?", f"{msg}\\\\n\\\\nDelete and attempt to recreate?"):
                            try:
                                os.unlink(target_link_path)
                                self._add_status_message(f"Removed incorrect symlink: {target_link_path}")
                            except OSError as e_unlink:
                                self._add_status_message(f"Error removing incorrect symlink '{target_link_path}': {e_unlink}", is_error=True) # Corrected: \'{target_link_path}\' to '{target_link_path}'
                                return
                        else:
                            return # User chose not to fix
                except OSError as e: # os.readlink can fail
                    msg = f"Warning: Could not read symlink at '{target_link_path}': {e}. It might be broken." # Corrected: \'{target_link_path}\' to '{target_link_path}'
                    self._add_status_message(msg, is_warning=True)
                    if messagebox.askyesno("Fix Broken Symlink?", f"{msg}\\\\n\\\\nDelete and attempt to recreate?"):
                        try:
                            os.unlink(target_link_path)
                            self._add_status_message(f"Removed broken symlink: {target_link_path}")
                        except OSError as e_unlink:
                            self._add_status_message(f"Error removing broken symlink '{target_link_path}': {e_unlink}", is_error=True) # Corrected: \'{target_link_path}\' to '{target_link_path}'
                            return
                    else:
                        return
            else: # Exists but is not a symlink
                msg = (f"Warning: '{target_link_path}' exists but is not a symlink (it's a file or regular directory). " # Corrected: \'{target_link_path}\' and (it\\\'s to (it's
                       f"It should be a symlink to the shared '{WORLDS_DIR_NAME}' directory.") # Corrected: \'{WORLDS_DIR_NAME}\' to '{WORLDS_DIR_NAME}'
                self._add_status_message(msg, is_warning=True)
                if messagebox.askyesno("Resolve Conflict?", f"{msg}\\\\n\\\\nDelete the existing item and attempt to create a symlink? This will delete the item at '{target_link_path}'."): # Corrected: \'{target_link_path}\' to '{target_link_path}'
                    try:
                        if os.path.isdir(target_link_path): # For directories
                            import shutil
                            shutil.rmtree(target_link_path)
                        else: # For files
                            os.remove(target_link_path)
                        self._add_status_message(f"Removed conflicting item: {target_link_path}")
                    except OSError as e_del:
                        self._add_status_message(f"Error removing conflicting item '{target_link_path}': {e_del}", is_error=True) # Corrected: \'{target_link_path}\' to '{target_link_path}'
                        return
                else:
                    return # User chose not to fix
        
        if link_exists_correctly:
            return

        self._add_status_message(f"Attempting to create symlink for '{WORLDS_DIR_NAME}' in '{server_name}'...") # Corrected: \'{WORLDS_DIR_NAME}\' in \'{server_name}\' to '{WORLDS_DIR_NAME}' in '{server_name}'
        try:
            os.symlink(self.base_worlds_path, target_link_path, target_is_directory=True)
            self._add_status_message(f"Successfully created symlink: '{target_link_path}' -> '{self.base_worlds_path}'.") # Corrected: \'{target_link_path}\' -> \'{self.base_worlds_path}\' to '{target_link_path}' -> '{self.base_worlds_path}'
        except OSError as e:
            error_msg = (f"Error creating symlink '{target_link_path}': {e}. " # Corrected: \'{target_link_path}\' to '{target_link_path}'
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
        # 嘗試尋找該進程的工作目錄下的 logs/latest.log 或 stdout log
        try:
            cwd = proc.cwd()
            log_path = os.path.join(cwd, 'logs', 'latest.log')
            if os.path.isfile(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        self._add_status_message(line.rstrip())
            else:
                # 若無 logs/latest.log，嘗試尋找 stdout log
                for fname in os.listdir(cwd):
                    if fname.lower().endswith('.log'):
                        with open(os.path.join(cwd, fname), 'r', encoding='utf-8', errors='ignore') as f:
                            for line in f:
                                self._add_status_message(line.rstrip())
                        break
        except Exception as e:
            self._add_status_message(f"無法載入現有 bedrock_server log: {e}", is_warning=True)

    def _attach_to_existing_bedrock_server(self, proc):
        # 顯示提示，並允許按鈕關閉該進程
        self._add_status_message(f"偵測到已執行的 bedrock_server.exe (PID: {proc.pid})，無法即時顯示 log，但已載入現有 log。", is_warning=True)
        self.server_process = proc  # 儲存 psutil.Process 物件
        self.start_server_button.config(text="關閉 Bedrock Server")
        self._load_existing_bedrock_log(proc)

    def _initial_setup_and_checks(self):
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
            # Check if the configured server is older than the latest found on disk
            if current_selected_server_info["name"] != latest_server_info["name"] and \
               latest_server_info["version"] > current_selected_server_info["version"]:
                msg = (f"A newer server version '{latest_server_info['name']}' is available.\\\\n" # Corrected: \'{latest_server_info[\\\'name\\\']}\\\' to '{latest_server_info['name']}'
                       f"Your currently selected version is '{current_selected_server_info['name']}'.\\\\n\\\\n" # Corrected: \'{current_selected_server_info[\\\'name\\\']}\\\' to '{current_selected_server_info['name']}'
                       "Do you want to switch to the newer version?")
                if messagebox.askyesno("Update Available", msg):
                    final_server_to_use_info = latest_server_info
                    self._add_status_message(f"User opted to switch to newer server: {latest_server_info['name']}.") # Corrected: latest_server_to_use_info[\'name\'] to latest_server_info['name'] (and quotes)
                else:
                    final_server_to_use_info = current_selected_server_info
                    self._add_status_message(f"User opted to stay with server: {current_selected_server_info['name']}.") # Corrected: [\'name\'] to ['name']
            else:
                final_server_to_use_info = current_selected_server_info
                # Only add this message if it wasn't just set by user choice or defaulting
                if configured_server_name == final_server_to_use_info["name"]: # Check if it's the original config
                     self._add_status_message(f"Current server '{current_selected_server_info['name']}' is up-to-date or preferred.") # Corrected: \'{...[\'name\']}\' to '{...['name']}'
        else: # No valid configuration or configured server not found
            final_server_to_use_info = latest_server_info
            if configured_server_name: 
                 self._add_status_message(f"Previously configured server '{configured_server_name}' not found/valid. Defaulting to latest: {latest_server_info['name']}.", is_warning=True) # Corrected quotes
                 messagebox.showinfo("Server Selection Changed", f"Previously configured server '{configured_server_name}' was not found or is no longer valid. Switched to the latest available: '{latest_server_info['name']}'.") # Corrected quotes
            else:
                 self._add_status_message(f"No previous configuration. Defaulting to latest server: {latest_server_info['name']}.") # Corrected quotes
                 messagebox.showinfo("Server Selection", f"Selected server set to the latest available: '{latest_server_info['name']}'.") # Corrected quotes


        if final_server_to_use_info:
            self.current_server_var.set(final_server_to_use_info["name"])
            self._save_config(final_server_to_use_info["name"])
            self._add_status_message(f"Selected server: {final_server_to_use_info['name']}.") # Corrected quotes
            self._check_and_create_worlds_link(final_server_to_use_info["path"])
            self._ensure_config_symlinks(final_server_to_use_info["path"])
            # 新增：啟動時自動偵測現有 bedrock_server.exe
            try:
                import psutil
            except ImportError:
                self._add_status_message("缺少 psutil 套件，無法自動偵測現有 bedrock_server.exe。", is_warning=True)
                return
            proc = self._find_existing_bedrock_server_process()
            if proc:
                self._attach_to_existing_bedrock_server(proc)
            # 新增：查詢自動啟動狀態
            self._check_autostart_status()
        else:
            # This case should ideally not be reached if all_server_infos is not empty
            self.current_server_var.set("")
            self._save_config(None)
            self._add_status_message("Could not determine a server directory to use.", is_warning=True)
            self._check_autostart_status()

    def _toggle_bedrock_server(self):
        import threading
        import sys
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())
        def stop_server():
            try:
                # 無論 self.server_process 狀態，皆搜尋所有 bedrock_server.exe 並終止
                try:
                    import psutil
                    found = False
                    for proc in psutil.process_iter(['pid', 'name']):
                        if proc.info['name'] and 'bedrock_server.exe' in proc.info['name'].lower():
                            try:
                                proc.terminate()
                                proc.wait(timeout=10)
                                self._add_status_message(f"已終止 bedrock_server.exe (PID: {proc.pid})")
                                found = True
                            except Exception as e:
                                self._add_status_message(f"終止 bedrock_server.exe (PID: {proc.pid}) 失敗: {e}", is_error=True)
                    if not found:
                        self._add_status_message("未找到任何 bedrock_server.exe 進程。", is_warning=True)
                except ImportError:
                    # 若無 psutil 則 fallback 用 --stop
                    stop_proc = subprocess.Popen([sys.executable, script_path, "--stop"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in stop_proc.stdout:
                        self._add_status_message(line.rstrip())
                    stop_proc.wait()
                    self._add_status_message("=== bedrock_server.exe 已關閉 ===")
            except Exception as e:
                self._add_status_message(f"關閉 bedrock_server.exe 失敗: {e}", is_error=True)
            self.server_process = None
            self.start_server_button.config(text="啟動 Bedrock Server")
        # 判斷是否有任何 bedrock_server.exe 在執行
        try:
            import psutil
            any_running = any(
                proc.info['name'] and 'bedrock_server.exe' in proc.info['name'].lower()
                for proc in psutil.process_iter(['name'])
            )
        except ImportError:
            any_running = self.server_process and (hasattr(self.server_process, 'poll') and self.server_process.poll() is None or hasattr(self.server_process, 'is_running') and self.server_process.is_running())
        if any_running:
            self._add_status_message("=== 正在關閉 bedrock_server.exe... ===")
            threading.Thread(target=stop_server, daemon=True).start()
        else:
            self._start_bedrock_server()

    def _start_bedrock_server(self):
        import threading
        import sys
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")
        if not os.path.isfile(script_path):
            self._add_status_message("run_bedrock_server.py not found!", is_error=True)
            return
        if not os.path.isdir(server_dir):
            self._add_status_message(f"Server directory '{server_dir}' not found!", is_error=True)
            return
        def run_and_capture():
            self._add_status_message("=== 啟動 bedrock_server.exe ===")
            try:
                self.server_process = subprocess.Popen([sys.executable, script_path, "--start", server_dir],
                                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in self.server_process.stdout:
                    self._add_status_message(line.rstrip())
                self.server_process.wait()
                self._add_status_message(f"=== bedrock_server.exe 結束，退出碼: {self.server_process.returncode} ===")
                self.server_process = None
                self.start_server_button.config(text="啟動 Bedrock Server")
            except Exception as e:
                self._add_status_message(f"啟動或執行 bedrock_server.exe 失敗: {e}", is_error=True)
                self.server_process = None
                self.start_server_button.config(text="啟動 Bedrock Server")
        self.start_server_button.config(text="關閉 Bedrock Server")
        self.server_thread = threading.Thread(target=run_and_capture, daemon=True)
        self.server_thread.start()

    def _check_autostart_status(self):
        import sys
        import subprocess
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")
        if not os.path.isfile(script_path) or not os.path.isdir(server_dir):
            self.auto_start_button.config(text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server, state=tk.DISABLED)
            return
        try:
            proc = subprocess.Popen([
                sys.executable, script_path, "--status", "--service", server_dir
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _ = proc.communicate()
            status_text = output.strip()
            if proc.returncode == 0 and ("已設定" in status_text or "已存在" in status_text or "enabled" in status_text or "已啟用" in status_text):
                self.auto_start_button.config(text="關閉開機自動啟動", command=lambda: self._toggle_autostart_bedrock_server(remove=True), state=tk.NORMAL)
            else:
                self.auto_start_button.config(text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)
        except Exception as e:
            self._add_status_message(f"查詢開機自動啟動狀態失敗: {e}", is_warning=True)
            self.auto_start_button.config(text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)

    def _toggle_autostart_bedrock_server(self, remove=False):
        import sys
        import subprocess
        server_dir = os.path.join(self.script_dir, self.current_server_var.get())
        script_path = os.path.join(self.script_dir, "run_bedrock_server.py")
        if not os.path.isfile(script_path):
            self._add_status_message("run_bedrock_server.py not found!", is_error=True)
            return
        if not os.path.isdir(server_dir):
            self._add_status_message(f"Server directory '{server_dir}' not found!", is_error=True)
            return
        if remove:
            self._add_status_message("正在移除開機自動啟動...")
            args = [sys.executable, script_path, "--remove", "--service", server_dir]
        else:
            self._add_status_message("正在設定開機自動啟動...")
            args = [sys.executable, script_path, "--create", "--service", server_dir]
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _ = proc.communicate()
            self._add_status_message(output.strip())
            if proc.returncode == 0:
                if remove:
                    self._add_status_message("開機自動啟動已移除。")
                else:
                    self._add_status_message("開機自動啟動設定完成。")
            else:
                self._add_status_message("開機自動啟動操作失敗。", is_error=True)
        except Exception as e:
            self._add_status_message(f"開機自動啟動操作失敗: {e}", is_error=True)
        self._check_autostart_status()

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
