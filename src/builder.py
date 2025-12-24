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

# Global SSL context using certifi CA bundle (macOS fix)
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Override urllib's default HTTPS context globally
ssl._create_default_https_context = lambda: SSL_CONTEXT

class PackBuilder:
    """Handles Pack Builder functionality"""

    ATMOSPHERE_REPO = "Atmosphere-NX/Atmosphere"

    def __init__(self, main_gui):
        """Initialize with reference to main GUI"""
        self.gui = main_gui
        self.fetch_button = None # To hold a reference to the button

        # Connect event handlers to UI widgets
        self.connect_events()
    
    def connect_events(self):
        """Connect event handlers to UI elements"""
        # Search and filter
        self.gui.builder_search.bind('<KeyRelease>', self.filter_builder_components)
        self.gui.builder_category_filter.bind('<<ComboboxSelected>>', self.filter_builder_components)

        # Selection change
        self.gui.builder_list.bind('<<TreeviewSelect>>', self.on_builder_selection_change)

        # Double-click to edit version
        self.gui.builder_list.bind('<Double-Button-1>', self.on_version_double_click)

        # Get button references and connect commands
        # We need to find the buttons in the UI and connect them
        builder_buttons = self.gui.builder_tab.winfo_children()
        self._connect_builder_buttons()
    
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
                        self.fetch_button = child # Store reference
                    elif text == "View Details":
                        child.config(command=self.show_component_details)
                    elif text == "Build Pack":
                        child.config(command=self.build_pack)
                find_buttons(child)
        
        find_buttons(self.gui.builder_tab)

    def on_version_double_click(self, event):
        """Handle double-click on component to edit manual version"""
        region = self.gui.builder_list.identify_region(event.x, event.y)
        if region != "cell":
            return

        # Get the clicked item
        item = self.gui.builder_list.identify_row(event.y)
        if not item:
            return

        comp_id = item
        comp_data = self.gui.components_data.get(comp_id)
        if not comp_data:
            return

        # Show version input dialog
        self.show_version_input_dialog(comp_id, comp_data)

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
            self.update_builder_preview()
            dialog.destroy()

        def clear_version():
            self.gui.manual_versions.pop(comp_id, None)
            self.filter_builder_components()
            self.update_builder_preview()
            dialog.destroy()

        ttk.Button(button_frame, text="Save", command=save_version,
                   bootstyle="primary").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=clear_version,
                   bootstyle="warning").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy,
                   bootstyle="secondary").pack(side=LEFT, padx=5)

        self.gui.center_window(dialog)

    def compute_content_hash(self, selected_components):
        """
        Compute a content hash based on selected components and their versions.
        This provides a unique identifier for the pack contents.
        """
        hasher = hashlib.sha1()
        for comp_id in sorted(selected_components.keys()):
            version = selected_components[comp_id].get('asset_info', {}).get('version', 'N/A')
            hasher.update(f"{comp_id}:{version}".encode('utf-8'))
        return hasher.hexdigest()[:7]

    def extract_firmware_version_from_body(self, release_body):
        """
        Extract supported firmware version from Atmosphere release body.
        Based on atmos.py logic with inheritance support.
        """
        if not release_body:
            return "N/A"

        # 1. PRIMARY PATTERN: "Basic support was added for 20.4.0" (or similar)
        pattern_1 = re.search(r'(?:support|support was added|HOS)\s*.*?(?:for|up to)\s*(\d+\.\d+\.\d+)',
                             release_body, re.IGNORECASE)
        if pattern_1:
            return pattern_1.group(1)

        # 2. FALLBACK PATTERN: Explicit HOS/firmware mention
        match_2 = re.search(r'(?:HOS|firmware)\s*(\d+\.\d+\.\d+)', release_body, re.IGNORECASE)
        if match_2:
            return match_2.group(1)

        # 3. SECONDARY FALLBACK: General "supports up to" mention
        match_3 = re.search(r'supports\s*up\s*to\s*(\d+\.\d+\.\d+)', release_body, re.IGNORECASE)
        if match_3:
            return match_3.group(1)

        return "N/A"

    def get_atmosphere_firmware_info(self, atmosphere_version, log=None):
        """
        Fetch firmware info for a specific Atmosphere version.
        Uses inheritance logic from previous releases if current release doesn't specify.

        Returns: (firmware_version, content_hash)
        """
        try:
            # Fetch recent releases to build inheritance chain (3 is enough for inheritance)
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

            # Clean the atmosphere version for comparison
            clean_version = atmosphere_version.lstrip('v')

            # Build firmware mapping with inheritance
            latest_known_fw = "N/A"
            target_fw = "N/A"
            content_hash = "N/A"

            for release in releases:
                tag = release.get('tag_name', '').lstrip('v')
                body = release.get('body', '')

                # Extract firmware from this release
                fw_found = self.extract_firmware_version_from_body(body)

                # Update inheritance tracker
                if fw_found != "N/A":
                    latest_known_fw = fw_found
                    current_fw = fw_found
                else:
                    current_fw = latest_known_fw

                # Check if this is our target version
                if tag == clean_version:
                    target_fw = current_fw
                    # Extract content hash from tag or commit
                    # Typically format: "1.9.3-master-8b8e4438e"
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

    def populate_builder_list(self):
        """Populate builder list with components"""
        # Clear existing items
        for item in self.gui.builder_list.get_children():
            self.gui.builder_list.delete(item)
        
        components = self.gui.components_data
        categories = set(comp.get('category', 'Unknown') for comp in components.values())
        
        # Update category filter
        self.gui.builder_category_filter['values'] = ['All Categories'] + sorted(list(categories))
        self.gui.builder_category_filter.set('All Categories')
        
        # Now, populate the list using the filter logic
        self.filter_builder_components(initial_load=True)
    
    def filter_builder_components(self, event=None, initial_load=False):
        """Filter components based on search and category. Also handles initial population."""
        
        if not initial_load:
            selected_ids = self.gui.builder_list.selection()

        search_term = self.gui.builder_search.get().lower()
        category_filter = self.gui.builder_category_filter.get()
        last_build_components = self.gui.last_build_data.get('components', {})

        for item in self.gui.builder_list.get_children():
            self.gui.builder_list.delete(item)

        for comp_id, comp_data in sorted(self.gui.components_data.items(), key=lambda x: x[1]['name']):
            name = comp_data['name'].lower()
            category = comp_data['category']

            # Apply filters
            if search_term and search_term not in name:
                continue
            if category_filter != 'All Categories' and category != category_filter:
                continue

            display_name = comp_data['name']

            # Get manual version if set
            manual_version = self.gui.manual_versions.get(comp_id, "Latest")

            self.gui.builder_list.insert('', END, iid=comp_id,
                                         values=(display_name, category, manual_version))

        # Handle selection
        if initial_load: # On first load, prioritize last build, then defaults
            if last_build_components: # Restore from last build
                for comp_id in last_build_components:
                    if self.gui.builder_list.exists(comp_id):
                        self.gui.builder_list.selection_add(comp_id)
            else: # Or, select defaults
                for comp_id, comp_data in self.gui.components_data.items():
                    if comp_data.get('default', False) and self.gui.builder_list.exists(comp_id):
                        self.gui.builder_list.selection_add(comp_id)
        else: # On subsequent filters, just re-apply the previous selection
            for comp_id in selected_ids: 
                if self.gui.builder_list.exists(comp_id):
                    self.gui.builder_list.selection_add(comp_id)
        
        self.update_builder_preview()

    def on_builder_selection_change(self, event=None):
        """Update preview when selection changes"""
        self.update_builder_preview()
    
    def update_builder_preview(self):
        """Update the selected components preview"""
        # Clear preview
        for item in self.gui.builder_preview.get_children():
            self.gui.builder_preview.delete(item)

        # Get selected items
        selected = self.gui.builder_list.selection()

        # Get last build components for version info
        last_build_components = self.gui.last_build_data.get('components', {})

        # Update preview
        for comp_id in selected:
            comp = self.gui.components_data.get(comp_id, {})

            # Priority 1: Manual version input (highest priority)
            manual_version = self.gui.manual_versions.get(comp_id, "")

            # Priority 2: Use fetched version from asset_info if available
            fetched_version = comp.get('asset_info', {}).get('version', 'N/A')

            # Determine which version to use
            if manual_version:
                version = manual_version
            else:
                version = fetched_version

            # Priority 3: If no fetched version and no manual, try last build version
            if version == 'N/A' and comp_id in last_build_components:
                version = last_build_components[comp_id].get('version', 'N/A')

            # Priority 4: If still no version and it's a direct_url, try to extract from URL for preview
            if version == 'N/A' and comp.get('source_type') == 'direct_url':
                url = comp.get('repo', '')
                if url:
                    version_match = re.search(r'/([vV]?\d+(?:\.\d+)*(?:\.\d+)?)/', url)
                    if version_match:
                        version = version_match.group(1)
                        if not manual_version:
                            fetched_version = version  # Update fetched_version for comparison

            # Determine component name and check if it's new/updated
            display_name = comp.get('name', comp_id)
            is_updated = False

            # Check if this component has a newer version than last build
            if comp_id in last_build_components and fetched_version != 'N/A':
                last_build_version = last_build_components[comp_id].get('version', 'N/A')
                # If versions differ, mark as updated
                if last_build_version != 'N/A' and fetched_version != last_build_version:
                    display_name = display_name + " *"
                    is_updated = True

            # Insert with appropriate tag
            item_id = self.gui.builder_preview.insert('', END, values=(display_name,
                                                                        version,
                                                                        comp.get('category', 'Unknown')))
            if is_updated:
                self.gui.builder_preview.item(item_id, tags=('updated',))

        # Update label
        count = len(selected)
        self.gui.selection_label.config(text=f"Selected: {count} components")
    
    def builder_select_all(self):
        """Select all visible components"""
        for item in self.gui.builder_list.get_children():
            self.gui.builder_list.selection_add(item)
        self.update_builder_preview()
    
    def builder_clear_selection(self):
        """Clear all selections"""
        self.gui.builder_list.selection_remove(self.gui.builder_list.selection())
        self.update_builder_preview()
    
    def show_component_details(self):
        """Show detailed component information"""
        selected = self.gui.builder_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select at least one component to view details.")
            return
        
        # Create details window
        details_window = ttk.Toplevel(self.gui.root)
        details_window.title("Component Details")
        details_window.geometry("700x500")
        details_window.transient(self.gui.root)
        
        # Create table
        table_frame = ttk.Frame(details_window, padding=10)
        table_frame.pack(fill=BOTH, expand=True)
        
        tree = ttk.Treeview(table_frame, columns=('Name', 'Version', 'Category', 'Description'),
                              show='headings', bootstyle="primary")
        
        tree.heading('Name', text='Component Name')
        tree.heading('Version', text='Version')
        tree.heading('Category', text='Category')
        tree.heading('Description', text='Description')
        
        tree.column('Name', width=150)
        tree.column('Version', width=80)
        tree.column('Category', width=120)
        tree.column('Description', width=300)
        
        scroll = ttk.Scrollbar(table_frame, orient=VERTICAL, command=tree.yview, bootstyle="primary-round")
        tree.configure(yscrollcommand=scroll.set)
        
        scroll.pack(side=RIGHT, fill=Y)
        tree.pack(fill=BOTH, expand=True)
        
        # Populate
        for comp_id in selected:
            comp = self.gui.components_data.get(comp_id, {})
            version = comp.get('asset_info', {}).get('version', 'N/A')
            desc = comp.get('description', 'No description')
            if isinstance(desc, dict):
                desc = desc.get('descriptions', {}).get('en', 'No description')
            tree.insert('', END, values=(comp.get('name', comp_id),
                                          version,
                                          comp.get('category', 'Unknown'), 
                                          desc))
        
        # Close button
        ttk.Button(details_window, text="Close", command=details_window.destroy,
                   bootstyle="secondary").pack(pady=10)

        # Center the window using the main GUI's helper
        self.gui.center_window(details_window) 

    def build_pack(self):
        """Build the HATS pack"""
        selected = self.gui.builder_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select at least one component to build.")
            return

        # Ask where to save - use temporary name, we'll rename after computing hash
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

        # Get build comment
        build_comment = self.gui.build_comment.get().strip()

        # Show progress window
        self.show_build_progress(selected, output_file, build_comment)
    
    def fetch_github_versions(self):
        """Fetch latest versions from GitHub for components without a specific version set"""
        # Check if any components are selected
        selected = self.gui.builder_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select at least one component to fetch versions.")
            return

        if self.fetch_button:
            self.fetch_button.config(state=DISABLED)

        # Create progress window
        progress_window = ttk.Toplevel(self.gui.root)
        progress_window.title("Fetching Versions")
        progress_window.geometry("600x650")
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
                    api_url = f"https://api.github.com/repos/{repo}/releases?per_page=1"

                    req = urllib.request.Request(api_url)
                    req.add_header('Accept', 'application/vnd.github.v3+json')
                    req.add_header('User-Agent', 'HATSKit-Pro')

                    pat = self.gui.github_pat.get()
                    if pat:
                        req.add_header('Authorization', f'token {pat}')

                    with urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT) as response:
                        if response.status == 200:
                            data = json.loads(response.read().decode())
                            if data and isinstance(data, list):
                                latest = max(data, key=lambda r: r.get("published_at", ""))
                                return cid, latest.get("tag_name"), None
                            return cid, None, "No releases found"
                        else:
                            return cid, None, f"HTTP {response.status}"

                # 3. GitHub Tag Strategy (Pinned Version) [OPTIMIZED FEATURE]
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

    def show_build_progress(self, selected, output_file, build_comment=""):
        """Show build progress window"""
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
        """Worker thread to build the HATS pack (Parallel Version)."""

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

            # --- PHASE 1: PARALLEL DOWNLOADS ---
            log(f"--- PHASE 1: Downloading {total_components} Components ---")
            log("(Please wait, this may take a moment based on your internet speed...)\n")
            update_progress(0, 'indeterminate')

            def download_single_component(comp_id):
                comp_data = self.gui.components_data.get(comp_id)
                if not comp_data: return False, "Definition not found"

                # Version logic
                manual_version = self.gui.manual_versions.get(comp_id, "")
                version_to_build = manual_version if manual_version else comp_data.get('asset_info', {}).get('version', 'N/A')

                log(f"⏳ [{comp_data['name']}] Downloading ({version_to_build})...")

                asset_configs = self._get_asset_configs(comp_data)
                if not asset_configs: return False, "No asset patterns defined"

                downloaded_assets = []

                # Silent logger for parallel threads to avoid clutter
                def silent_log(msg):
                    if any(x in msg for x in ["❌", "⚠️", "Error", "Failed", "HTTP"]):
                        log(f"  [{comp_data['name']}] {msg.strip()}")

                for asset_config in asset_configs:
                    try:
                        asset_path = self._download_asset(
                            comp_data,
                            download_dir,
                            silent_log,
                            pattern=asset_config.get('pattern'),
                            version=version_to_build
                        )

                        if not asset_path: return False, "Download failed (check log)"
                        downloaded_assets.append((asset_path, asset_config.get('processing_steps', [])))

                    except Exception as e:
                        return False, f"Exception: {e}"

                total_size_mb = sum(p[0].stat().st_size for p in downloaded_assets) / (1024*1024)
                log(f"✅ [{comp_data['name']}] Ready ({total_size_mb:.2f} MB)")

                return True, {
                    'comp_id': comp_id,
                    'comp_data': comp_data,
                    'version': version_to_build,
                    'assets': downloaded_assets
                }

            # Execute Parallel Downloads [NEW FEATURE]
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

            # --- PHASE 2: SEQUENTIAL PROCESSING ---
            log(f"\n\n--- PHASE 2: Processing & Extracting ---")

            current_step = 0
            for comp_id in selected_ids:
                if not window.winfo_exists(): return
                result = download_results.get(comp_id)
                if not result: continue

                comp_data = result['comp_data']
                log(f"\n⚙️ {comp_data['name']}")

                all_component_files = []
                component_failed = False

                for asset_path, steps in result['assets']:
                    try:
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

            # --- PHASE 3: FINALIZING ---
            log("\n\n--- PHASE 3: Finalizing Pack ---")

            skeleton_path = Path("assets/skeleton.zip")
            if skeleton_path.exists():
                log("📦 Adding base skeleton...")
                with zipfile.ZipFile(skeleton_path, 'r') as zip_ref:
                    zip_ref.extractall(staging_dir)

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

    def _generate_metadata_file(self, staging_dir, base_name, manifest, comment):
        """Generate a readable text file with pack details"""
        info_path = staging_dir / "pack_info.txt"

        try:
            with open(info_path, 'w', encoding='utf-8') as f:
                f.write(f"HATS Pack Info\n")
                f.write(f"==============\n\n")
                f.write(f"Name: {base_name}\n")
                f.write(f"Date: {manifest['build_date']}\n")
                f.write(f"Builder Version: {manifest['builder_version']}\n")
                f.write(f"Content Hash: {manifest['content_hash']}\n")
                f.write(f"Firmware Support: {manifest.get('supported_firmware', 'N/A')}\n")

                if comment:
                    f.write(f"\nComment:\n{comment}\n")

                f.write(f"\nComponents:\n")
                f.write(f"-----------\n")

                for cid, data in manifest.get('components', {}).items():
                    f.write(f"- {data['name']} ({data['version']})\n")

        except Exception as e:
            print(f"Error generating metadata file: {e}")

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
                                log(f"     Available versions: {', '.join([r.get('tag_name', 'N/A') for r in releases[:5]])}")
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
                    last_percent = -1

                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Log progress every 10%
                            if file_size > 0:
                                percent = int((downloaded / file_size) * 100)
                                if percent >= last_percent + 10 and percent <= 100:
                                    log(f"  ⬇ {percent}% ({downloaded / (1024*1024):.1f} MB / {file_size / (1024*1024):.1f} MB)")
                                    last_percent = percent

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
                            log(
                                "    ❌ 'unzip_subfolder_to_root' failed: "
                                f"Multiple root folders found ({', '.join(top_level_dirs)}). "
                                "Specify 'subfolder_name'."
                            )
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

                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    # Automatically find the single top-level directory
                    top_level_dirs = {name.split('/')[0] for name in zip_ref.namelist() if '/' in name}
                    
                    if len(top_level_dirs) == 1:
                        found_folder = top_level_dirs.pop() + '/'
                        log(f"    ✅ Found single source folder: '{found_folder.strip('/')}'")
                    elif len(top_level_dirs) == 0:
                        log("    ❌ 'unzip_subfolder_to_root' failed: No subfolders found in the archive.")
                        continue
                    else:
                        log(f"    ❌ 'unzip_subfolder_to_root' failed: Ambiguous archive with multiple root folders: {', '.join(top_level_dirs)}")
                        continue

                    # Extract contents of the found folder
                    for member in zip_ref.infolist():
                        if member.filename.startswith(found_folder):
                            # Calculate the new path by stripping the source folder prefix
                            target_path = member.filename.replace(found_folder, '', 1)
                            if not target_path: # Skip the root folder itself
                                continue

                            member.filename = target_path # Temporarily modify member for extraction
                            zip_ref.extract(member, staging_dir)
                            
                            # Record the final path in the staging directory for the manifest
                            if not member.is_dir():
                                all_processed_files.append(staging_dir / target_path)
            else:
                log(f"    ⚠️ Unimplemented action: {action}")
        
        return all_processed_files