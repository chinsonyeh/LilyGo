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

        self._setup_ui()
        self._initial_setup_and_checks()

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Server Directory Label and Entry
        ttk.Label(main_frame, text="Selected Server Directory:").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0,5))
        self.server_entry = ttk.Entry(main_frame, textvariable=self.current_server_var, state="readonly", width=70)
        self.server_entry.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0,10))

        # Backup Button
        self.backup_button = ttk.Button(main_frame, text="備份", command=self._backup_data)
        self.backup_button.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=(0,5), pady=(0,10))

        # Change Server Button
        self.change_server_button = ttk.Button(main_frame, text="Change Server", command=self._select_server_directory)
        self.change_server_button.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=(0,10))
        
        # Auto-start Button
        self.auto_start_button = ttk.Button(main_frame, text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server)
        self.auto_start_button.grid(row=2, column=2, sticky=(tk.W, tk.E), padx=5, pady=(0,10))

        # Start/Stop Server Button
        self.server_process = None
        self.server_thread = None
        self.start_server_button = ttk.Button(main_frame, text="啟動 Bedrock Server", command=self._toggle_bedrock_server)
        self.start_server_button.grid(row=2, column=3, sticky=(tk.W, tk.E), padx=(5,0), pady=(0,10))

        # Status Label
        ttk.Label(main_frame, text="Status Log:").grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(5,0))
        
        # Status Text Area with Scrollbar
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0,10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)

        self.status_text = tk.Text(status_frame, wrap=tk.WORD, height=10, state='disabled', relief=tk.SUNKEN, borderwidth=1)
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.status_text['yscrollcommand'] = scrollbar.set

        # Configure main_frame column and row weights for expansion
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        main_frame.columnconfigure(3, weight=1)
        main_frame.rowconfigure(4, weight=1)

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
        self.start_server_button.config(text="停止 Bedrock Server")
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

    def _select_server_directory(self):
        server_infos = self._get_server_directories_info()
        if not server_infos:
            messagebox.showinfo("Change Server", "No Bedrock server directories found to select from.", parent=self.root)
            return

        select_window = tk.Toplevel(self.root)
        select_window.title("Select Server Directory")
        select_window.transient(self.root) # Set to be on top of the main window
        select_window.grab_set() # Make it modal

        ttk.Label(select_window, text="Available server directories:").pack(pady=(10,5), padx=10)

        listbox_frame = ttk.Frame(select_window)
        listbox_frame.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        
        listbox = tk.Listbox(listbox_frame, exportselection=False, height=10)
        for s_info in server_infos:
            listbox.insert(tk.END, s_info["name"])
        
        current_server_name = self.current_server_var.get()
        if current_server_name:
            try:
                # Get a list of names for index finding
                names_only = [s_info["name"] for s_info in server_infos]
                current_idx = names_only.index(current_server_name)
                listbox.select_set(current_idx)
                listbox.see(current_idx)
                listbox.activate(current_idx)
            except ValueError:
                pass # Current server not in list, do nothing

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
            
            self._add_status_message(f"Changing server to: {selected_server_name}...")
            self._save_config(selected_server_name)
            
            # Trigger a full refresh which will load the new config, update UI, and symlinks
            self._initial_setup_and_checks() 
            
            # _initial_setup_and_checks will set the final status, but we can confirm the change.
            # Check if the current_server_var actually changed to the selected one after refresh.
            if self.current_server_var.get() == selected_server_name:
                self._add_status_message(f"Successfully changed and refreshed for server: {selected_server_name}.")
            else:
                self._add_status_message(f"Server change initiated for {selected_server_name}. Check status for details.", is_warning=True)

            select_window.destroy()

        def on_cancel():
            select_window.destroy()

        button_frame = ttk.Frame(select_window)
        button_frame.pack(pady=(5,10), padx=10)

        select_button = ttk.Button(button_frame, text="Select", command=on_select)
        select_button.pack(side=tk.LEFT, padx=5)

        cancel_button = ttk.Button(button_frame, text="Cancel", command=on_cancel)
        cancel_button.pack(side=tk.LEFT, padx=5)

        # Center the Toplevel window
        select_window.update_idletasks() # Ensure window size is calculated
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

        if current_button_text in ("關閉 Bedrock Server", "停止 Bedrock Server"):
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
            # Schedule GUI update on the main thread
            self.root.after(200, self._check_autostart_status)

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
            # Button text will be updated by _check_autostart_status

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
                self.start_server_button.config(text="啟動 Bedrock Server")
            except Exception as e:
                self._add_status_message(f"Failed to start or run bedrock_server.exe (direct): {e}", is_error=True)
                self.server_process = None
                self.start_server_button.config(text="啟動 Bedrock Server")

        if service_status_returncode in (0, 2): # Service is installed (0 = running, 2 = installed but not running)
            self._add_status_message("Service is installed. Attempting to start via service manager...")
            self.start_server_button.config(text="停止 Bedrock Server") # Assume it will start, _check_autostart_status will correct if needed
            self.server_thread = threading.Thread(target=run_and_capture_service_start, daemon=True)
            self.server_thread.start()
        else:
            self._add_status_message("Service not installed or status unknown. Attempting direct start...")
            self.start_server_button.config(text="停止 Bedrock Server") # Assume it will start
            self.server_thread = threading.Thread(target=run_and_capture_direct_start, daemon=True)
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
                sys.executable, script_path, "--status-service"
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _ = proc.communicate()
            status_text = output.strip().lower()
            print("status_text:", status_text)
            print("proc.returncode:", proc.returncode)
            if proc.returncode in (0, 2):
                self.auto_start_button.config(text="關閉開機自動啟動", command=lambda: self._toggle_autostart_bedrock_server(remove=True), state=tk.NORMAL)
                # 若服務已安裝且正在執行，則啟動按鈕設為"停止 Bedrock Server"
                if proc.returncode == 0:
                    self.start_server_button.config(text="停止 Bedrock Server")
                # 若服務已安裝但未執行，則啟動按鈕設為"啟動 Bedrock Server"
                elif "but not running" in status_text:
                    self.start_server_button.config(text="啟動 Bedrock Server")
            else:
                self.auto_start_button.config(text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)
        except Exception as e:
            self._add_status_message(f"查詢開機自動啟動狀態失敗: {e}", is_warning=True)
            self.auto_start_button.config(text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)

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
                self._add_status_message("正在停止服務 (如果正在執行)...")
                stop_args = [sys.executable, script_path, "--stop-service", server_dir]
                stop_proc = subprocess.Popen(stop_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                output, _ = stop_proc.communicate()
                self._add_status_message(output.strip())
                # We don't necessarily care about the return code of stop-service here,
                # as it might not be running, which is fine. The main goal is to remove it.

                self._add_status_message("正在移除開機自動啟動...")
                remove_args = [sys.executable, script_path, "--remove-service", server_dir]
                proc = subprocess.Popen(remove_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            else:
                self._add_status_message("正在設定開機自動啟動...")
                create_args = [sys.executable, script_path, "--create-service", server_dir]
                proc = subprocess.Popen(create_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            
            output, _ = proc.communicate()
            self._add_status_message(output.strip())

            if proc.returncode == 0:
                if remove:
                    self._add_status_message("開機自動啟動已移除。")
                    self.auto_start_button.config(text="設為開機自動啟動", command=self._toggle_autostart_bedrock_server, state=tk.NORMAL)
                else:
                    self._add_status_message("開機自動啟動設定完成。")
                    self.auto_start_button.config(text="關閉開機自動啟動", command=lambda: self._toggle_autostart_bedrock_server(remove=True), state=tk.NORMAL)
                    self._start_bedrock_server()
            else:
                self._add_status_message("開機自動啟動操作失敗。", is_error=True)
        except Exception as e:
            self._add_status_message(f"開機自動啟動操作失敗: {e}", is_error=True)
        # 仍然再次查詢狀態以保險
        self._check_autostart_status()

    def _backup_data(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S") # Date and Time as YYYYMMDD-HHMMSS
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
                                    # arcname is the path inside the zip file
                                    arcname = os.path.join(item_name, os.path.relpath(file_abs_path, item_path))
                                    zf.write(file_abs_path, arcname)
                            self._add_status_message(f"'{item_name}' directory backed up.")
                        elif os.path.isfile(item_path): # For single files, if ever needed for other items
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
