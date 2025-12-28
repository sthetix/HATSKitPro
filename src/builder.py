"""
builder.py - Pack Builder Module
Handles all Pack Builder tab logic and functionality
"""

import ttkbootstrap as ttk
import threading
import urllib.request
import urllib.error
import json
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox, scrolledtext
import zipfile
import tempfile
import shutil
from pathlib import Path
import datetime
import hashlib
import fnmatch
import re
import ssl
import certifi
import concurrent.futures
import os

# Global SSL context using certifi CA bundle (macOS fix)
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Override urllib's default HTTPS context globally
ssl._create_default_https_context = lambda: SSL_CONTEXT

class PackBuilder:
    """Handles Pack Builder functionality"""

    ATMOSPHERE_REPO = "Atmosphere-NX/Atmosphere"

    # Checkbox Unicode Symbols
    CHECKED_ICON = "☑ "
    UNCHECKED_ICON = "☐ "

    # New file for presets
    PROFILES_FILE = "profiles.json"

    def __init__(self, main_gui):
        """Initialize with reference to main GUI"""
        self.gui = main_gui
        self.fetch_button = None # To hold a reference to the button

        # Track Checked Components (Set of Component IDs)
        self.checked_components = set()

        # Dictionary to store loaded profiles
        self.profiles = {}

        # Load presets on startup
        self.load_profiles()

        # Connect event handlers to UI widgets
        self.connect_events()

        # Bind Profile Selection
        self.gui.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_selected)

    def connect_events(self):
        """Connect event handlers to UI elements"""
        # Search and filter
        self.gui.builder_search.bind('<KeyRelease>', self.filter_builder_components)

        # Mouse Click Logic (for Checkboxes)
        self.gui.builder_list.bind('<Button-1>', self.on_tree_click)
        
        # Spacebar Logic (Toggle checkboxes with keyboard)
        self.gui.builder_list.bind('<space>', self.on_space_press)

        # Double-click to edit version
        self.gui.builder_list.bind('<Double-Button-1>', self.on_version_double_click)
        
        # Prevent categories from collapsing (Binding added to enforce your logic)
        self.gui.builder_list.bind('<<TreeviewClose>>', self.prevent_category_collapse)

        # Connect buttons
        self._connect_builder_buttons()
        
    def prevent_category_collapse(self, event):
        """Force categories to stay open"""
        return "break"

    def _connect_builder_buttons(self):
        """Find and connect builder tab buttons"""
        # This connects the button commands after UI creation
        def find_buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    text = child.cget('text')
                    if text == "Select All":
                        child.config(command=self.builder_select_all)
                    elif text == "Clear Selection":
                        child.config(command=self.builder_clear_selection)
                    elif text == "Fetch Versions":
                        child.config(command=self.fetch_github_versions)
                        self.fetch_button = child 
                    elif text == "Build Pack":
                        child.config(command=self.build_pack)
                find_buttons(child)
        
        find_buttons(self.gui.builder_tab)

    def save_last_used_profile(self):
        """Saves current selection to profiles.json as 'Last Used'"""
        self.profiles["Last Used"] = list(self.checked_components)

        try:
            with open(self.PROFILES_FILE, 'w') as f:
                json.dump(self.profiles, f, indent=4)
        except Exception as e:
            print(f"Failed to save profiles: {e}")

    def load_profiles(self):
        """Load profiles from JSON (Pure 'Last Used' logic)"""
        defaults = {
            "Minimal": ["atmosphere", "hekate"],
            "Standard": ["Lockpick_RCM_Pro", "status_monitor_overlay", "linkalho", "quick_reboot_app", "quick_reboot_ovl", "sys-clk-base", "atmosphere", "sysmodules_overlay", "sphaira", "ultrahand_overlay", "ftpd", "edizon_overlay", "hekate", "jksv", "dns_mitm_manager", "dbi", "sys_patch", "prodinfo_gen", "tinwoo", "sys-clk-overlay", "quickntp"],
            "Full": []
        }

        if os.path.exists(self.PROFILES_FILE):
            try:
                with open(self.PROFILES_FILE, 'r') as f:
                    self.profiles = json.load(f)
            except:
                self.profiles = defaults.copy()
        else:
            self.profiles = defaults.copy()

        self._update_profile_combo()

    def _update_profile_combo(self):
        """Refresh dropdown and set default selection"""
        names = list(self.profiles.keys())

        # Ensure "Last Used" is at the top
        if "Last Used" in names:
            names.remove("Last Used")
            names.sort()
            names.insert(0, "Last Used")
        else:
            names.sort()

        self.gui.profile_combo['values'] = names

        # Default to "Last Used" if it exists
        if "Last Used" in names:
            self.gui.profile_combo.set("Last Used")
        elif names:
            self.gui.profile_combo.set(names[0])

    def on_profile_selected(self, event):
        """Apply the selected profile"""
        name = self.gui.profile_combo.get()
        if name not in self.profiles: return

        # Logic for "Full" (if empty list, select all visible in components.json)
        target_components = self.profiles[name]

        self.checked_components.clear()

        if name == "Full" and not target_components:
             # If "Full" is defined as empty list in defaults, select all known components
             for cid in self.gui.components_data:
                 self.checked_components.add(cid)
        else:
            for cid in target_components:
                # Only add if it exists in current components.json
                if cid in self.gui.components_data:
                    self.checked_components.add(cid)

        self.filter_builder_components()

    def save_current_profile(self):
        """Save current selection as a new profile (Custom Dialog)"""
        if not self.checked_components:
            self.gui.show_custom_info("No Selection", "Please select at least one component to save.")
            return

        # Create a custom styled dialog instead of system default
        dialog = ttk.Toplevel(self.gui.root)
        dialog.title("Save Preset")
        dialog.geometry("400x180")
        dialog.transient(self.gui.root)
        dialog.grab_set() # Make modal

        content = ttk.Frame(dialog, padding=20)
        content.pack(fill=BOTH, expand=True)

        ttk.Label(content, text="Enter a name for this preset:", font=('Segoe UI', 10)).pack(anchor=W, pady=(0, 10))

        name_var = ttk.StringVar()
        entry = ttk.Entry(content, textvariable=name_var)
        entry.pack(fill=X, pady=(0, 20))
        entry.focus() # Auto-focus input

        btn_frame = ttk.Frame(content)
        btn_frame.pack(fill=X)

        def on_save(event=None):
            name = name_var.get().strip()
            if not name:
                return

            # Prevent overwriting defaults
            if name in ["Minimal", "Standard", "Full"]:
                self.gui.show_custom_info("Protected", "Cannot overwrite default presets.", parent=dialog)
                return

            self.profiles[name] = list(self.checked_components)
            self._save_profiles_to_disk()
            self._update_profile_combo()
            self.gui.profile_combo.set(name)
            dialog.destroy()

        entry.bind('<Return>', on_save) # Allow pressing Enter to save

        ttk.Button(btn_frame, text="Save", bootstyle="info", command=on_save).pack(side=RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT, padx=5)

        self.gui.center_window(dialog)

    def delete_current_profile(self):
        """Delete the currently selected profile"""
        name = self.gui.profile_combo.get()
        if not name: return

        if name in ["Minimal", "Standard", "Full"]:
            self.gui.show_custom_info("Protected", "Cannot delete default profiles.")
            return

        # Use custom confirm dialog instead of system default
        if self.gui.show_custom_confirm("Delete Preset", f"Are you sure you want to delete '{name}'?", style="danger"):
            del self.profiles[name]
            self._save_profiles_to_disk()
            self._update_profile_combo()
            self.gui.profile_combo.set('')

    def _save_profiles_to_disk(self):
        """Write to JSON"""
        try:
            with open(self.PROFILES_FILE, 'w') as f:
                json.dump(self.profiles, f, indent=4)
        except Exception as e:
            print(f"Failed to save profiles: {e}")

    def populate_builder_list(self):
        """Populate builder list with components grouped by category"""
        self.checked_components.clear()
        self.filter_builder_components(initial_load=True)

    def filter_builder_components(self, event=None, initial_load=False):
        """Filter components based on search and rebuild hierarchical tree."""
        
        # Clear Treeview
        for item in self.gui.builder_list.get_children():
            self.gui.builder_list.delete(item)

        search_term = self.gui.builder_search.get().lower()
        last_build_components = self.gui.last_build_data.get('components', {})

        # Group data by category
        grouped_data = {}
        for comp_id, comp_data in self.gui.components_data.items():
            name = comp_data['name']
            category = comp_data.get('category', 'Uncategorized')

            # Apply Search Filter
            if search_term and search_term not in name.lower():
                continue

            if category not in grouped_data:
                grouped_data[category] = []
            grouped_data[category].append((comp_id, comp_data))

        # Helper to clean versions for robust comparison (e.g. "v1.0" == "1.0")
        def normalize_ver(v):
            return str(v).lower().lstrip('v').strip()

        # Populate Treeview
        for category in sorted(grouped_data.keys()):
            # Create Category Node ID
            cat_id = f"CAT_{category}"

            # Visual state of category
            cat_text = f"{self.UNCHECKED_ICON} {category}"

            # Insert Category - Always open=True
            self.gui.builder_list.insert('', END, iid=cat_id, text=cat_text, open=True, tags=('category',))

            # Insert Components
            for comp_id, comp_data in sorted(grouped_data[category], key=lambda x: x[1]['name']):
    
                # Check Logic
                is_checked = False
    
                if initial_load:
                    # Priority 1: Resume "Last Used" session
                    if "Last Used" in self.profiles:
                        if comp_id in self.profiles["Last Used"]:
                            is_checked = True

                    # Priority 2: Default flags in components.json (First run ever)
                    elif "Last Used" not in self.profiles and comp_data.get('default', False):
                        is_checked = True
                else:
                    if comp_id in self.checked_components:
                        is_checked = True

                if is_checked:
                    self.checked_components.add(comp_id)
                    icon = self.CHECKED_ICON
                else:
                    icon = self.UNCHECKED_ICON

                # Color Indicators Logic
                manual_ver = self.gui.manual_versions.get(comp_id, "")
                fetched_ver = comp_data.get('asset_info', {}).get('version', 'Latest')
    
                # Determine Base Version for comparison
                if comp_id in last_build_components:
                    base_ver = last_build_components[comp_id].get('version', 'N/A')
                else:
                    base_ver = comp_data.get('version', 'N/A')

                # Check for Update
                is_update = False
                if base_ver != 'N/A' and fetched_ver != 'Latest':
                    if normalize_ver(fetched_ver) != normalize_ver(base_ver):
                        is_update = True
    
                tags = ['component']
                display_ver = fetched_ver

                if manual_ver:
                    display_ver = manual_ver
                    tags.append('manual')
                elif is_update:
                    display_ver = fetched_ver
                    tags.append('update')
                elif is_checked:
                    tags.append('checked')
    
                display_text = f"{icon} {comp_data['name']}"
    
                # Description Handling
                description = comp_data.get('description', '')
                if isinstance(description, dict):
                    description = description.get('descriptions', {}).get('en', '')
                elif not isinstance(description, str):
                    description = ""

                # Insert into tree
                self.gui.builder_list.insert(cat_id, END, iid=comp_id, text=display_text, 
                                             values=(description, display_ver), tags=tuple(tags))

        self.update_category_checkboxes()
        self.update_selection_count()
        self._check_for_preset_match() # Initial check

    def update_category_checkboxes(self):
        """Update visual state of category checkboxes based on their children"""
        for cat_id in self.gui.builder_list.get_children():
            children = self.gui.builder_list.get_children(cat_id)
            if not children: continue

            # If all children are checked, mark category checked
            all_checked = True
            for child in children:
                if child not in self.checked_components:
                    all_checked = False
                    break

            current_text = self.gui.builder_list.item(cat_id, "text")
            cat_name = current_text.replace(self.CHECKED_ICON, "").replace(self.UNCHECKED_ICON, "").strip()

            if all_checked:
                self.gui.builder_list.item(cat_id, text=f"{self.CHECKED_ICON} {cat_name}")
            else:
                self.gui.builder_list.item(cat_id, text=f"{self.UNCHECKED_ICON} {cat_name}")

    def on_tree_click(self, event):
        """Handle clicks to simulate checkbox toggling"""
        
        # Disable Shift+Click functionality completely
        if event.state & 0x0001:
            return "break"

        region = self.gui.builder_list.identify_region(event.x, event.y)
        item_id = self.gui.builder_list.identify_row(event.y)
        
        if not item_id:
            return

        # If user clicked on the tree/text area
        if region == "tree" or region == "cell":
            if item_id.startswith("CAT_"):
                self.toggle_category(item_id)
            else:
                self.toggle_component(item_id)
    
    def on_space_press(self, event):
        """Toggle selection for all highlighted rows via Spacebar"""
        selected_items = self.gui.builder_list.selection()
        if not selected_items:
            return

        for item_id in selected_items:
            if item_id.startswith("CAT_"):
                self.toggle_category(item_id)
            else:
                self.toggle_component(item_id)

    def update_selection_count(self):
        """Update the label showing how many components are selected"""
        count = len(self.checked_components)
        self.gui.selection_label.config(text=f"Selected: {count} components")

    def _check_for_preset_match(self):
        """Check if current selection matches a preset and update dropdown"""
        if not hasattr(self.gui, 'profile_combo'): return

        current_set = self.checked_components
        match = ''

        # Get all available component IDs to handle the "Full" logic
        all_comps = set(self.gui.components_data.keys())

        for name, preset_comps in self.profiles.items():
            # Handle "Full" special case (empty list in config means 'all')
            if name == 'Full' and not preset_comps:
                if current_set == all_comps:
                    match = name
                    break
            else:
                # Standard exact match comparison
                if current_set == set(preset_comps):
                    match = name
                    break

        # Update the dropdown text without triggering the selection event
        self.gui.profile_combo.set(match)

    def toggle_component(self, comp_id):
        """Toggle a single component's checked state"""
        tags = list(self.gui.builder_list.item(comp_id, "tags"))
        
        has_priority_color = 'manual' in tags or 'update' in tags

        if comp_id in self.checked_components:
            self.checked_components.remove(comp_id)
            icon = self.UNCHECKED_ICON
            if not has_priority_color and 'checked' in tags:
                tags.remove('checked')
        else:
            self.checked_components.add(comp_id)
            icon = self.CHECKED_ICON
            if not has_priority_color and 'checked' not in tags:
                tags.insert(1, 'checked')
        
        current_text = self.gui.builder_list.item(comp_id, "text")
        clean_name = current_text.replace(self.CHECKED_ICON, "").replace(self.UNCHECKED_ICON, "").strip()
        self.gui.builder_list.item(comp_id, text=f"{icon} {clean_name}", tags=tuple(tags))
        
        self.update_category_checkboxes()
        self.update_selection_count()
        self._check_for_preset_match() # Check profile match

    def toggle_category(self, cat_id):
        """Toggle all components in a category"""
        children = self.gui.builder_list.get_children(cat_id)
        if not children: return

        target_check = False
        for child in children:
            if child not in self.checked_components:
                target_check = True
                break
        
        for child in children:
            tags = list(self.gui.builder_list.item(child, "tags"))
            has_priority_color = 'manual' in tags or 'update' in tags

            if target_check:
                self.checked_components.add(child)
                icon = self.CHECKED_ICON
                if not has_priority_color and 'checked' not in tags:
                    tags.insert(1, 'checked')
            else:
                if child in self.checked_components:
                    self.checked_components.remove(child)
                icon = self.UNCHECKED_ICON
                if not has_priority_color and 'checked' in tags:
                    tags.remove('checked')

            current_text = self.gui.builder_list.item(child, "text")
            clean_name = current_text.replace(self.CHECKED_ICON, "").replace(self.UNCHECKED_ICON, "").strip()
            self.gui.builder_list.item(child, text=f"{icon} {clean_name}", tags=tuple(tags))

        self.update_category_checkboxes()
        self.update_selection_count()
        self._check_for_preset_match() # Check profile match

    def builder_select_all(self):
        """Check all visible components"""
        for category in self.gui.builder_list.get_children():
            children = self.gui.builder_list.get_children(category)
            for child in children:
                self.checked_components.add(child)
        
        self.filter_builder_components() 
        self._check_for_preset_match() # Check profile match

    def builder_clear_selection(self):
        """Uncheck all components"""
        self.checked_components.clear()
        
        self.filter_builder_components() 
        self._check_for_preset_match() # Will reset combo to blank

    def on_version_double_click(self, event):
        """Handle double-click on component to edit manual version"""
        region = self.gui.builder_list.identify_region(event.x, event.y)
        if region != "cell" and region != "tree":
            return
        # Get the clicked item
        item = self.gui.builder_list.identify_row(event.y)
        
        # Return "break" for categories to strictly disable default collapse behavior
        if item and item.startswith("CAT_"):
            return "break"

        if not item:
            return

        comp_data = self.gui.components_data.get(item)
        if not comp_data:
            return
        # Show version input dialog
        self.show_version_input_dialog(item, comp_data)

    def show_version_input_dialog(self, comp_id, comp_data):
        """Show dialog to input manual version for a component"""
        dialog = ttk.Toplevel(self.gui.root)
        dialog.title(f"Set Version - {comp_data['name']}")
        dialog.geometry("500x350")
        dialog.transient(self.gui.root)
        dialog.grab_set()

        info_frame = ttk.Frame(dialog, padding=20)
        info_frame.pack(fill=BOTH, expand=True)

        ttk.Label(info_frame, text=f"Component: {comp_data['name']}",
                  font=('Segoe UI', 10, 'bold')).pack(pady=(0, 10))

        ttk.Label(info_frame, text="Enter a specific version to download (e.g., v1.7.1, 6.2.0)\n"
                                   "Leave empty to fetch the latest version automatically.",
                  wraplength=450).pack(pady=(0, 15))
        # Current manual version
        current_manual = self.gui.manual_versions.get(comp_id, "")

        ttk.Label(info_frame, text="Version:").pack(anchor=W)
        version_entry = ttk.Entry(info_frame, width=30)
        version_entry.pack(fill=X, pady=5)
        version_entry.insert(0, current_manual)
        version_entry.focus()
        # Info about current version
        fetched_version = comp_data.get('asset_info', {}).get('version', 'N/A')
        if fetched_version != 'N/A':
            ttk.Label(info_frame, text=f"Latest fetched version: {fetched_version}",
                      font=('Segoe UI', 8), bootstyle="secondary").pack(pady=(5, 0))

        button_frame = ttk.Frame(info_frame)
        button_frame.pack(pady=(15, 0))

        def save_version():
            version = version_entry.get().strip()
            if version:
                self.gui.manual_versions[comp_id] = version
            else:
                # Remove manual version if empty
                self.gui.manual_versions.pop(comp_id, None)
            # Refresh the display
            self.filter_builder_components()
            dialog.destroy()

        def clear_version():
            self.gui.manual_versions.pop(comp_id, None)
            self.filter_builder_components()
            dialog.destroy()

        ttk.Button(button_frame, text="Cancel", command=dialog.destroy,
                   bootstyle="secondary").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=clear_version,
                   bootstyle="warning").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Save", command=save_version,
                   bootstyle="info").pack(side=LEFT, padx=5)
        self.gui.center_window(dialog)

    def fetch_github_versions(self):
        """Fetch latest versions for CHECKED components"""
        # ADAPTATION: Use checked_components instead of treeview selection
        selected = list(self.checked_components)
        if not selected:
            self.gui.show_custom_info("No Selection", "Please check at least one component to fetch versions.")
            return

        if self.fetch_button:
            self.fetch_button.config(state=DISABLED)
        # Create progress window
        progress_window = ttk.Toplevel(self.gui.root)
        progress_window.title("Fetching Versions")
        progress_window.geometry("600x700")
        progress_window.transient(self.gui.root)
        progress_window.grab_set()
        self.gui.center_window(progress_window)

        ttk.Label(progress_window, text="Fetching latest component versions...",
                  font=('Segoe UI', 10, 'bold')).pack(pady=10)

        progress = ttk.Progressbar(progress_window, mode='indeterminate', bootstyle="info")
        progress.pack(fill=X, padx=20, pady=10)
        progress.start()

        log_text = scrolledtext.ScrolledText(progress_window, height=15, width=70, wrap='word')
        log_text.pack(fill=BOTH, expand=True, padx=10, pady=10)
        log_text.config(state='disabled')

        close_btn = ttk.Button(progress_window, text="Close", state=DISABLED,
                               command=progress_window.destroy, bootstyle="primary")
        close_btn.pack(pady=10)
        # Run the fetch in a separate thread
        thread = threading.Thread(target=self._worker_fetch_versions,
                                  args=(progress_window, log_text, progress, close_btn, selected), daemon=True)
        thread.start()

    def _worker_fetch_versions(self, window, log_widget, progress_bar, close_button, selected_ids):
        def log(message):
            try:
                if not log_widget.winfo_exists(): return
                log_widget.config(state='normal')
                log_widget.insert(END, message + "\n")
                log_widget.see(END)
                log_widget.config(state='disabled')
                log_widget.update_idletasks()
            except Exception:
                pass

        # Prepare list of tasks
        tasks = []
        for cid in selected_ids:
            cdata = self.gui.components_data.get(cid)
            if not cdata: continue

            # Skip manual versions (no need to fetch)
            if cid in self.gui.manual_versions:
                continue
    
            tasks.append((cid, cdata))

        total_tasks = len(tasks)
        log(f"Fetching versions for {total_tasks} components...")

        updated_count = 0
        failed_count = 0
        completed_tasks = 0

        # Define the single fetch operation
        def fetch_single(cid, cdata):
            try:
                source_type = cdata.get('source_type')

                # 1. Direct URL Strategy
                if source_type == 'direct_url':
                    url = cdata.get('repo', '')
                    if url:
                        # Try to extract version from URL string first (fastest)
                        version_match = re.search(r'/([vV]?\d+(?:\.\d+)*(?:\.\d+)?)/', url)
                        if version_match:
                            return cid, version_match.group(1), None
                    return cid, None, "No version in URL"

                # 2. GitHub Release Strategy (Finds latest)
                elif source_type == 'github_release' and cdata.get('repo'):
                    repo = cdata['repo']
                    api_url = f"https://api.github.com/repos/{repo}/releases?per_page=10"

                    req = urllib.request.Request(api_url)
                    req.add_header('Accept', 'application/vnd.github.v3+json')
                    req.add_header('User-Agent', 'HATSKit-Pro')

                    pat = self.gui.github_pat.get()
                    if pat:
                        req.add_header('Authorization', f'token {pat}')

                    with urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT) as response:
                        if response.status == 200:
                            releases = json.loads(response.read().decode())
                            if releases:
                                # Find the release with the most recent 'published_at' date
                                latest_release = max(
                                    releases,
                                    key=lambda r: r.get("published_at", "") or ""
                                )
                                latest_version = latest_release.get("tag_name")
                                
                                if latest_version:
                                    return cid, latest_version, None
                                return cid, None, "No version tag found"
                            return cid, None, "No releases found"
                        else:
                            return cid, None, f"HTTP {response.status}"

                # 3. GitHub Tag Strategy
                elif source_type == 'github_tag':
                    # For pinned tags, the "latest" version is simply the tag itself.
                    # We return it directly without an API call.
                    tag = cdata.get('tag')
                    if tag:
                        return cid, tag, None
                    return cid, None, "Missing 'tag' in config"

                return cid, None, f"Skipped/Unknown Type: {source_type}"

            except urllib.error.HTTPError as e:
                if e.code == 403:
                    return cid, None, "RATE LIMIT EXCEEDED (Use a PAT)"
                return cid, None, f"HTTP {e.code}"
            except Exception as e:
                return cid, None, str(e)

        # Execute in parallel (Max 5 workers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_cid = {executor.submit(fetch_single, cid, cdata): (cid, cdata) for cid, cdata in tasks}

            for future in concurrent.futures.as_completed(future_to_cid):
                if not window.winfo_exists():
                    executor.shutdown(wait=False)
                    break

                cid, cdata = future_to_cid[future]
                try:
                    res_cid, version, error = future.result()

                    if version:
                        log(f"  ✅ {cdata['name']}: {version}")
                        if 'asset_info' not in self.gui.components_data[res_cid]:
                            self.gui.components_data[res_cid]['asset_info'] = {}
                        self.gui.components_data[res_cid]['asset_info']['version'] = version
                        updated_count += 1
                    else:
                        log(f"  ❌ {cdata['name']}: {error}")
                        failed_count += 1

                except Exception as exc:
                    log(f"  ❌ {cdata['name']}: Exception {exc}")
                    failed_count += 1

                completed_tasks += 1
                if total_tasks > 0:
                    try:
                        progress_bar.configure(mode='determinate', value=(completed_tasks/total_tasks)*100)
                    except: pass

        if updated_count > 0:
            self.gui.save_components_file()

        def on_complete():
            if self.fetch_button:
                try: self.fetch_button.config(state=NORMAL)
                except: pass

            self.filter_builder_components()

            if window.winfo_exists():
                try:
                    progress_bar.stop()
                    close_button.config(state=NORMAL)

                    msg = f"Updated: {updated_count}\nFailed: {failed_count}"
                    if failed_count > 0 and not self.gui.github_pat.get():
                        msg += "\n\nTip: Failures may be due to GitHub API rate limits.\nConsider adding a PAT in Settings."

                    self.gui.show_custom_info("Fetch Complete", msg, parent=window, height=280)
                except: pass

        self.gui.root.after(100, on_complete)
        
    def build_pack(self):
        """Build the HATS pack using checked components"""
        # ADAPTATION: Use checked_components instead of treeview selection
        selected = list(self.checked_components)
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select at least one component to build.")
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        date_str = now.strftime("%d%m%Y")
        initial_file = f"HATS-{date_str}-building.zip"

        output_file = filedialog.asksaveasfilename(
            title="Save HATS Pack",
            defaultextension=".zip",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            initialfile=initial_file
        )

        if not output_file:
            return

        build_comment = self.gui.build_comment.get().strip()
        self.show_build_progress(selected, output_file, build_comment)
        """Show build progress window"""
    def show_build_progress(self, selected, output_file, build_comment=""):
        progress_window = ttk.Toplevel(self.gui.root)
        progress_window.title("Building Pack")
        progress_window.geometry("700x700")
        progress_window.transient(self.gui.root)
        progress_window.grab_set()
        self.gui.center_window(progress_window)
        
        ttk.Label(progress_window, text="Building HATS Pack...",
                  font=('Segoe UI', 10, 'bold')).pack(pady=10)
        
        progress = ttk.Progressbar(progress_window, length=100, mode='determinate', bootstyle="success")
        progress.pack(fill=X, padx=20, pady=10)
        
        log_text = scrolledtext.ScrolledText(progress_window, height=20, width=80, wrap='word')
        log_text.pack(fill=BOTH, expand=True, padx=10, pady=10)
        log_text.config(state='disabled')

        close_btn = ttk.Button(progress_window, text="Close", state=DISABLED,
                               command=progress_window.destroy, bootstyle="primary")
        close_btn.pack(pady=10)
        # Run build in a separate thread
        thread = threading.Thread(target=self._worker_build_pack, 
                                  args=(selected, output_file, progress_window, log_text, progress, close_btn, build_comment), 
                                  daemon=True)
        thread.start()

    def _worker_build_pack(self, selected_ids, output_file, window, log_widget, progress_bar, close_button, build_comment=""):
        """Worker thread to build the HATS pack (Clean Log Version)."""

        # Thread-safe logging helper
        def log(message):
            try:
                if not log_widget.winfo_exists(): return
                log_widget.config(state='normal')
                log_widget.insert(END, message + "\n")
                log_widget.see(END)
                log_widget.config(state='disabled')
                log_widget.update_idletasks()
            except Exception:
                pass

        def update_progress(value, mode='determinate'):
            try:
                if window.winfo_exists():
                    progress_bar.configure(mode=mode, value=value)
            except: pass

        # Initialize
        total_components = len(selected_ids)
        download_results = {}
        failed_components = []

        last_build_fw = self.gui.last_build_data.get('supported_firmware', 'N/A')
        manifest = {
            "pack_name": Path(output_file).name,
            "build_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "builder_version": self.gui.VERSION,
            "supported_firmware": last_build_fw,
            "content_hash": "pending",
            "components": {}
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir) / "downloads"
            staging_dir = Path(temp_dir) / "staging"
            download_dir.mkdir()
            staging_dir.mkdir()

            # ==============================================================================
            # PHASE 1: PARALLEL DOWNLOADS
            # ==============================================================================
            log(f"--- PHASE 1: Downloading {total_components} Components ---")
            log("(Please wait, this may take a moment based on your internet speed...)\n")
            update_progress(0, 'indeterminate')

            def download_single_component(comp_id):
                comp_data = self.gui.components_data.get(comp_id)
                if not comp_data: return False, "Definition not found"

                # Version logic
                manual_version = self.gui.manual_versions.get(comp_id, "")
                version_to_build = manual_version if manual_version else comp_data.get('asset_info', {}).get('version', 'N/A')
    
                # 1. Log Start
                log(f"⏳ [{comp_data['name']}] Downloading ({version_to_build})...")

                asset_configs = self._get_asset_configs(comp_data)
                if not asset_configs: return False, "No asset patterns defined"

                downloaded_assets = []

                # Define a silent logger that only lets CRITICAL ERRORS through
                def silent_log(msg):
                    if any(x in msg for x in ["❌", "⚠️", "Error", "Failed", "HTTP"]):
                        log(f"  [{comp_data['name']}] {msg.strip()}")

                for asset_config in asset_configs:
                    try:
                        asset_path = self._download_asset(
                            comp_data,
                            download_dir,
                            silent_log, # Use silent logger
                            pattern=asset_config.get('pattern'),
                            version=version_to_build
                        )

                        if not asset_path: return False, "Download failed (check log for details)"
                        downloaded_assets.append((asset_path, asset_config.get('processing_steps', [])))

                    except Exception as e:
                        return False, f"Exception: {e}"

                # Calculate total size for the "Done" message
                total_size_mb = sum(p[0].stat().st_size for p in downloaded_assets) / (1024*1024)
    
                # 2. Log Finish
                log(f"✅ [{comp_data['name']}] Ready ({total_size_mb:.2f} MB)")

                return True, {
                    'comp_id': comp_id,
                    'comp_data': comp_data,
                    'version': version_to_build,
                    'assets': downloaded_assets
                }

            # Execute Downloads
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_id = {executor.submit(download_single_component, cid): cid for cid in selected_ids}

                completed_downloads = 0
                for future in concurrent.futures.as_completed(future_to_id):
                    if not window.winfo_exists():
                        executor.shutdown(wait=False)
                        return

                    cid = future_to_id[future]
                    try:
                        success, result = future.result()
                        if success:
                            download_results[cid] = result
                        else:
                            failed_components.append((cid, result))
                    except Exception as e:
                        failed_components.append((cid, str(e)))

                    completed_downloads += 1
                    update_progress((completed_downloads / total_components) * 40, 'determinate')

            if failed_components:
                log("\n❌ Critical Download Errors:")
                for cid, err in failed_components:
                    name = self.gui.components_data.get(cid, {}).get('name', cid)
                    log(f"  • {name}: {err}")
                self.gui.root.after(100, lambda: [close_button.config(state=NORMAL), self.gui.show_custom_info("Build Failed", "Downloads failed.", parent=window)])
                return

            # ==============================================================================
            # PHASE 2: SEQUENTIAL PROCESSING
            # ==============================================================================
            log(f"\n\n--- PHASE 2: Processing & Extracting ---")

            current_step = 0
            for comp_id in selected_ids:
                if not window.winfo_exists(): return
                result = download_results.get(comp_id)
                if not result: continue

                comp_data = result['comp_data']

                # Cleaner Processing Header
                log(f"\n⚙️ {comp_data['name']}")
    
                all_component_files = []
                component_failed = False

                for asset_path, steps in result['assets']:
                    try:
                        # We use a lambda to indent the processing steps
                        indent_log = lambda m: log(f"   {m.strip()}")
                        processed_files = self._process_asset(asset_path, comp_data, staging_dir, indent_log, processing_steps=steps)

                        if processed_files is None:
                            component_failed = True
                            break
                        all_component_files.extend(processed_files)
                    except Exception as e:
                        log(f"   ❌ Error: {e}")
                        component_failed = True
                        break

                if component_failed:
                    self.gui.root.after(100, lambda: [close_button.config(state=NORMAL), self.gui.show_custom_info("Error", f"Failed to process {comp_data['name']}", parent=window)])
                    return

                # Add to Manifest
                manifest['components'][comp_id] = {
                    "name": comp_data['name'],
                    "version": result['version'],
                    "category": comp_data.get('category', 'Unknown'),
                    "repo": comp_data.get('repo', ''),
                    "files": [str(p.relative_to(staging_dir)).replace('\\', '/') for p in all_component_files]
                }

                if comp_id == "atmosphere":
                    firmware_ver, _ = self.get_atmosphere_firmware_info(result['version'], lambda m: None)
                    if firmware_ver != "N/A": manifest['supported_firmware'] = firmware_ver

                current_step += 1
                update_progress(40 + ((current_step / total_components) * 50))

            # ==============================================================================
            # PHASE 3: FINALIZING
            # ==============================================================================
            log("\n\n--- PHASE 3: Finalizing Pack ---")

            # Skeleton
            skeleton_path = Path("assets/skeleton.zip")
            if skeleton_path.exists():
                log("📦 Adding base skeleton...")
                with zipfile.ZipFile(skeleton_path, 'r') as zip_ref:
                    zip_ref.extractall(staging_dir)

            # Hash & Manifest
            log("📝 Generating manifest and summary...")
            selected_components = {cid: self.gui.components_data[cid] for cid in selected_ids}
            manifest['content_hash'] = self.compute_content_hash(selected_components)

            final_base_name = f"HATS-{datetime.datetime.now().strftime('%d%m%Y')}-{manifest['content_hash']}"
            output_path = Path(output_file)
            final_output_file = output_path.parent / f"{final_base_name}.zip"
            manifest['pack_name'] = f"{final_base_name}.zip"

            manifest_path = staging_dir / "manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)

            self._generate_metadata_file(staging_dir, final_base_name, manifest, build_comment)

            # Zip
            log(f"💾 Compressing to {final_base_name}.zip...")
            update_progress(95)
            try:
                with zipfile.ZipFile(final_output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in staging_dir.rglob('*'):
                        arcname = file_path.relative_to(staging_dir)
                        zipf.write(file_path, arcname)
            except Exception as e:
                log(f"❌ ZIP Error: {e}")
                self.gui.root.after(100, lambda: close_button.config(state=NORMAL))
                return

            update_progress(100)
            self.gui.last_build_data = manifest
            try:
                with open(self.gui.MANIFEST_FILE, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, indent=2)
            except: pass

        log("\n🎉 Build complete!")
        self.gui.root.after(100, lambda: [
            close_button.config(state=NORMAL),
            self.gui.prepare_for_install(str(final_output_file)),
            self.gui.show_custom_info("Build Complete", f"HATS Pack successfully built!\n\nSaved to:\n{final_output_file}", parent=window, height=320)
        ])
        
    def _generate_metadata_file(self, staging_dir, base_name, manifest, build_comment):
        """Helper to generate the text summary file inside the pack"""
        metadata_path = staging_dir / f"{base_name}.txt"
        last_build_components = self.gui.last_build_data.get('components', {})

        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write("# HATS Pack Summary\n\n")
            f.write(f"**Generated on:** {datetime.datetime.now(datetime.timezone.utc).strftime('%d-%m-%Y %H:%M:%S')} UTC  \n")
            f.write(f"**Builder Version:** {manifest.get('builder_version', self.gui.VERSION)}-GUI  \n")

            if manifest.get('content_hash'):
                f.write(f"**Content Hash:** {manifest['content_hash']}  \n")

            supported_fw = manifest.get('supported_firmware', 'N/A')
            if supported_fw != "N/A":
                f.write(f"**Supported Firmware:** Up to {supported_fw}  \n")

            f.write("\n---\n\n")

            version_changes = []
            for comp_id, comp_data in manifest['components'].items():
                last_comp = last_build_components.get(comp_id)
                if last_comp and last_comp.get('version') != comp_data['version']:
                    version_changes.append(f"- **{comp_data['name']}:** {last_comp.get('version')} → **{comp_data['version']}**")

            if version_changes or build_comment:
                f.write("## CHANGELOG\n\n")
                if build_comment:
                    f.write(f"### Build Notes:\n{build_comment}\n\n")
                if version_changes:
                    f.write("### Version Updates:\n")
                    for change in version_changes:
                        f.write(f"{change}\n")
                f.write("\n---\n\n")

            f.write("## INCLUDED COMPONENTS\n")
            components_by_category = {}
            for comp_id, comp_data in manifest['components'].items():
                category = comp_data.get('category', 'Uncategorized')
                if category not in components_by_category:
                    components_by_category[category] = []
                components_by_category[category].append(comp_data)

            for category, components in sorted(components_by_category.items()):
                f.write(f"\n### {category.upper()}\n")
                for comp in sorted(components, key=lambda x: x['name']):
                    f.write(f"- **{comp['name']}** ({comp['version']})\n")

            f.write("\n---\nGenerated with HATSKit Pro Builder\n")

    def _get_asset_configs(self, comp_data):
        """
        Get list of asset configurations from component data.
        Handles both old (single asset) and new (multiple assets) formats.

        Returns: list of dict with 'pattern' and 'processing_steps'
        """
        # New format: multiple assets
        if 'asset_patterns' in comp_data:
            return comp_data['asset_patterns']
        # Old format: single asset (convert to list for uniform processing)
        elif 'asset_pattern' in comp_data:
            return [{
                'pattern': comp_data['asset_pattern'],
                'processing_steps': comp_data.get('processing_steps', [])
            }]
        return []

    def compute_content_hash(self, selected_components):
        """Compute a content hash based on selected components and their versions."""
        hasher = hashlib.sha1()
        for comp_id in sorted(selected_components.keys()):
            version = selected_components[comp_id].get('asset_info', {}).get('version', 'N/A')
            hasher.update(f"{comp_id}:{version}".encode('utf-8'))
        return hasher.hexdigest()[:7]

    def extract_firmware_version_from_body(self, release_body):
        """Extract supported firmware version from Atmosphere release body."""
        if not release_body:
            return "N/A"
        pattern_1 = re.search(r'(?:support|support was added|HOS)\s*.*?(?:for|up to)\s*(\d+\.\d+\.\d+)',
                             release_body, re.IGNORECASE)
        if pattern_1:
            return pattern_1.group(1)
        match_2 = re.search(r'(?:HOS|firmware)\s*(\d+\.\d+\.\d+)', release_body, re.IGNORECASE)
        if match_2:
            return match_2.group(1)
        match_3 = re.search(r'supports\s*up\s*to\s*(\d+\.\d+\.\d+)', release_body, re.IGNORECASE)
        if match_3:
            return match_3.group(1)
        return "N/A"

    def get_atmosphere_firmware_info(self, atmosphere_version, log=None):
        """Fetch firmware info for a specific Atmosphere version."""
        try:
            api_url = f"https://api.github.com/repos/{self.ATMOSPHERE_REPO}/releases?per_page=3"
            req = urllib.request.Request(api_url)
            req.add_header('Accept', 'application/vnd.github.v3+json')
            pat = self.gui.github_pat.get()
            if pat:
                req.add_header('Authorization', f'token {pat}')
            if log:
                log(f"  Fetching Atmosphere release info to determine supported firmware...")
            with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
                releases = json.loads(response.read().decode())
            clean_version = atmosphere_version.lstrip('v')
            latest_known_fw = "N/A"
            target_fw = "N/A"
            content_hash = "N/A"
            for release in releases:
                tag = release.get('tag_name', '').lstrip('v')
                body = release.get('body', '')
                fw_found = self.extract_firmware_version_from_body(body)
                if fw_found != "N/A":
                    latest_known_fw = fw_found
                    current_fw = fw_found
                else:
                    current_fw = latest_known_fw
                if tag == clean_version:
                    target_fw = current_fw
                    hash_match = re.search(r'-([a-f0-9]{7,})', release.get('tag_name', ''))
                    if hash_match:
                        content_hash = hash_match.group(1)[:7]
                    break
            if log:
                if target_fw != "N/A":
                    log(f"  ✅ Atmosphere {atmosphere_version} supports firmware up to {target_fw}")
                else:
                    log(f"  ⚠️ Could not determine firmware support for Atmosphere {atmosphere_version}")
            return target_fw, content_hash
        except Exception as e:
            if log:
                log(f"  ⚠️ Error fetching Atmosphere firmware info: {e}")
            return "N/A", "N/A"

    def _download_asset(self, comp_data, temp_dir, log, pattern=None, version=None):
        """
        Downloads the asset for a component with progress tracking and timeout.

        Args:
            comp_data: Component configuration
            temp_dir: Temporary directory for downloads
            log: Logging function
            pattern: Specific asset pattern to download (for multi-asset components)
            version: Specific version to download (if None, fetches latest)
        """
        source_type = comp_data.get('source_type')
        if source_type == 'github_release':
            repo = comp_data.get('repo')
            if not pattern:
                pattern = comp_data.get('asset_pattern')
            if not repo or not pattern:
                log("  ❌ Invalid component: missing 'repo' or 'asset_pattern'.")
                return None
            # Fetch releases - more if looking for specific version
            per_page = 10 if version and version != 'N/A' else 5
            api_url = f"https://api.github.com/repos/{repo}/releases?per_page={per_page}"
            if version and version != 'N/A':
                log(f"  Fetching release info for version {version}...")
            else:
                log(f"  Fetching latest release info...")
            req = urllib.request.Request(api_url)
            pat = self.gui.github_pat.get()
            if pat:
                req.add_header('Authorization', f'token {pat}')
            try:
                with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
                    releases = json.loads(response.read().decode())
                    if releases:
                        target_release = None
                        # If specific version requested, find it
                        if version and version != 'N/A':
                            for release in releases:
                                tag = release.get('tag_name', '')
                                # Match with or without 'v' prefix
                                if tag == version or tag == f"v{version}" or tag.lstrip('v') == version.lstrip('v'):
                                    target_release = release
                                    log(f"  ✅ Found release: {tag}")
                                    break
                            if not target_release:
                                log(f"  ❌ Version '{version}' not found in recent releases.")
                                return None
                        else:
                            # No specific version, use latest
                            target_release = releases[0]
                        # Download asset from target release
                        for asset in target_release.get('assets', []):
                            if fnmatch.fnmatch(asset['name'].lower(), pattern.lower()):
                                url = asset['browser_download_url']
                                filename = Path(temp_dir) / asset['name']
                                asset_size = asset.get('size', 0)
                                log(f"  Downloading: {url}")
                                if asset_size > 0:
                                    size_mb = asset_size / (1024 * 1024)
                                    log(f"  Size: {size_mb:.2f} MB")
                                # Use improved download method with progress
                                success = self._download_file_with_progress(url, filename, log)
                                if success:
                                    log(f"  ✅ Downloaded to: {filename.name}")
                                    return filename
                                else:
                                    log(f"  ❌ Download failed")
                                    return None
                        log(f"  ❌ Asset matching '{pattern}' not found in release {target_release.get('tag_name')}.")
                    else:
                        log(f"  ❌ No releases found for repository '{repo}'.")
            except urllib.error.HTTPError as e:
                log(f"  ❌ HTTP Error {e.code}: {e.reason}")
                return None
        elif source_type == "github_tag":
            repo = comp_data.get("repo")
            tag = comp_data.get("tag")
            if not pattern:
                pattern = comp_data.get("asset_pattern")
            if not repo or not tag or not pattern:
                log("  ❌ Invalid github_tag component configuration.")
                return None
            api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
            log(f"  Fetching tagged release: {tag}")
            req = urllib.request.Request(api_url)
            pat = self.gui.github_pat.get()
            if pat:
                req.add_header("Authorization", f"token {pat}")
            try:
                with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
                    release = json.loads(response.read().decode())
                for asset in release.get("assets", []):
                    if fnmatch.fnmatch(asset["name"].lower(), pattern.lower()):
                        url = asset["browser_download_url"]
                        filename = Path(temp_dir) / asset["name"]
                        log(f"  Downloading: {url}")
                        if self._download_file_with_progress(url, filename, log):
                            log(f"  ✅ Downloaded to: {filename.name}")
                            return filename
                log(f"  ❌ Asset matching '{pattern}' not found in tag {tag}")
                return None
            except Exception as e:
                log(f"  ❌ Failed to fetch github tag '{tag}': {e}")
                return None
        elif source_type == 'direct_url':
            url = comp_data.get('repo')  # For direct_url, the URL is stored in 'repo' field
            if not url:
                log("  ❌ Invalid component: missing 'repo' (URL) for direct_url type.")
                return None
            # Extract filename from URL
            filename = Path(url).name
            if not filename:
                filename = "downloaded_file"
            filepath = Path(temp_dir) / filename
            log(f"  Downloading from direct URL: {url}")
            try:
                # Use improved download method with progress
                success = self._download_file_with_progress(url, filepath, log)
                if success:
                    log(f"  ✅ Downloaded to: {filename}")
                    # Extract version from URL (e.g., /658/ -> 658, /v1.2.3/ -> v1.2.3)
                    # Look for patterns like /number/ or /vX.X.X/ in the URL path
                    version_match = re.search(r'/([vV]?\d+(?:\.\d+)*(?:\.\d+)?)/', url)
                    if version_match:
                        extracted_version = version_match.group(1)
                        log(f"  ℹ️ Extracted version from URL: {extracted_version}")
                        # Store the version in asset_info for later use
                        if 'asset_info' not in comp_data:
                            comp_data['asset_info'] = {}
                        comp_data['asset_info']['version'] = extracted_version
                    return filepath
                else:
                    log(f"  ❌ Download failed")
                    return None
            except Exception as e:
                log(f"  ❌ Failed to download from direct URL: {e}")
                return None
        else:
            log(f"  ❌ Unsupported source_type: '{source_type}'")
            return None

    def _download_file_with_progress(self, url, filepath, log, timeout=120, retries=2):
        """
        Download a file with progress tracking, timeout, and retry logic.

        Args:
            url: URL to download from
            filepath: Local path to save file
            log: Logging function
            timeout: Download timeout in seconds (default: 120)
            retries: Number of retry attempts (default: 2)

        Returns:
            bool: True if download succeeded, False otherwise
        """
        for attempt in range(retries + 1):
            try:
                if attempt > 0:
                    log(f"  ⟳ Retry attempt {attempt}/{retries}...")
                # Create request with timeout
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'HATSKit-Pro-Builder')
                # Open connection with timeout
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    # Get file size if available
                    file_size = int(response.headers.get('Content-Length', 0))
                    # Download in chunks with progress
                    chunk_size = 8192  # 8 KB chunks
                    downloaded = 0
                    # last_percent = -1  # Unused
                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                    # Verify download
                    if file_size > 0 and downloaded < file_size:
                        log(f"  ⚠️ Incomplete download: {downloaded} / {file_size} bytes")
                        if attempt < retries:
                            continue
                        return False
                    return True
            except urllib.error.URLError as e:
                log(f"  ⚠️ Download error: {e.reason}")
                if attempt < retries:
                    import time
                    time.sleep(2)  # Wait before retry
                    continue
                return False
            except Exception as e:
                log(f"  ⚠️ Unexpected error: {e}")
                if attempt < retries:
                    import time
                    time.sleep(2)
                    continue
                return False
        return False

    def _process_asset(self, asset_path, comp_data, staging_dir, log, processing_steps=None):
        """
        Processes a downloaded asset based on component's processing_steps.

        Args:
            asset_path: Path to downloaded asset
            comp_data: Component configuration
            staging_dir: Staging directory for extraction
            log: Logging function
            processing_steps: Specific processing steps (for multi-asset components)
        """
        if processing_steps is None:
            steps = comp_data.get('processing_steps', [])
        else:
            steps = processing_steps
        all_processed_files = []
        if not steps: # If no steps, assume it's a simple zip to root
            steps = [{"action": "unzip_to_root"}]
        for step in steps:
            action = step.get('action')
            log(f"  - Executing step: {action}")
            if action == 'unzip_to_root':
                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    zip_ref.extractall(staging_dir)
                    # Record all extracted files for the manifest
                    all_processed_files.extend(
                        staging_dir / member.filename for member in zip_ref.infolist() if not member.is_dir()
                    )
            elif action == 'unzip_to_path':
                target_path_str = step.get('target_path', '').lstrip('/')
                if not target_path_str:
                    log("    ❌ 'unzip_to_path' is missing 'target_path'.")
                    continue
                target_dir = staging_dir / target_path_str
                target_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    zip_ref.extractall(target_dir)
                    # Record all extracted files for the manifest
                    all_processed_files.extend(
                        target_dir / member.filename for member in zip_ref.infolist() if not member.is_dir()
                    )
                log(f"    ✅ Extracted to: {target_path_str}")
            elif action == 'copy_file':
                target_dir_str = step.get('target_path', '').lstrip('/')
                if not target_dir_str:
                    log("    ❌ 'copy_file' is missing 'target_path'.")
                    continue
                # target_path is a directory, use original filename
                target_dir = staging_dir / target_dir_str
                target_dir.mkdir(parents=True, exist_ok=True)
                # Get the filename from the downloaded asset
                filename = asset_path.name
                target_path = target_dir / filename
                shutil.copy(asset_path, target_path)
                all_processed_files.append(target_path)
                log(f"    ✅ Copied to: {target_path.relative_to(staging_dir)}")
            elif action == 'find_and_rename':
                pattern = step.get('source_file_pattern')
                target_name = step.get('target_filename')
                target_folder_str = step.get('target_path', '/').lstrip('/')
                if not pattern or not target_name:
                    log("    ❌ 'find_and_rename' is missing 'source_file_pattern' or 'target_filename'.")
                    continue
                found = False
                for f in staging_dir.rglob(pattern):
                    target_folder = staging_dir / target_folder_str
                    target_folder.mkdir(parents=True, exist_ok=True)
                    new_path = target_folder / target_name
                    shutil.move(str(f), new_path)
                    all_processed_files.append(new_path)
                    log(f"    ✅ Renamed '{f.name}' to '{new_path.relative_to(staging_dir)}'")
                    found = True
                    break
                if not found:
                    log(f"    ⚠️ Could not find file matching '{pattern}' to rename.")
            elif action == 'delete_file':
                path_str = step.get('path', '').lstrip('/')
                if not path_str:
                    log("    ❌ 'delete_file' is missing 'path'.")
                    continue
                found = False
                # Use rglob to find matching files/folders
                for item_to_delete in staging_dir.rglob(path_str):
                    try:
                        if item_to_delete.is_dir():
                            shutil.rmtree(item_to_delete)
                        else:
                            item_to_delete.unlink()
                        log(f"    ✅ Deleted: {item_to_delete.relative_to(staging_dir)}")
                        found = True
                    except OSError as e:
                        log(f"    ❌ Error deleting {item_to_delete.name}: {e}")
                if not found:
                    log(f"    ⚠️ Could not find '{path_str}' to delete.")
            elif action == 'find_and_copy':
                pattern = step.get('source_file_pattern')
                target_folder_str = step.get('target_path', '/').lstrip('/')
                if not pattern:
                    log("    ❌ 'find_and_copy' is missing 'source_file_pattern'.")
                    continue
                # Extract ZIP to temp directory to inspect contents
                with tempfile.TemporaryDirectory(dir=asset_path.parent) as extract_dir:
                    extract_dir_path = Path(extract_dir)
                    with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir_path)
                        # Track newest file per filename
                        newest_by_name = {}
                        for f in extract_dir_path.rglob(pattern):
                            zip_path = f.relative_to(extract_dir_path).as_posix()
                            try:
                                info = zip_ref.getinfo(zip_path)
                                # ZipInfo.date_time = (Y, M, D, H, M, S)
                                mtime = datetime.datetime(*info.date_time).timestamp()
                            except KeyError:
                                # Fallback to filesystem mtime
                                try:
                                    mtime = f.stat().st_mtime
                                except OSError:
                                    continue
                            current = newest_by_name.get(f.name)
                            if current is None or mtime > current[1]:
                                newest_by_name[f.name] = (f, mtime)
                    if not newest_by_name:
                        log(f"    ⚠️ Could not find file matching '{pattern}' in the archive.")
                    else:
                        target_folder = staging_dir / target_folder_str
                        target_folder.mkdir(parents=True, exist_ok=True)
                        for fname, (src_path, _) in newest_by_name.items():
                            dest = target_folder / fname
                            if src_path.is_dir():
                                shutil.copytree(src_path, dest, dirs_exist_ok=True)
                                for f in dest.rglob('*'):
                                    if f.is_file():
                                        all_processed_files.append(f)
                                log(f"    ✅ Copied directory '{fname}' to '{dest.relative_to(staging_dir)}'")
                            else:
                                shutil.copy(src_path, dest)
                                all_processed_files.append(dest)
                                log(f"    ✅ Copied newest '{fname}' to '{dest.relative_to(staging_dir)}'")
            elif action == 'unzip_subfolder_to_root':
                subfolder_name = step.get('subfolder_name', '').strip('/')
                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    if subfolder_name:
                        source_folder = subfolder_name.rstrip('/') + '/'
                        log(f"    🔍 Using specified source folder: '{subfolder_name}'")
                    else:
                        # Auto-detect single top-level directory
                        top_level_dirs = {name.split('/')[0] for name in zip_ref.namelist() if '/' in name}
                        if len(top_level_dirs) == 1:
                            source_folder = top_level_dirs.pop() + '/'
                            log(f"    ✅ Auto-detected source folder: '{source_folder.strip('/')}'")
                        elif len(top_level_dirs) == 0:
                            log("    ❌ 'unzip_subfolder_to_root' failed: No subfolders found in the archive.")
                            continue
                        else:
                            log(f"    ❌ 'unzip_subfolder_to_root' failed: Multiple root folders found ({', '.join(top_level_dirs)}).")
                            continue
                    extracted = False
                    for member in zip_ref.infolist():
                        if member.filename.startswith(source_folder):
                            target_path = member.filename[len(source_folder):]
                            if not target_path:
                                continue
                            member.filename = target_path
                            zip_ref.extract(member, staging_dir)
                            if not member.is_dir():
                                all_processed_files.append(staging_dir / target_path)
                                extracted = True
                    if not extracted:
                        log(f"    ⚠️ No files extracted from '{source_folder}'")
            else:
                log(f"    ⚠️ Unimplemented action: {action}")
        return all_processed_files