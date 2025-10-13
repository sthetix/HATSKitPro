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

            with urllib.request.urlopen(req, timeout=15) as response:
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

            self.gui.builder_list.insert('', END, iid=comp_id,
                                         values=(display_name, category))

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

            # Priority: Use fetched version from asset_info if available, otherwise from last_build.json
            version = comp.get('asset_info', {}).get('version', 'N/A')

            # If no fetched version, try last build version
            if version == 'N/A' and comp_id in last_build_components:
                version = last_build_components[comp_id].get('version', 'N/A')

            # If still no version and it's a direct_url, try to extract from URL for preview
            if version == 'N/A' and comp.get('source_type') == 'direct_url':
                url = comp.get('repo', '')
                if url:
                    version_match = re.search(r'/([vV]?\d+(?:\.\d+)*(?:\.\d+)?)/', url)
                    if version_match:
                        version = version_match.group(1)

            self.gui.builder_preview.insert('', END, values=(comp.get('name', comp_id),
                                                              version,
                                                              comp.get('category', 'Unknown')))

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

        # Show progress window
        self.show_build_progress(selected, output_file)
    
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
        """Worker thread to fetch versions from GitHub API for selected components."""
        def log(message):
            log_widget.config(state='normal')
            log_widget.insert(END, message + "\n")
            log_widget.see(END)
            log_widget.config(state='disabled')
            log_widget.update_idletasks()

        updated_count = 0
        failed_count = 0

        # Only check selected GitHub release components
        components_to_check = []
        direct_url_components = []
        other_skipped_components = []

        for cid in selected_ids:
            cdata = self.gui.components_data.get(cid)
            if not cdata:
                continue

            source_type = cdata.get('source_type')

            if source_type == 'direct_url':
                direct_url_components.append((cid, cdata))
            elif source_type == 'github_release' and cdata.get('repo'):
                components_to_check.append((cid, cdata))
            else:
                other_skipped_components.append((cid, cdata))

        log(f"Found {len(components_to_check)} GitHub components to fetch...")

        # Process direct URL components to extract versions from URLs
        if len(direct_url_components) > 0:
            log(f"\nProcessing {len(direct_url_components)} direct URL components...")
            for cid, cdata in direct_url_components:
                url = cdata.get('repo', '')
                log(f"Checking: {cdata.get('name', cid)}")

                if url:
                    # Extract version from URL
                    version_match = re.search(r'/([vV]?\d+(?:\.\d+)*(?:\.\d+)?)/', url)
                    if version_match:
                        extracted_version = version_match.group(1)
                        log(f"  -> Extracted version from URL: {extracted_version}")

                        # Store the version in asset_info
                        if 'asset_info' not in self.gui.components_data[cid]:
                            self.gui.components_data[cid]['asset_info'] = {}
                        self.gui.components_data[cid]['asset_info']['version'] = extracted_version
                        updated_count += 1
                    else:
                        log(f"  -> Could not extract version from URL: {url}")
                        failed_count += 1
                else:
                    log(f"  -> No URL found for component")
                    failed_count += 1

        if len(other_skipped_components) > 0:
            log(f"\nSkipped {len(other_skipped_components)} other non-GitHub components")

        for comp_id, comp_data in components_to_check:
            repo = comp_data['repo']
            # Fetch the list of releases. The first one is always the newest.
            api_url = f"https://api.github.com/repos/{repo}/releases?per_page=1"
            log(f"Checking: {comp_data['name']} ({repo})")

            try:
                req = urllib.request.Request(api_url)
                req.add_header('Accept', 'application/vnd.github.v3+json')
                pat = self.gui.github_pat.get()
                if pat:
                    req.add_header('Authorization', f'token {pat}')

                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        releases = json.loads(response.read().decode())
                        if releases:
                            latest_release = releases[0]
                            latest_version = latest_release.get('tag_name')

                            if latest_version:
                                log(f"  -> Found latest version: {latest_version}")
                                # Create asset_info dict if it doesn't exist
                                if 'asset_info' not in self.gui.components_data[comp_id]:
                                    self.gui.components_data[comp_id]['asset_info'] = {}
                                self.gui.components_data[comp_id]['asset_info']['version'] = latest_version
                                updated_count += 1
                            else:
                                log(f"  -> No version tag found in the latest release.")
                                failed_count += 1
                        else:
                            log(f"  -> No releases found for repository.")
                            failed_count += 1
                    else:
                        log(f"  -> FAILED: HTTP {response.status}")
                        failed_count += 1
            except Exception as e:
                log(f"  -> ERROR: {e}")
                failed_count += 1

        total_skipped = len(other_skipped_components)

        log("\n" + "="*30)
        log("Fetch complete!")
        log(f"Updated: {updated_count} | Failed: {failed_count} | Skipped: {total_skipped}")

        # Stop progress and re-enable button from the main thread
        summary = f"Finished checking versions.\nUpdated: {updated_count}\nFailed: {failed_count}"
        if total_skipped > 0:
            summary += f"\nSkipped: {total_skipped} (other components)"

        # Save components.json if versions were updated
        if updated_count > 0:
            self.gui.save_components_file()

        self.gui.root.after(100, lambda: [
            progress_bar.stop(),
            self.fetch_button.config(state=NORMAL),
            close_button.config(state=NORMAL),
            self.update_builder_preview(), # Update the preview to show new versions
            self.gui.show_custom_info("Fetch Complete", summary, parent=window, height=250)
        ])

    def show_build_progress(self, selected, output_file):
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
                                  args=(selected, output_file, progress_window, log_text, progress, close_btn), 
                                  daemon=True)
        thread.start()

    def _worker_build_pack(self, selected_ids, output_file, window, log_widget, progress_bar, close_button):
        """Worker thread to build the HATS pack."""
        def log(message):
            log_widget.config(state='normal')
            log_widget.insert(END, message + "\n")
            log_widget.see(END)
            log_widget.config(state='disabled')
            log_widget.update_idletasks()

        def update_progress(value):
            progress_bar['value'] = value
            progress_bar.update_idletasks()

        total_steps = len(selected_ids) + 2 # (download/process per component + manifest + zip)
        current_step = 0

        # Check if we should inherit firmware info from last build
        last_build_fw = self.gui.last_build_data.get('supported_firmware', 'N/A')

        manifest = {
            "pack_name": Path(output_file).name,
            "build_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "builder_version": self.gui.VERSION,
            "supported_firmware": last_build_fw,  # Inherit from last build initially
            "content_hash": "pending",            # Will be computed after downloads
            "components": {}
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            staging_dir = Path(temp_dir) / "staging"
            staging_dir.mkdir()
            log(f"Created temporary staging area: {staging_dir}")

            # --- New Logic: Always extract local skeleton.zip first ---
            skeleton_path = Path("assets/skeleton.zip")
            if skeleton_path.exists():
                log("▶ Processing base skeleton...")
                try:
                    with zipfile.ZipFile(skeleton_path, 'r') as zip_ref:
                        zip_ref.extractall(staging_dir)
                    log("  ✅ Skeleton extracted successfully.")
                except Exception as e:
                    log(f"  ❌ FAILED to extract skeleton.zip: {e}")
            else:
                log("⚠️ WARNING: assets/skeleton.zip not found. Pack may be incomplete.")

            for comp_id in selected_ids:
                comp_data = self.gui.components_data.get(comp_id)
                if not comp_data:
                    log(f"❌ ERROR: Component '{comp_id}' not found in definitions. Skipping.")
                    continue
                
                # 1. Download asset
                try:
                    version_to_build = comp_data.get('asset_info', {}).get('version', 'N/A')
                    log(f"\n▶ Processing: {comp_data['name']} ({version_to_build})")
                    asset_path = self._download_asset(comp_data, Path(temp_dir), log)
                    if not asset_path:
                        log(f"  ❌ FAILED to download. Skipping component.")
                        continue
                except Exception as e:
                    log(f"  ❌ FAILED during download: {e}. Skipping component.")
                    continue

                # 2. Process asset
                try:
                    processed_files = self._process_asset(asset_path, comp_data, staging_dir, log)
                    if processed_files is None: # Error occurred
                        log(f"  ❌ FAILED during processing. Skipping component.")
                        continue
                    manifest['components'][comp_id] = {
                        "name": comp_data['name'],
                        "version": version_to_build,
                        "category": comp_data.get('category', 'Unknown'),
                        "files": [str(p.relative_to(staging_dir)).replace('\\', '/') for p in processed_files]
                    }

                    # 3. If this is Atmosphere, fetch firmware support info
                    if comp_id == "atmosphere":
                        log(f"\n▶ Scanning Atmosphere release for firmware support info...")
                        firmware_ver, _ = self.get_atmosphere_firmware_info(version_to_build, log)
                        manifest['supported_firmware'] = firmware_ver
                        # Note: We keep using the computed content_hash from all components

                except Exception as e:
                    log(f"  ❌ FAILED during processing: {e}. Skipping component.")
                    continue

                current_step += 1
                update_progress((current_step / total_steps) * 100)

            # --- Compute content hash AFTER all downloads are complete ---
            log("\n▶ Computing content hash from downloaded versions...")
            selected_components = {comp_id: self.gui.components_data[comp_id] for comp_id in selected_ids if comp_id in self.gui.components_data}
            content_hash = self.compute_content_hash(selected_components)
            manifest['content_hash'] = content_hash
            log(f"  ✅ Content hash: {content_hash}")

            # --- Determine final filename with correct hash ---
            now = datetime.datetime.now(datetime.timezone.utc)
            date_str = now.strftime("%d%m%Y")
            final_base_name = f"HATS-{date_str}-{content_hash}"

            # Determine the final output path
            output_path = Path(output_file)
            final_output_file = output_path.parent / f"{final_base_name}.zip"

            # Update manifest with the correct pack name
            manifest['pack_name'] = f"{final_base_name}.zip"

            # --- Generate metadata files ---

            # 3. Create manifest
            log("\n▶ Generating manifest.json...")
            manifest_path = staging_dir / "manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            log("  ✅ Manifest created.")
            current_step += 1
            update_progress((current_step / total_steps) * 100)

            # 4. Create ZIP file
            log("\n▶ Creating ZIP archive...")
            try:
                # --- Generate the single metadata .txt file ---
                metadata_path = staging_dir / f"{final_base_name}.txt"
                log(f"▶ Generating {metadata_path.name}...")
                last_build_components = self.gui.last_build_data.get('components', {})

                with open(metadata_path, 'w', encoding='utf-8') as f:
                    f.write("===================================\n")
                    f.write(f"HATS Pack Summary")
                    f.write("===================================\n\n")
                    f.write(f"Generated on: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
                    f.write(f"Builder Version: {manifest.get('builder_version', self.gui.VERSION)}-GUI\n")

                    # Add content hash if available
                    if manifest.get('content_hash') and manifest['content_hash'] != "N/A":
                        f.write(f"Content Hash: {manifest['content_hash']}\n")

                    # Add supported firmware info
                    supported_fw = manifest.get('supported_firmware', 'N/A')
                    if supported_fw != "N/A":
                        f.write(f"Supported Firmware: Up to {supported_fw}\n")

                    f.write("\n")
                    
                    version_changes = []
                    for comp_id, comp_data in manifest['components'].items():
                        last_comp = last_build_components.get(comp_id)
                        # Only show version changes, not newly added/removed components
                        if last_comp and last_comp.get('version') != comp_data['version']:
                            version_changes.append(f"- {comp_data['name']}: {last_comp.get('version')} -> {comp_data['version']}")

                    if version_changes:
                        f.write("--- CHANGELOG (What's New Since Last Build) ---\n")
                        for change in version_changes:
                            f.write(f"{change}\n")
                        f.write("-------------------------------------------------\n\n")

                    # --- Included Components Section ---
                    f.write("--- INCLUDED COMPONENTS ---\n")
                    
                    # Group components by category
                    components_by_category = {}
                    for comp_id, comp_data in manifest['components'].items():
                        category = comp_data.get('category', 'Uncategorized')
                        if category not in components_by_category:
                            components_by_category[category] = []
                        components_by_category[category].append(comp_data)

                    for category, components in sorted(components_by_category.items()):
                        f.write(f"\n--- {category.upper()} ---\n")
                        for comp in sorted(components, key=lambda x: x['name']):
                            f.write(f" - {comp['name']} ({comp['version']})\n")

                log(f"  ✅ {metadata_path.name} created.")

                with zipfile.ZipFile(final_output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in staging_dir.rglob('*'):
                        arcname = file_path.relative_to(staging_dir)
                        zipf.write(file_path, arcname)
                log(f"  ✅ Pack saved to: {final_output_file}")
            except Exception as e:
                log(f"  ❌ FAILED to create ZIP: {e}")
                self.gui.root.after(100, lambda: close_button.config(state=NORMAL))
                return

            current_step += 1
            update_progress(100)

            # 5. Save local manifest.json (for last build reference)
            self.gui.last_build_data = manifest
            try:
                with open(self.gui.MANIFEST_FILE, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, indent=2)
                log("  ✅ Updated local manifest.json (last build reference).")
            except Exception as e:
                log(f"  ⚠️ Could not save local manifest.json: {e}")

        log("\n🎉 Build complete!")
        self.gui.root.after(100, lambda: [
            close_button.config(state=NORMAL),
            self.gui.prepare_for_install(str(final_output_file)),
            self.gui.show_custom_info("Build Complete", f"HATS Pack successfully built!\n\nSaved to:\n{final_output_file}\n\nThe Manager tab is now ready for installation.", parent=window, height=320)
        ])

    def _download_asset(self, comp_data, temp_dir, log):
        """Downloads the asset for a component."""
        source_type = comp_data.get('source_type')
        if source_type == 'github_release':
            repo = comp_data.get('repo')
            pattern = comp_data.get('asset_pattern')
            if not repo or not pattern:
                log("  ❌ Invalid component: missing 'repo' or 'asset_pattern'.")
                return None

            # Fetch the list of releases. The first one is always the newest,
            # regardless of whether it's a pre-release or a full release.
            api_url = f"https://api.github.com/repos/{repo}/releases?per_page=1"
            log(f"  Fetching latest release info...")

            req = urllib.request.Request(api_url)
            pat = self.gui.github_pat.get()
            if pat:
                req.add_header('Authorization', f'token {pat}')

            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    releases = json.loads(response.read().decode())
                    if releases:
                        latest_release = releases[0] # The first one is the newest
                        for asset in latest_release.get('assets', []):
                            if fnmatch.fnmatch(asset['name'].lower(), pattern.lower()):
                                url = asset['browser_download_url']
                                filename = Path(temp_dir) / asset['name']
                                log(f"  Downloading: {url}")
                                urllib.request.urlretrieve(url, filename)
                                log(f"  ✅ Downloaded to: {filename.name}")
                                return filename
                        log(f"  ❌ Asset matching '{pattern}' not found in the latest release ({latest_release.get('tag_name')}).")
                    else:
                        log(f"  ❌ No releases found for repository '{repo}'.")
            except urllib.error.HTTPError as e:
                log(f"  ❌ HTTP Error {e.code}: {e.reason}")
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
                urllib.request.urlretrieve(url, filepath)
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
            except Exception as e:
                log(f"  ❌ Failed to download from direct URL: {e}")
                return None
        else:
            log(f"  ❌ Unsupported source_type: '{source_type}'")
            return None

    def _process_asset(self, asset_path, comp_data, staging_dir, log):
        """Processes a downloaded asset based on component's processing_steps."""
        steps = comp_data.get('processing_steps', [])
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

                # Unzip to a temporary location to search inside
                with tempfile.TemporaryDirectory(dir=asset_path.parent) as extract_dir:
                    with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                    
                    found = False
                    for f in Path(extract_dir).rglob(pattern):
                        target_folder = staging_dir / target_folder_str
                        target_folder.mkdir(parents=True, exist_ok=True)
                        new_path = target_folder / f.name
                        shutil.copy(str(f), new_path)
                        all_processed_files.append(new_path)
                        log(f"    ✅ Found and copied '{f.name}' to '{new_path.relative_to(staging_dir)}'")
                        found = True
                    
                    if not found:
                        log(f"    ⚠️ Could not find file matching '{pattern}' in the archive.")
            elif action == 'unzip_subfolder_to_root':
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