"""
manager.py - Manager Module
Handles all Manager tab logic and functionality (HATS-Off)
HATSKit Pro v1.2.8
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox, scrolledtext
import json
import os
import zipfile
import py7zr
import shutil
from pathlib import Path
import requests
import threading
import webbrowser


class PackManager:
    """Handles Manager/HATS-Off functionality"""
    
    def __init__(self, main_gui):
        """Initialize with reference to main GUI"""
        self.gui = main_gui
        self.manifest_data = {}
        self.trash_data = {}
        self.current_view = 'installed' # 'installed' or 'trash'
        self.latest_release_info = None
        self.download_thread = None

        # GitHub repo info
        self.GITHUB_REPO = "sthetix/HATS"
        self.GITHUB_API_URL = f"https://api.github.com/repos/{self.GITHUB_REPO}/releases/latest"

        # Firmware repo info
        self.FIRMWARE_REPO = "sthetix/NXFW"
        self.FIRMWARE_API_URL = f"https://api.github.com/repos/{self.FIRMWARE_REPO}/releases/latest"
        self.latest_firmware_info = None
        self.firmware_download_thread = None

        # Connect event handlers
        self.connect_events()

        # Check for latest release on startup
        self.check_latest_release()
        self.check_latest_firmware()
    
    def connect_events(self):
        """Connect event handlers to UI elements"""
        # Tree selection
        self.gui.manager_tree.bind('<<TreeviewSelect>>', self.on_manager_selection_change)
        
        # Connect buttons
        self._connect_manager_buttons()
    
    def _connect_manager_buttons(self):
        """Find and connect manager tab buttons"""
        def find_buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    text = child.cget('text')
                    if text == "Browse...":
                        child.config(command=self.manager_browse_sd)
                    elif text == "Select Pack (.zip)...":
                        child.config(command=self.manager_select_pack)
                    elif text == "Install to SD Card":
                        child.config(command=self.manager_install_pack)
                    elif text == "Installed Components":
                        child.config(command=lambda: self.manager_switch_view('installed'))
                    elif text == "Trash Bin":
                        child.config(command=lambda: self.manager_switch_view('trash'))
                    elif text == "Move to Trash":
                        child.config(command=self.manager_move_to_trash)
                    elif text == "Select All":
                        child.config(command=self.manager_select_all)
                    elif text == "Clear Selection":
                        child.config(command=self.manager_deselect_all)
                    elif text == "Download Latest":
                        # Check parent to determine if HATS or Firmware
                        parent = child.master
                        while parent and not isinstance(parent, ttk.Labelframe):
                            parent = parent.master
                        if parent and "Firmware" in parent.cget('text'):
                            child.config(command=self.download_latest_firmware)
                        else:
                            child.config(command=self.download_latest_pack)
                    elif text == "Refresh":
                        # Check parent to determine if HATS or Firmware
                        parent = child.master
                        while parent and not isinstance(parent, ttk.Labelframe):
                            parent = parent.master
                        if parent and "Firmware" in parent.cget('text'):
                            child.config(command=self.check_latest_firmware)
                        else:
                            child.config(command=self.check_latest_release)
                    elif text == "View on GitHub":
                        # Check parent to determine if HATS or Firmware
                        parent = child.master
                        while parent and not isinstance(parent, ttk.Labelframe):
                            parent = parent.master
                        if parent and "Firmware" in parent.cget('text'):
                            child.config(command=self.open_github_firmware)
                        else:
                            child.config(command=self.open_github_releases)
                find_buttons(child)

        find_buttons(self.gui.manager_tab)
    
    def manager_browse_sd(self):
        """Browse for SD card (silent mode - no popups)"""
        folder = filedialog.askdirectory(title="Select SD Card Root Folder")
        if folder:
            self.gui.sd_path.set(folder)
            self.update_install_button_state()
            self.manager_refresh()
            # Update System Config tab status display
            self.gui.update_system_config_sd_status()
            # Silently auto-detect settings for Extra Config tab (no popup)
            self.gui.auto_detect_system_settings_silent()
    
    def manager_refresh(self):
        """Refresh manager view"""
        sd_path = self.gui.sd_path.get()
        if not sd_path: return

        # Load both manifests
        self.load_manifests()

        # Check if main manifest was found
        if not self.manifest_data:
            self.gui.status_bar.config(text=f"SD card selected. No manifest.json found (normal for new setup).")
            # Clear the tree and do nothing else, as there are no components to show.
            self.populate_manager_tree()
        else:
            self.populate_manager_tree()
            self.gui.status_bar.config(text=f"Loaded {len(self.manifest_data.get('components', []))} components from {sd_path}")

    def load_manifests(self):
        """Load both the main and trash manifests."""
        sd_path = self.gui.sd_path.get()
        if not sd_path:
            return

        main_manifest_path = Path(sd_path) / 'manifest.json'
        trash_manifest_path = Path(sd_path) / 'trash.json'

        try:
            self.manifest_data = json.loads(main_manifest_path.read_text(encoding='utf-8')) if main_manifest_path.exists() else {}
            self.trash_data = json.loads(trash_manifest_path.read_text(encoding='utf-8')) if trash_manifest_path.exists() else {}
        except (json.JSONDecodeError, IOError) as e:
            self.gui.show_custom_info("Manifest Error", f"Failed to load manifest files:\n{e}", width=450)

    def populate_manager_tree(self):
        """Populate the manager tree based on the current view."""
        for item in self.gui.manager_tree.get_children():
            self.gui.manager_tree.delete(item)

        data_source = self.manifest_data if self.current_view == 'installed' else self.trash_data
        components = data_source.get('components', {})

        for comp_id, comp_data in components.items():
            self.gui.manager_tree.insert('', END, iid=comp_id,
                                     values=(comp_data.get('name', comp_id), comp_data.get('version', 'N/A'),
                                             comp_data.get('category', 'Unknown'),
                                             len(comp_data.get('files', []))))
        
        self.update_manager_selection_label()

    def save_manifests(self):
        """Save both manifests back to the SD card."""
        sd_path = self.gui.sd_path.get()
        if not sd_path:
            return

        main_manifest_path = Path(sd_path) / 'manifest.json'
        trash_manifest_path = Path(sd_path) / 'trash.json'

        try:
            main_manifest_path.write_text(json.dumps(self.manifest_data, indent=2), encoding='utf-8')
            if self.trash_data: # Only write trash if it's not empty
                trash_manifest_path.write_text(json.dumps(self.trash_data, indent=2), encoding='utf-8')
        except IOError as e:
            self.gui.show_custom_info("Save Error", f"Failed to save manifest files:\n{e}", width=450)

    def manager_select_pack(self):
        """Opens a file dialog to select a HATS pack zip file."""
        pack_file = filedialog.askopenfilename(
            title="Select HATS Pack",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
        )
        
        if pack_file:
            self.gui.pack_path.set(pack_file)
            self.update_install_button_state()

    def update_install_button_state(self):
        """Enable or disable the install button based on SD and Pack paths."""
        if self.gui.sd_path.get() and self.gui.pack_path.get():
            self.gui.install_btn.config(state=NORMAL)

    def manager_install_pack(self):
        """Performs the clean installation of the selected pack."""
        
        sd_path = self.gui.sd_path.get()
        pack_file = self.gui.pack_path.get()
        
        # Validation
        if not sd_path or not pack_file:
            self.gui.show_custom_info("Error", "Please select both SD card location and HATS pack file.")
            return
        
        if not os.path.exists(sd_path):
            self.gui.show_custom_info("Error", f"SD card path does not exist:\n{sd_path}", width=450)
            return
        
        if not os.path.exists(pack_file):
            self.gui.show_custom_info("Error", f"Pack file does not exist:\n{pack_file}", width=450)
            return
        
        # Confirmation dialog with folder list
        folders_to_delete = ["atmosphere", "sept"]
        existing_folders = [f for f in folders_to_delete if os.path.exists(os.path.join(sd_path, f))]
        
        confirm_msg = f"⚠️ CLEAN INSTALLATION WARNING ⚠️\n\n"
        confirm_msg += f"This will install to: {sd_path}\n\n"
        
        if existing_folders:
            confirm_msg += "The following folders will be PERMANENTLY DELETED:\n"
            for folder in existing_folders:
                confirm_msg += f"  • {folder}\n"
            confirm_msg += "\nOld HATS manifest files will also be deleted.\n"
        else:
            confirm_msg += "This appears to be a fresh installation.\n"
        
        confirm_msg += "\nAre you sure you want to continue?"
        
        # Create custom confirmation dialog
        confirm_dialog = ttk.Toplevel(self.gui.root)
        confirm_dialog.title("Confirm Clean Installation")
        confirm_dialog.geometry("500x450")
        confirm_dialog.transient(self.gui.root)
        confirm_dialog.grab_set()
        
        confirm_frame = ttk.Frame(confirm_dialog, padding=20)
        confirm_frame.pack(fill=BOTH, expand=True)
        
        # Warning icon/header
        ttk.Label(confirm_frame, text="⚠️ CLEAN INSTALLATION WARNING ⚠️",
                  font=('Segoe UI', 12, 'bold'), bootstyle="warning").pack(pady=(0, 15))
        
        # Message text
        msg_text = scrolledtext.ScrolledText(confirm_frame, height=10, width=55, wrap='word')
        msg_text.pack(fill=BOTH, expand=True, pady=(0, 15))
        msg_text.insert('1.0', confirm_msg)
        msg_text.config(state='disabled')
        
        # Button frame
        btn_frame = ttk.Frame(confirm_frame)
        btn_frame.pack()
        
        user_confirmed = [False]  # Use list to modify in nested function
        
        def on_confirm():
            user_confirmed[0] = True
            confirm_dialog.destroy()
        
        def on_cancel():
            confirm_dialog.destroy()
        
        ttk.Button(btn_frame, text="Yes, Continue", command=on_confirm,
                   bootstyle="danger", width=15).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel,
                   bootstyle="secondary", width=15).pack(side=LEFT, padx=5)
        
        # Center the dialog
        self.gui.center_window(confirm_dialog)
        
        # Wait for user response
        self.gui.root.wait_window(confirm_dialog)
        
        if not user_confirmed[0]:
            return
        
        # Create progress window
        progress_window = ttk.Toplevel(self.gui.root)
        progress_window.title("Installing HATS Pack")
        progress_window.geometry("600x600")
        progress_window.transient(self.gui.root)
        progress_window.grab_set()
        
        # Progress window content frame
        progress_content = ttk.Frame(progress_window, padding=20)
        progress_content.pack(fill=BOTH, expand=True)
        
        ttk.Label(progress_content, text="Installing HATS Pack...",
                  font=('Segoe UI', 12, 'bold')).pack(pady=(0, 10))
        
        progress = ttk.Progressbar(progress_content, mode='indeterminate', bootstyle="success")
        progress.pack(fill=X, pady=10)
        progress.start()
        
        log_text = scrolledtext.ScrolledText(progress_content, height=12, width=70)
        log_text.pack(fill=BOTH, expand=True, pady=10)
        
        # Center the progress window
        self.gui.center_window(progress_window)
        
        def log(message):
            log_text.insert(END, message + "\n")
            log_text.see(END)
            log_text.update()
        
        try:
            # Step 1: Cleanup
            log("🧹 Starting cleanup process...")
            
            for folder in folders_to_delete:
                folder_path = os.path.join(sd_path, folder)
                if os.path.exists(folder_path):
                    log(f"  Deleting {folder}...")
                    shutil.rmtree(folder_path, ignore_errors=True)
            
            # Delete old HATS version files
            log("  Removing HATS version files...")
            # Delete new fixed filename
            version_file = Path(sd_path) / "HATS_VERSION.txt"
            if version_file.exists():
                try:
                    version_file.unlink()
                    log(f"    Deleted HATS_VERSION.txt")
                except:
                    pass
            # Legacy support: delete old HATS-*.txt format
            for file in Path(sd_path).glob("HATS-*.txt"):
                try:
                    file.unlink()
                    log(f"    Deleted {file.name} (legacy)")
                except:
                    pass

            # Delete manifest.json and trash.json
            for manifest_file in ["manifest.json", "trash.json"]:
                manifest_path = Path(sd_path) / manifest_file
                if manifest_path.exists():
                    try:
                        manifest_path.unlink()
                        log(f"    Deleted {manifest_file}")
                    except:
                        pass

            log("✅ Cleanup complete!\n")
            
            # Step 2: Extract new pack
            log("📦 Extracting HATS pack...")
            with zipfile.ZipFile(pack_file, 'r') as zip_ref:
                total_files = len(zip_ref.namelist())
                log(f"  Total files to extract: {total_files}")
                zip_ref.extractall(sd_path)
            
            log("✅ Installation Complete!")
            log(f"HATS pack successfully installed to:\n{sd_path}")
            
            progress.stop()
            
            # Success label
            success_label = ttk.Label(progress_content, text="✅ Installation Successful!",
                      font=('Segoe UI', 11, 'bold'), bootstyle="success")
            success_label.pack(pady=10)
            
            close_btn = ttk.Button(progress_content, text="Close", 
                                   command=progress_window.destroy,
                                   bootstyle="success", width=15)
            close_btn.pack(pady=5)
            
            # Silently refresh the manager view without showing popup
            self.load_manifests()
            self.populate_manager_tree()
            self.gui.status_bar.config(text=f"Loaded manifest from: {sd_path}")
            
        except Exception as e:
            progress.stop()
            log(f"\n❌ ERROR: {str(e)}")
            self.gui.show_custom_info("Installation Failed", 
                                      f"An error occurred during installation:\n\n{str(e)}", width=500, height=300)
            progress_window.destroy()
    
    def on_manager_selection_change(self, event=None):
        """Update selection label when selection changes"""
        self.update_manager_selection_label()
    
    def update_manager_selection_label(self):
        """Update the manager selection count label"""
        selected = self.gui.manager_tree.selection()
        count = len(selected)
        
        # TODO: Calculate total files when we have real manifest data
        self.gui.manager_selection_label.config(text=f"Selected: {count} components")
        
        # Enable/disable remove button
        if count > 0:
            self.gui.manager_remove_btn.config(state=NORMAL)
        else:
            self.gui.manager_remove_btn.config(state=DISABLED)
    
    def manager_switch_view(self, view):
        """Switch between installed and trash views"""
        self.current_view = view

        if view == 'installed':
            self.gui.manager_installed_btn.config(bootstyle="primary")
            self.gui.manager_trash_btn.config(bootstyle="secondary")
            self.gui.manager_components_frame.config(text="Installed Components")
            self.gui.manager_remove_btn.config(text="Move to Trash", bootstyle="danger",
                                               command=self.manager_move_to_trash)
        else:
            self.gui.manager_trash_btn.config(bootstyle="primary")
            self.gui.manager_installed_btn.config(bootstyle="secondary")
            self.gui.manager_components_frame.config(text="Trash Bin")
            self.gui.manager_remove_btn.config(text="Restore", bootstyle="success",
                                               command=self.manager_restore_from_trash)
            # TODO: Add a "Delete Permanently" button and logic
        
        self.populate_manager_tree()
        # After populating, ensure the selection count is updated correctly
        self.update_manager_selection_label()
    
    def manager_select_all(self):
        """Select all components in manager"""
        for item in self.gui.manager_tree.get_children():
            self.gui.manager_tree.selection_add(item)
        self.update_manager_selection_label()
    
    def manager_deselect_all(self):
        """Deselect all components in manager"""
        self.gui.manager_tree.selection_remove(self.gui.manager_tree.selection())
        self.update_manager_selection_label()
    
    def manager_restore_from_trash(self):
        """Restore selected components from the trash."""
        selected_ids = self.gui.manager_tree.selection()
        if not selected_ids:
            return

        if not self.gui.show_custom_confirm("Confirm Restore", 
                                            "This will restore the component entries to the main manifest.\n\nTo re-download the files, please run the Pack Installer again.\n\nContinue?",
                                            yes_text="Restore", style="success", height=350):
            return

        # For simplicity, we'll move the manifest entries back and let the user re-run the main installer.
        # A more advanced implementation would re-download files.
        
        if 'components' not in self.manifest_data:
            self.manifest_data['components'] = {}

        for comp_id in selected_ids:
            if comp_id in self.trash_data.get('components', {}):
                comp_data = self.trash_data['components'][comp_id]
                self.manifest_data['components'][comp_id] = comp_data
                del self.trash_data['components'][comp_id]

        self.save_manifests()
        self.populate_manager_tree()
        self.gui.show_custom_info("Restore", "Component entries have been restored to the main manifest. "
                                  "Please run the Pack Installer again to download the necessary files.", height=250)

    def manager_move_to_trash(self):
        """Move selected components to trash"""
        selected_ids = self.gui.manager_tree.selection()
        if not selected_ids:
            return
        
        sd_path = Path(self.gui.sd_path.get())
        if not sd_path.exists():
            self.gui.show_custom_info("Error", "SD Card path is not valid.")
            return

        component_names = [self.manifest_data['components'][cid]['name'] for cid in selected_ids]
        component_list = '\n'.join(f"  • {name}" for name in component_names)
        
        # Create a custom confirmation dialog
        confirm_dialog = ttk.Toplevel(self.gui.root)
        confirm_dialog.title("Confirm Move to Trash")
        confirm_dialog.geometry("500x400")
        confirm_dialog.transient(self.gui.root)
        confirm_dialog.grab_set()
        
        confirm_frame = ttk.Frame(confirm_dialog, padding=20)
        confirm_frame.pack(fill=BOTH, expand=True)
        
        ttk.Label(confirm_frame, text="⚠️ Confirm Deletion ⚠️",
                  font=('Segoe UI', 12, 'bold'), bootstyle="warning").pack(pady=(0, 15))

        msg = f"This will DELETE the files for the following components from your SD card:\n\n{component_list}\n\nAre you sure you want to continue?"
        msg_text = scrolledtext.ScrolledText(confirm_frame, height=8, width=55, wrap='word')
        msg_text.pack(fill=BOTH, expand=True, pady=(0, 15))
        msg_text.insert('1.0', msg)
        msg_text.config(state='disabled')
        
        user_confirmed = [False]
        def on_confirm():
            user_confirmed[0] = True
            confirm_dialog.destroy()
        
        btn_frame = ttk.Frame(confirm_frame)
        btn_frame.pack()
        ttk.Button(btn_frame, text="Yes, Delete Files", command=on_confirm, bootstyle="danger").pack(side=LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=confirm_dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=10)
        
        self.gui.center_window(confirm_dialog)
        self.gui.root.wait_window(confirm_dialog)
        
        if not user_confirmed[0]:
            return

        # Ensure trash manifest has a components dictionary
        if 'components' not in self.trash_data:
            self.trash_data['components'] = {}

        deleted_count = 0
        for comp_id in selected_ids:
            if comp_id in self.manifest_data['components']:
                comp_data = self.manifest_data['components'][comp_id]
                
                # Delete files
                for file_path_str in comp_data.get('files', []):
                    file_to_delete = sd_path / file_path_str
                    try:
                        if file_to_delete.exists():
                            file_to_delete.unlink()
                            deleted_count += 1
                    except OSError:
                        pass # Ignore errors if file is in use, etc.

                # Move from main manifest to trash manifest
                self.trash_data['components'][comp_id] = comp_data
                del self.manifest_data['components'][comp_id]

        # Save changes and refresh UI
        self.save_manifests()
        self.populate_manager_tree()
        self.gui.show_custom_info("Success", f"Moved {len(selected_ids)} components to trash.\nDeleted {deleted_count} files.", height=250)

    # ===== DOWNLOAD FUNCTIONALITY =====

    def check_latest_release(self):
        """Check GitHub for the latest release"""
        def fetch_release():
            try:
                headers = {}
                # Use GitHub PAT if available
                if self.gui.github_pat.get():
                    headers['Authorization'] = f'token {self.gui.github_pat.get()}'

                response = requests.get(self.GITHUB_API_URL, headers=headers, timeout=10)
                response.raise_for_status()
                release_data = response.json()

                self.latest_release_info = {
                    'tag': release_data.get('tag_name', 'Unknown'),
                    'name': release_data.get('name', 'Unknown'),
                    'published_at': release_data.get('published_at', ''),
                    'download_url': None,
                    'size': 0
                }

                # Find the .zip asset
                for asset in release_data.get('assets', []):
                    if asset['name'].endswith('.zip'):
                        self.latest_release_info['download_url'] = asset['browser_download_url']
                        self.latest_release_info['size'] = asset['size']
                        self.latest_release_info['filename'] = asset['name']
                        break

                # Update UI on main thread
                self.gui.root.after(0, self.update_release_ui, True, None)

            except requests.RequestException as e:
                self.gui.root.after(0, self.update_release_ui, False, str(e))

        # Run in background thread
        threading.Thread(target=fetch_release, daemon=True).start()

    def update_release_ui(self, success, error_msg):
        """Update the UI with release information"""
        if success and self.latest_release_info:
            release_text = f"{self.latest_release_info['tag']} ({self.format_size(self.latest_release_info['size'])})"
            self.gui.latest_release_label.config(text=release_text, bootstyle="success")
            self.gui.download_btn.config(state=NORMAL)
        else:
            error_text = "Failed to fetch"
            if error_msg:
                error_text += f" - {error_msg[:50]}"
            self.gui.latest_release_label.config(text=error_text, bootstyle="danger")
            self.gui.download_btn.config(state=DISABLED)

    def format_size(self, size_bytes):
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def open_github_releases(self):
        """Open GitHub releases page in browser"""
        webbrowser.open(f"https://github.com/{self.GITHUB_REPO}/releases")

    def download_latest_pack(self):
        """Download the latest pack with progress tracking"""
        if not self.latest_release_info or not self.latest_release_info.get('download_url'):
            self.gui.show_custom_info("Error", "No download URL available. Please refresh release info.")
            return

        # Create downloads directory
        downloads_dir = Path("downloads")
        downloads_dir.mkdir(exist_ok=True)

        filename = self.latest_release_info.get('filename', 'HATS-pack.zip')
        save_path = downloads_dir / filename

        filename = self.latest_release_info.get('filename', 'HATS-pack.7z')
        save_path = downloads_dir / filename

        # Check if already downloaded
        if save_path.exists():
            if not self.gui.show_custom_confirm(
                "File Exists",
                f"The file {filename} already exists.\n\nDo you want to re-download it?",
                yes_text="Re-download",
                no_text="Use Existing",
                height=280
            ):
                # User chose to use existing file
                self.gui.pack_path.set(str(save_path))
                self.update_install_button_state()
                self.gui.show_custom_info(
                    "Using Existing Pack",
                    f"Using existing pack:\n\n{save_path}\n\nYou can now install it to your SD card.",
                    width=500,
                    height=280
                )
                return

        # Disable download button
        self.gui.download_btn.config(state=DISABLED)

        # Show progress bar
        self.gui.download_progress_frame.pack(side=LEFT, fill=X, expand=True, padx=10)
        self.gui.download_progress['value'] = 0
        self.gui.download_status_label.config(text="Starting download...")

        def download_with_progress():
            try:
                # Get chunk size from config (default 2MB)
                chunk_size = self.gui.config_data.get('download_chunk_size', 2 * 1024 * 1024)

                headers = {}
                if self.gui.github_pat.get():
                    headers['Authorization'] = f'token {self.gui.github_pat.get()}'

                response = requests.get(
                    self.latest_release_info['download_url'],
                    headers=headers,
                    stream=True,
                    timeout=30
                )
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Update progress on main thread
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                status_text = f"Downloaded: {self.format_size(downloaded)} / {self.format_size(total_size)} ({progress:.1f}%)"
                                self.gui.root.after(0, self.update_download_progress, progress, status_text)

                # Download complete
                self.gui.root.after(0, self.download_complete, str(save_path), None)

            except Exception as e:
                self.gui.root.after(0, self.download_complete, None, str(e))

        # Start download in background thread
        self.download_thread = threading.Thread(target=download_with_progress, daemon=True)
        self.download_thread.start()

    def update_download_progress(self, progress, status_text):
        """Update download progress bar (runs on main thread)"""
        self.gui.download_progress['value'] = progress
        self.gui.download_status_label.config(text=status_text)

    def download_complete(self, save_path, error_msg):
        """Handle download completion (runs on main thread)"""
        # Hide progress bar
        self.gui.download_progress_frame.pack_forget()

        # Re-enable download button
        self.gui.download_btn.config(state=NORMAL)

        if error_msg:
            self.gui.show_custom_info("Download Failed", f"Failed to download pack:\n\n{error_msg}", width=450, height=250)
        else:
            # Auto-populate pack path
            self.gui.pack_path.set(save_path)
            self.update_install_button_state()

            # Force GUI update before showing dialog
            self.gui.root.update_idletasks()

            # Delay the popup slightly to ensure all GUI updates complete
            def show_completion_popup():
                self.gui.show_custom_info(
                    "Download Complete",
                    f"Pack downloaded successfully!\n\n{save_path}\n\nYou can now install it to your SD card.",
                    width=500,
                    height=300
                )

            self.gui.root.after(200, show_completion_popup)

    # ===== FIRMWARE DOWNLOAD FUNCTIONALITY =====

    def check_latest_firmware(self):
        """Check GitHub for the latest firmware release"""
        def fetch_firmware():
            try:
                headers = {}
                # Use GitHub PAT if available
                if self.gui.github_pat.get():
                    headers['Authorization'] = f'token {self.gui.github_pat.get()}'

                response = requests.get(self.FIRMWARE_API_URL, headers=headers, timeout=10)
                response.raise_for_status()
                release_data = response.json()

                self.latest_firmware_info = {
                    'tag': release_data.get('tag_name', 'Unknown'),
                    'name': release_data.get('name', 'Unknown'),
                    'published_at': release_data.get('published_at', ''),
                    'download_url': None,
                    'size': 0
                }

                # Find the .zip asset
                for asset in release_data.get('assets', []):
                    if asset['name'].endswith('.zip'):
                        self.latest_firmware_info['download_url'] = asset['browser_download_url']
                        self.latest_firmware_info['size'] = asset['size']
                        self.latest_firmware_info['filename'] = asset['name']
                        break

                # Update UI on main thread
                self.gui.root.after(0, self.update_firmware_ui, True, None)

            except requests.RequestException as e:
                self.gui.root.after(0, self.update_firmware_ui, False, str(e))

        # Run in background thread
        threading.Thread(target=fetch_firmware, daemon=True).start()

    def update_firmware_ui(self, success, error_msg):
        """Update the UI with firmware release information"""
        if success and self.latest_firmware_info:
            release_text = f"{self.latest_firmware_info['tag']} ({self.format_size(self.latest_firmware_info['size'])})"
            self.gui.latest_firmware_label.config(text=release_text, bootstyle="success")
            self.gui.firmware_download_btn.config(state=NORMAL)
        else:
            error_text = "Failed to fetch"
            if error_msg:
                error_text += f" - {error_msg[:50]}"
            self.gui.latest_firmware_label.config(text=error_text, bootstyle="danger")
            self.gui.firmware_download_btn.config(state=DISABLED)

    def open_github_firmware(self):
        """Open GitHub firmware releases page in browser"""
        webbrowser.open(f"https://github.com/{self.FIRMWARE_REPO}/releases")

    def download_latest_firmware(self):
        """Download the latest firmware pack with progress tracking"""
        if not self.latest_firmware_info or not self.latest_firmware_info.get('download_url'):
            self.gui.show_custom_info("Error", "No download URL available. Please refresh release info.")
            return

        # Create downloads directory
        downloads_dir = Path("downloads")
        downloads_dir.mkdir(exist_ok=True)

        filename = self.latest_firmware_info.get('filename', 'FW-pack.zip')
        save_path = downloads_dir / filename

        # Check if already downloaded
        if save_path.exists():
            if not self.gui.show_custom_confirm(
                "File Exists",
                f"The file {filename} already exists.\n\nDo you want to re-download it?",
                yes_text="Re-download",
                no_text="Use Existing",
                height=250
            ):
                # User chose to use existing file
                self.gui.show_custom_info("Success", f"Using existing firmware pack:\n{save_path}")
                return

        # Disable download button
        self.gui.firmware_download_btn.config(state=DISABLED)

        # Show progress bar
        self.gui.firmware_progress_frame.pack(side=LEFT, fill=X, expand=True, padx=10)
        self.gui.firmware_progress['value'] = 0
        self.gui.firmware_status_label.config(text="Starting download...")

        def download_with_progress():
            try:
                # Get chunk size from config (default 2MB)
                chunk_size = self.gui.config_data.get('download_chunk_size', 2 * 1024 * 1024)

                headers = {}
                if self.gui.github_pat.get():
                    headers['Authorization'] = f'token {self.gui.github_pat.get()}'

                response = requests.get(
                    self.latest_firmware_info['download_url'],
                    headers=headers,
                    stream=True,
                    timeout=30
                )
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Update progress on main thread
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                status_text = f"Downloaded: {self.format_size(downloaded)} / {self.format_size(total_size)} ({progress:.1f}%)"
                                self.gui.root.after(0, self.update_firmware_progress, progress, status_text)

                # Download complete
                self.gui.root.after(0, self.firmware_download_complete, str(save_path), None)

            except Exception as e:
                self.gui.root.after(0, self.firmware_download_complete, None, str(e))

        # Start download in background thread
        self.firmware_download_thread = threading.Thread(target=download_with_progress, daemon=True)
        self.firmware_download_thread.start()

    def update_firmware_progress(self, progress, status_text):
        """Update firmware download progress bar (runs on main thread)"""
        self.gui.firmware_progress['value'] = progress
        self.gui.firmware_status_label.config(text=status_text)

    def firmware_download_complete(self, save_path, error_msg):
        """Handle firmware download completion (runs on main thread)"""
        # Hide progress bar
        self.gui.firmware_progress_frame.pack_forget()

        # Re-enable download button
        self.gui.firmware_download_btn.config(state=NORMAL)

        if error_msg:
            self.gui.show_custom_info("Download Failed", f"Failed to download firmware pack:\n\n{error_msg}", width=450, height=250)
        else:
            # Force GUI update before showing dialog
            self.gui.root.update_idletasks()

            # Delay the popup slightly to ensure all GUI updates complete
            def show_completion_popup():
                self.gui.show_custom_info(
                    "Download Complete",
                    f"Firmware pack downloaded successfully!\n\n{save_path}\n\nYou can manually extract this to your SD card.",
                    width=500,
                    height=300
                )

            self.gui.root.after(200, show_completion_popup)