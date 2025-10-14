#!/usr/bin/env python3
"""
HATSKit Pro v1.0.0 - Main GUI Skeleton
A unified tool for building and managing HATS packs
"""

# Required packages marker for launcher dependency scanner
REQUIRED_PACKAGES = ['ttkbootstrap', 'requests']

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
import json
import os

# Import our modules
from src.builder import PackBuilder
from src.editor import ComponentEditor
from src.manager import PackManager

VERSION = "1.0.0"
CONFIG_FILE = 'config.json'
COMPONENTS_FILE = 'components.json'
MANIFEST_FILE = 'manifest.json'

# Dummy data as fallback
DUMMY_COMPONENTS = {
    "atmosphere": {
        "name": "Atmosphère",
        "version": "1.7.0",
        "category": "Essential",
        "description": "Custom firmware for Nintendo Switch",
        "default": True
    },
    "hekate": {
        "name": "Hekate",
        "version": "6.2.0",
        "category": "Essential",
        "description": "Custom bootloader",
        "default": True
    },
    "tinfoil": {
        "name": "Tinfoil",
        "version": "19.0",
        "category": "Homebrew Apps",
        "description": "Title installer",
        "default": False
    }
}

def load_json_file(filepath):
    """Load JSON file with error handling"""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        messagebox.showerror("Error", f"Failed to load {filepath}:\n{e}")
        return None


class HATSKitProGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"HATSKit Pro v{VERSION}")
        self.root.geometry("1100x1100")
        self.root.resizable(True, True)
        
        # Variables
        self.github_pat = ttk.StringVar()
        self.sd_path = ttk.StringVar()
        self.component_vars = {}
        self.components_data = {}
        self.config_data = {}
        self.last_build_data = {}
        self.MANIFEST_FILE = MANIFEST_FILE # Make it an instance attribute
        self.VERSION = VERSION # Make it an instance attribute
        
        self.create_menu()
        
        # Load data files before creating UI
        self.load_components_file()
        self.load_last_build_file()
        self.load_config()
        
        self.create_main_ui()
        
        # Initialize modules AFTER UI is created
        self.builder = PackBuilder(self)
        self.editor = ComponentEditor(self)
        self.manager = PackManager(self)
        
        # Populate initial data
        self.builder.populate_builder_list()
        self.editor.populate_editor_list()

    def load_config(self):
        """Load config.json and apply settings"""
        self.config_data = load_json_file(CONFIG_FILE) or {}
        pat = self.config_data.get('github_pat')
        if pat:
            self.github_pat.set(pat)
            print("Loaded GitHub PAT from config.")
        else:
            print("No GitHub PAT found in config.")

    def save_config(self):
        """Save current config to config.json"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4)
        except IOError as e:
            self.show_custom_info("Error", f"Failed to save {CONFIG_FILE}:\n{e}", width=450)
    
    def load_components_file(self):
        """Load components.json"""
        data = load_json_file(COMPONENTS_FILE)
        if data:
            self.components_data = data
            print(f"Loaded {len(data)} components from {COMPONENTS_FILE}")
        else:
            self.components_data = DUMMY_COMPONENTS
            print(f"Using dummy data - {COMPONENTS_FILE} not found")
    
    def load_last_build_file(self):
        """Load manifest.json (last build reference)"""
        data = load_json_file(MANIFEST_FILE)
        if data:
            self.last_build_data = data
            print(f"Loaded last build info: {data.get('pack_name', 'N/A')}")
        else:
            self.last_build_data = {}
            print("No manifest.json found")

    def save_components_file(self):
        """Save the current components data to components.json"""
        try:
            with open(COMPONENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.components_data, f, indent=2, sort_keys=True)
        except IOError as e:
            self.show_custom_info("Error", f"Failed to save {COMPONENTS_FILE}:\n{e}", width=450)
            
    def create_menu(self):
        """Create top menu bar"""
        menubar = ttk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = ttk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Reload Components", command=self.reload_components)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Settings menu
        settings_menu = ttk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="GitHub PAT", command=self.show_pat_settings)
        settings_menu.add_command(label="Download Settings", command=self.show_download_settings)
        
        # Help menu
        help_menu = ttk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
    
    def reload_components(self, show_info=True):
        """Reload components.json and refresh UI"""
        self.load_components_file()
        self.load_last_build_file()
        self.builder.populate_builder_list()
        self.editor.populate_editor_list()
        if show_info:
            self.show_custom_info("Reloaded", f"Loaded {len(self.components_data)} components")
        
    def prepare_for_install(self, pack_path):
        """Prepares the Manager tab for installation after a successful build."""
        # Set the pack path in the manager
        self.pack_path.set(pack_path)

        # Enable install button if SD path is also set
        self.manager.update_install_button_state()

        # Switch to the manager tab
        self.notebook.select(self.manager_tab)

    def create_main_ui(self):
        """Create main tabbed interface"""
        # Header
        header_frame = ttk.Frame(self.root, padding="10")
        header_frame.pack(fill=X)

        ttk.Label(header_frame, text="HATSKit Pro",
                  font=('Segoe UI', 18, 'bold')).pack()
        ttk.Label(header_frame, text="Build, Edit, and Manage HATS Packs",
                  font=('Segoe UI', 10)).pack()

        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self.root, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Tab 1: Pack Builder
        self.builder_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.builder_tab, text="Pack Builder")
        self.create_builder_tab_ui()

        # Tab 2: Component Editor
        self.editor_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.editor_tab, text="Component Editor")
        self.create_editor_tab_ui()

        # Tab 3: Manager
        self.manager_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.manager_tab, text="Manager")
        self.create_manager_tab_ui()

        # Status bar
        status_text = f"Loaded {len(self.components_data)} components"
        if self.last_build_data:
            pack_name = self.last_build_data.get('pack_name', 'N/A')
            # Extract the build info from pack name (e.g., "HATS-10102025-124501.zip" -> "HATS-10102025-124501")
            if pack_name != 'N/A' and pack_name.endswith('.zip'):
                pack_name = pack_name[:-4]  # Remove .zip extension
            status_text += f" | Last build: {pack_name}"
        self.status_bar = ttk.Label(self.root, text=status_text, relief=SUNKEN, anchor=W)
        self.status_bar.pack(side=BOTTOM, fill=X)

    def show_about(self):
        """Show about dialog"""
        about_dialog = ttk.Toplevel(self.root)
        about_dialog.title("About HATSKit Pro")
        about_dialog.geometry("400x480")
        about_dialog.transient(self.root)
        about_dialog.grab_set()
        
        info_frame = ttk.Frame(about_dialog, padding=30)
        info_frame.pack(fill=BOTH, expand=True)
        
        ttk.Label(info_frame, text="HATSKit Pro",
                  font=('Segoe UI', 16, 'bold')).pack(pady=(0, 5))
        ttk.Label(info_frame, text=f"Version {VERSION}",
                  font=('Segoe UI', 10)).pack(pady=(0, 20))
        
        ttk.Label(info_frame, text="A unified tool for building and managing\n"
                                   "HATS packs for Nintendo Switch CFW",
                  justify=CENTER, wraplength=350).pack(pady=(0, 20))
        
        ttk.Label(info_frame, text="Features:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(10, 5))
        
        features = [
            "• Build custom HATS packs",
            "• Edit component definitions",
            "• Manage installed components",
            "• Trash bin with restore capability"
        ]
        for feature in features:
            ttk.Label(info_frame, text=feature).pack(anchor=W, padx=10)
        
        ttk.Button(info_frame, text="Close", command=about_dialog.destroy,
                   bootstyle="primary").pack(pady=(20, 0))
        
        self.center_window(about_dialog)

    def create_builder_tab_ui(self):
        """Create Pack Builder tab UI only (logic in builder.py)"""
        # Info panel
        info_frame = ttk.LabelFrame(self.builder_tab, text="Information", padding="10")
        info_frame.pack(fill=X, padx=10, pady=5)
        
        ttk.Label(info_frame, text="Select components to include in your HATS pack. Use Ctrl+Click or Shift+Click to select multiple.",
                font=('Segoe UI', 9)).pack()
        
        # Main content area
        content_frame = ttk.Frame(self.builder_tab)
        content_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # LEFT PANEL
        left_frame = ttk.LabelFrame(content_frame, text="Available Components", padding="10")
        left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 5))
        
        # Search box
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=X, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side=LEFT, padx=(0, 5))
        self.builder_search = ttk.Entry(search_frame)
        self.builder_search.pack(side=LEFT, fill=X, expand=True)
        
        # Category filter
        filter_frame = ttk.Frame(left_frame)
        filter_frame.pack(fill=X, pady=(0, 5))
        ttk.Label(filter_frame, text="Category:").pack(side=LEFT, padx=(0, 5))
        self.builder_category_filter = ttk.Combobox(filter_frame, state="readonly", width=15)
        self.builder_category_filter.pack(side=LEFT)
        
        # Component list
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=BOTH, expand=True)
        
        list_scroll = ttk.Scrollbar(list_frame, bootstyle="primary-round")
        list_scroll.pack(side=RIGHT, fill=Y)
        
        self.builder_list = ttk.Treeview(
            list_frame,
            columns=('name', 'category'),
            show='headings',
            yscrollcommand=list_scroll.set,
            selectmode='extended',
            bootstyle="primary"
        )

        self.builder_list.heading('name', text='Component Name')
        self.builder_list.heading('category', text='Category')

        self.builder_list.column('name', width=250, minwidth=150)
        self.builder_list.column('category', width=150, minwidth=80)
        
        list_scroll.config(command=self.builder_list.yview)
        self.builder_list.pack(fill=BOTH, expand=True)
        
        # Buttons under list
        left_buttons = ttk.Frame(left_frame)
        left_buttons.pack(fill=X, pady=(5, 0))
        ttk.Button(left_buttons, text="Select All", bootstyle="secondary").pack(side=LEFT, padx=2)
        ttk.Button(left_buttons, text="Clear Selection", bootstyle="secondary").pack(side=LEFT, padx=2)
        ttk.Button(left_buttons, text="Fetch Versions", bootstyle="info").pack(side=LEFT, padx=2)
        
        # RIGHT PANEL
        right_frame = ttk.LabelFrame(content_frame, text="Selected Components", padding="10")
        right_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=(5, 0))
        
        self.selection_label = ttk.Label(right_frame, text="Selected: 0 components",
                                        font=('Segoe UI', 9, 'bold'), bootstyle="info")
        self.selection_label.pack(fill=X, pady=(0, 10))
        
        preview_frame = ttk.Frame(right_frame)
        preview_frame.pack(fill=BOTH, expand=True)
        
        preview_scroll = ttk.Scrollbar(preview_frame, bootstyle="primary-round")
        preview_scroll.pack(side=RIGHT, fill=Y)
        
        self.builder_preview = ttk.Treeview(
            preview_frame,
            columns=('name', 'version', 'category'),
            show='headings',
            yscrollcommand=preview_scroll.set,
            selectmode='browse',
            bootstyle="success"
        )
        
        self.builder_preview.heading('name', text='Component')
        self.builder_preview.heading('version', text='Version')
        self.builder_preview.heading('category', text='Category')
        
        self.builder_preview.column('name', width=180)
        self.builder_preview.column('version', width=80)
        self.builder_preview.column('category', width=100)
        
        preview_scroll.config(command=self.builder_preview.yview)
        self.builder_preview.pack(fill=BOTH, expand=True)
        
        # Action buttons at bottom
        action_frame = ttk.Frame(self.builder_tab, padding="10")
        action_frame.pack(fill=X, padx=10, pady=5)
        
        ttk.Label(action_frame, text="Tip: Select components from the left list, then click Build Pack",
                font=('Segoe UI', 8), bootstyle="secondary").pack(side=LEFT)
        
        button_container = ttk.Frame(action_frame)
        button_container.pack(side=RIGHT)
        
        ttk.Button(button_container, text="View Details", bootstyle="info-outline").pack(side=LEFT, padx=5)
        ttk.Button(button_container, text="Build Pack", bootstyle="success", width=15).pack(side=LEFT, padx=5)
        
    def create_editor_tab_ui(self):
        """Create Component Editor tab UI only (logic in editor.py)"""
        left_frame = ttk.LabelFrame(self.editor_tab, text="Components", padding=10)
        left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(10, 5), pady=10)
        
        # Search box
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=X, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side=LEFT, padx=(0, 5))
        self.editor_search = ttk.Entry(search_frame)
        self.editor_search.pack(side=LEFT, fill=X, expand=True)
        
        # Component listbox
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=BOTH, expand=True)
        
        list_scroll = ttk.Scrollbar(list_frame, bootstyle="primary-round")
        list_scroll.pack(side=RIGHT, fill=Y)
        
        self.editor_listbox = ttk.Treeview(
            list_frame,
            columns=('name',),
            show='tree',
            yscrollcommand=list_scroll.set,
            selectmode='browse',
            bootstyle="primary"
        )
        list_scroll.config(command=self.editor_listbox.yview)
        self.editor_listbox.pack(fill=BOTH, expand=True)
        
        # Buttons under list
        list_button_frame = ttk.Frame(left_frame)
        list_button_frame.pack(fill=X, pady=(5, 0))
        ttk.Button(list_button_frame, text="Add New", bootstyle="success").pack(side=LEFT, padx=2)
        ttk.Button(list_button_frame, text="Delete", bootstyle="danger").pack(side=LEFT, padx=2)
        
        # RIGHT PANEL
        right_frame = ttk.LabelFrame(self.editor_tab, text="Component Details", padding=10)
        right_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=(5, 10), pady=10)
        
        # Save button at bottom
        save_frame = ttk.Frame(right_frame)
        save_frame.pack(side=BOTTOM, fill=X, pady=(10, 0))
        ttk.Button(save_frame, text="Save Changes", bootstyle="primary").pack(side=RIGHT)

        # Scrollable form
        form_canvas = ttk.Canvas(right_frame, highlightthickness=0)
        form_scroll = ttk.Scrollbar(right_frame, orient=VERTICAL, command=form_canvas.yview, bootstyle="primary-round")
        self.editor_form = ttk.Frame(form_canvas, padding=(0,0,15,0))
        
        self.editor_form.bind(
            "<Configure>",
            lambda e: form_canvas.configure(scrollregion=form_canvas.bbox("all"))
        )
        
        form_canvas.create_window((0, 0), window=self.editor_form, anchor="nw")
        form_canvas.configure(yscrollcommand=form_scroll.set)
        
        form_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        form_scroll.pack(side=RIGHT, fill=Y)
        
        self.create_editor_form()
        
    def create_editor_form(self):
        """Create the component editor form fields"""
        form = self.editor_form
        
        # Basic info
        ttk.Label(form, text="Component ID:", font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, sticky=W, pady=5, padx=(0, 10))
        self.editor_id = ttk.Entry(form, width=40)
        self.editor_id.grid(row=0, column=1, sticky=EW, pady=5, padx=(0, 10))
        
        ttk.Label(form, text="Name:", font=('Segoe UI', 9, 'bold')).grid(row=1, column=0, sticky=W, pady=5, padx=(0, 10))
        self.editor_name = ttk.Entry(form, width=40)
        self.editor_name.grid(row=1, column=1, sticky=EW, pady=5, padx=(0, 10))
        
        ttk.Label(form, text="Category:", font=('Segoe UI', 9, 'bold')).grid(row=2, column=0, sticky=W, pady=5, padx=(0, 10))
        self.editor_category = ttk.Combobox(form, values=["Essential", "Homebrew Apps", "Patches", "Tesla Overlays", "Payloads"], state="readonly")
        self.editor_category.grid(row=2, column=1, sticky=EW, pady=5, padx=(0, 10))
        
        ttk.Label(form, text="Description:", font=('Segoe UI', 9, 'bold')).grid(row=3, column=0, sticky=NW, pady=5, padx=(0, 10))
        self.editor_description = ttk.Text(form, height=3, width=40, wrap='word')
        self.editor_description.grid(row=3, column=1, sticky=EW, pady=5, padx=(0, 10))
        
        # Source info
        ttk.Separator(form, orient=HORIZONTAL).grid(row=4, column=0, columnspan=2, sticky=EW, pady=10)
        ttk.Label(form, text="Source Information", font=('Segoe UI', 10, 'bold')).grid(row=5, column=0, columnspan=2, sticky=W, pady=5)
        
        ttk.Label(form, text="Source Type:", font=('Segoe UI', 9, 'bold')).grid(row=6, column=0, sticky=W, pady=5, padx=(0, 10))
        self.editor_source_type = ttk.Combobox(form, values=["github_release", "direct_url"], state="readonly")
        self.editor_source_type.grid(row=6, column=1, sticky=EW, pady=5, padx=(0, 10))

        # --- Dynamic Source Fields ---
        self.editor_repo_label = ttk.Label(form, text="[User]/[Repo]:", font=('Segoe UI', 9, 'bold'))
        self.editor_repo_label.grid(row=7, column=0, sticky=W, pady=5, padx=(0, 10))
        self.editor_repo = ttk.Entry(form, width=40)
        self.editor_repo.grid(row=7, column=1, sticky=EW, pady=5, padx=(0, 10))
        
        self.editor_pattern_label = ttk.Label(form, text="Asset Pattern:", font=('Segoe UI', 9, 'bold'))
        self.editor_pattern_label.grid(row=8, column=0, sticky=W, pady=5, padx=(0, 10))
        self.editor_pattern = ttk.Entry(form, width=40)
        self.editor_pattern.grid(row=8, column=1, sticky=EW, pady=5, padx=(0, 10))

        self.editor_url_label = ttk.Label(form, text="Direct URL:", font=('Segoe UI', 9, 'bold'))
        self.editor_url = ttk.Entry(form, width=40)

        def update_source_fields(*args):
            source_type = self.editor_source_type.get()
            if source_type == 'github_release':
                self.editor_repo_label.grid()
                self.editor_repo.grid()
                self.editor_pattern_label.grid()
                self.editor_pattern.grid()
                self.editor_url_label.grid_remove()
                self.editor_url.grid_remove()
            elif source_type == 'direct_url':
                self.editor_repo_label.grid_remove()
                self.editor_repo.grid_remove()
                self.editor_pattern_label.grid_remove()
                self.editor_pattern.grid_remove()
                self.editor_url_label.grid(row=7, column=0, sticky=W, pady=5, padx=(0, 10))
                self.editor_url.grid(row=7, column=1, sticky=EW, pady=5, padx=(0, 10))

        self.editor_source_type.bind('<<ComboboxSelected>>', update_source_fields)

        # Processing steps
        ttk.Separator(form, orient=HORIZONTAL).grid(row=9, column=0, columnspan=2, sticky=EW, pady=10)
        steps_header = ttk.Frame(form)
        steps_header.grid(row=10, column=0, columnspan=2, sticky=EW, pady=5)
        ttk.Label(steps_header, text="Processing Steps", font=('Segoe UI', 10, 'bold')).pack(side=LEFT)

        # Steps list
        self.editor_steps_list = ttk.Treeview(form, height=5, columns=('action',), show='headings', bootstyle="primary")
        self.editor_steps_list.heading('action', text='Action', anchor=CENTER)
        self.editor_steps_list.column('action', anchor=W)
        self.editor_steps_list.grid(row=11, column=0, columnspan=2, sticky=EW, pady=5, padx=(0, 10))

        # Add Step button
        add_step_frame = ttk.Frame(form)
        add_step_frame.grid(row=12, column=0, columnspan=2, pady=(5, 0), sticky=W)
        
        form.columnconfigure(1, weight=1)
    
    def create_manager_tab_ui(self):
        """Create Manager tab UI only (logic in manager.py)"""
        # SD Card selection
        sd_frame = ttk.LabelFrame(self.manager_tab, text="SD Card Location", padding="10")
        sd_frame.pack(fill=X, padx=10, pady=5)

        ttk.Entry(sd_frame, textvariable=self.sd_path, width=45).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(sd_frame, text="Browse...", bootstyle="primary").pack(side=LEFT, padx=5)

        # Download Official Pack Section
        download_frame = ttk.LabelFrame(self.manager_tab, text="Download Official HATS Pack", padding="10")
        download_frame.pack(fill=X, padx=10, pady=(10, 5))

        # Top row: Release info
        info_row = ttk.Frame(download_frame)
        info_row.pack(fill=X, pady=(0, 10))

        ttk.Label(info_row, text="Latest Release:", font=('Segoe UI', 9, 'bold')).pack(side=LEFT, padx=(0, 5))
        self.latest_release_label = ttk.Label(info_row, text="Checking...", font=('Segoe UI', 9))
        self.latest_release_label.pack(side=LEFT, padx=(0, 10))

        ttk.Button(info_row, text="Refresh", bootstyle="info-outline", width=10).pack(side=LEFT, padx=5)
        ttk.Button(info_row, text="View on GitHub", bootstyle="secondary-outline", width=15).pack(side=LEFT, padx=5)

        # Bottom row: Download button and progress
        download_row = ttk.Frame(download_frame)
        download_row.pack(fill=X)

        self.download_btn = ttk.Button(download_row, text="Download Latest", bootstyle="success", width=20)
        self.download_btn.pack(side=LEFT, padx=5)

        # Progress bar (hidden by default)
        self.download_progress_frame = ttk.Frame(download_row)
        self.download_progress_frame.pack(side=LEFT, fill=X, expand=True, padx=10)

        self.download_progress = ttk.Progressbar(self.download_progress_frame, mode='determinate', bootstyle="success-striped")
        self.download_progress.pack(fill=X, side=TOP)

        self.download_status_label = ttk.Label(self.download_progress_frame, text="", font=('Segoe UI', 8))
        self.download_status_label.pack(side=TOP, anchor=W)

        # Hide progress initially
        self.download_progress_frame.pack_forget()

        # Download Firmware Pack Section
        firmware_frame = ttk.LabelFrame(self.manager_tab, text="Download Firmware Pack", padding="10")
        firmware_frame.pack(fill=X, padx=10, pady=(10, 5))

        # Top row: Firmware release info
        firmware_info_row = ttk.Frame(firmware_frame)
        firmware_info_row.pack(fill=X, pady=(0, 10))

        ttk.Label(firmware_info_row, text="Latest Release:", font=('Segoe UI', 9, 'bold')).pack(side=LEFT, padx=(0, 5))
        self.latest_firmware_label = ttk.Label(firmware_info_row, text="Checking...", font=('Segoe UI', 9))
        self.latest_firmware_label.pack(side=LEFT, padx=(0, 10))

        ttk.Button(firmware_info_row, text="Refresh", bootstyle="info-outline", width=10).pack(side=LEFT, padx=5)
        ttk.Button(firmware_info_row, text="View on GitHub", bootstyle="secondary-outline", width=15).pack(side=LEFT, padx=5)

        # Bottom row: Download button and progress
        firmware_download_row = ttk.Frame(firmware_frame)
        firmware_download_row.pack(fill=X)

        self.firmware_download_btn = ttk.Button(firmware_download_row, text="Download Latest", bootstyle="success", width=20)
        self.firmware_download_btn.pack(side=LEFT, padx=5)

        # Progress bar (hidden by default)
        self.firmware_progress_frame = ttk.Frame(firmware_download_row)
        self.firmware_progress_frame.pack(side=LEFT, fill=X, expand=True, padx=10)

        self.firmware_progress = ttk.Progressbar(self.firmware_progress_frame, mode='determinate', bootstyle="success-striped")
        self.firmware_progress.pack(fill=X, side=TOP)

        self.firmware_status_label = ttk.Label(self.firmware_progress_frame, text="", font=('Segoe UI', 8))
        self.firmware_status_label.pack(side=TOP, anchor=W)

        # Hide progress initially
        self.firmware_progress_frame.pack_forget()

        # Pack Installer
        installer_frame = ttk.LabelFrame(self.manager_tab, text="Pack Installer", padding="10")
        installer_frame.pack(fill=X, padx=10, pady=(10, 5))

        self.pack_path = ttk.StringVar()
        pack_entry = ttk.Entry(installer_frame, textvariable=self.pack_path, state="readonly")
        pack_entry.pack(side=LEFT, padx=5, fill=X, expand=True)

        ttk.Button(installer_frame, text="Select Pack (.zip)...", bootstyle="info").pack(side=LEFT, padx=5)
        self.install_btn = ttk.Button(installer_frame, text="Install to SD Card", state=DISABLED)
        self.install_btn.pack(side=LEFT, padx=5)
        
        # View selector
        view_frame = ttk.Frame(self.manager_tab, padding="5")
        view_frame.pack(fill=X, padx=10)
        
        self.manager_installed_btn = ttk.Button(view_frame, text="Installed Components", bootstyle="primary")
        self.manager_installed_btn.pack(side=LEFT, padx=5)
        
        self.manager_trash_btn = ttk.Button(view_frame, text="Trash Bin", bootstyle="secondary")
        self.manager_trash_btn.pack(side=LEFT, padx=5)
        
        self.manager_trash_info = ttk.Label(view_frame, text="", font=('Segoe UI', 8))
        self.manager_trash_info.pack(side=LEFT, padx=10)
        
        # Components frame
        self.manager_components_frame = ttk.LabelFrame(self.manager_tab, text="Installed Components", padding="10")
        self.manager_components_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # Treeview
        tree_container = ttk.Frame(self.manager_components_frame)
        tree_container.pack(fill=BOTH, expand=True)
        
        tree_scroll = ttk.Scrollbar(tree_container, bootstyle="secondary-round")
        tree_scroll.pack(side=RIGHT, fill=Y)
        
        self.manager_tree = ttk.Treeview(
            tree_container,
            columns=('Name', 'Version', 'Category', 'Files'),
            show='headings',
            yscrollcommand=tree_scroll.set,
            selectmode='extended',
            bootstyle="primary"
        )
        tree_scroll.config(command=self.manager_tree.yview)
        
        self.manager_tree.heading('Name', text='Component Name')
        self.manager_tree.heading('Version', text='Version')
        self.manager_tree.heading('Category', text='Category')
        self.manager_tree.heading('Files', text='Files')
        
        self.manager_tree.column('Name', width=250)
        self.manager_tree.column('Version', width=100)
        self.manager_tree.column('Category', width=150)
        self.manager_tree.column('Files', width=80, anchor=CENTER)
        
        self.manager_tree.pack(fill=BOTH, expand=True)
        
        # Action buttons
        action_frame = ttk.Frame(self.manager_tab, padding="10")
        action_frame.pack(fill=X, padx=10, pady=5)
        
        self.manager_selection_label = ttk.Label(action_frame, text="Selected: 0 components (0 files)",
                                                 font=('Segoe UI', 9, 'bold'))
        self.manager_selection_label.pack(side=LEFT)
        
        button_container = ttk.Frame(action_frame)
        button_container.pack(side=RIGHT)
        
        self.manager_remove_btn = ttk.Button(button_container, text="Move to Trash",
                                             state=DISABLED, bootstyle="danger")
        self.manager_remove_btn.pack(side=LEFT, padx=5)

        ttk.Button(button_container, text="Select All", bootstyle="secondary").pack(side=LEFT, padx=5)
        ttk.Button(button_container, text="Clear Selection", bootstyle="secondary").pack(side=LEFT, padx=5)
    
    # ===== HELPER METHODS =====
    
    def center_window(self, window):
        """Center a popup window on the main window"""
        # This function is now a wrapper to call the actual centering logic
        # after a small delay, preventing the "flicker" effect.
        window.after(10, lambda: self._do_center(window))

    def _do_center(self, window):
        window.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_w = self.root.winfo_width()
        parent_h = self.root.winfo_height()
        
        window_w = window.winfo_width()
        window_h = window.winfo_height()
        
        x = parent_x + (parent_w // 2) - (window_w // 2)
        y = parent_y + (parent_h // 2) - (window_h // 2)
        
        window.geometry(f"+{x}+{y}")

    def show_custom_info(self, title, message, parent=None, blocking=True, width=400, height=200):
        """Show a custom centered info dialog"""
        parent_window = parent if parent else self.root
        dialog = ttk.Toplevel(parent_window)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.transient(parent_window)
        dialog.grab_set()

        info_frame = ttk.Frame(dialog, padding=20)
        info_frame.pack(fill=BOTH, expand=True)
            
        ttk.Label(info_frame, text=message, wraplength=350, justify=CENTER).pack(pady=20)

        ttk.Button(info_frame, text="OK", command=dialog.destroy, bootstyle="primary").pack()

        dialog.update_idletasks()
        self._do_center(dialog) # Center immediately without flicker

        # Force window to front and gain focus (essential for popups from background threads)
        dialog.lift()
        dialog.attributes('-topmost', True)
        dialog.after(100, lambda: dialog.attributes('-topmost', False))
        dialog.focus_force()

        # Re-center after lifting to ensure proper positioning
        dialog.after(10, lambda: self._do_center(dialog))

        if blocking:
            self.root.wait_window(dialog)

    def show_custom_confirm(self, title, message, yes_text="Yes", no_text="No", style="primary", width=450, height=250):
        """Show a custom centered confirmation dialog that returns True or False."""
        dialog = ttk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.transient(self.root)
        dialog.grab_set()

        result = [False] # Use a list to allow modification from inner function

        def on_yes():
            result[0] = True
            dialog.destroy()

        def on_no():
            result[0] = False
            dialog.destroy()

        info_frame = ttk.Frame(dialog, padding=20)
        info_frame.pack(fill=BOTH, expand=True)
        ttk.Label(info_frame, text=message, wraplength=400, justify=CENTER).pack(pady=20)

        button_frame = ttk.Frame(info_frame)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text=yes_text, command=on_yes, bootstyle=style).pack(side=LEFT, padx=10)
        ttk.Button(button_frame, text=no_text, command=on_no, bootstyle="secondary").pack(side=LEFT, padx=10)

        self.center_window(dialog)
        self.root.wait_window(dialog)
        return result[0]

    def show_pat_settings(self):
        """Show GitHub PAT settings dialog"""
        pat_dialog = ttk.Toplevel(self.root)
        pat_dialog.title("GitHub Personal Access Token")
        pat_dialog.geometry("500x350")
        pat_dialog.transient(self.root)
        pat_dialog.grab_set()
        
        info_frame = ttk.Frame(pat_dialog, padding=20)
        info_frame.pack(fill=BOTH, expand=True)
        
        ttk.Label(info_frame, text="GitHub Personal Access Token",
                  font=('Segoe UI', 11, 'bold')).pack(pady=(0, 10))
        
        ttk.Label(info_frame, text="Enter your GitHub PAT to increase API rate limits.\n"
                                   "This is optional but recommended for building packs.",
                  wraplength=450).pack(pady=(0, 15))
        
        ttk.Label(info_frame, text="Token:").pack(anchor=W)
        pat_entry = ttk.Entry(info_frame, textvariable=self.github_pat, show="*", width=50)
        pat_entry.pack(fill=X, pady=5)
        
        save_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(info_frame, text="Save token to config file",
                        variable=save_var, bootstyle="primary-round-toggle").pack(pady=10)
        
        button_frame = ttk.Frame(info_frame)
        button_frame.pack(pady=(15, 0))
        
        def save_pat():
            token = self.github_pat.get()
            should_save = save_var.get()

            if should_save:
                self.config_data['github_pat'] = token
                self.save_config()
                self.show_custom_info("Saved", "GitHub PAT saved to config.", parent=pat_dialog)
            else: # If unchecked, remove it from config
                self.config_data.pop('github_pat', None)
                self.save_config()
            pat_dialog.destroy() # Destroy the PAT dialog first

        ttk.Button(button_frame, text="Save", command=save_pat,
                   bootstyle="primary").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=pat_dialog.destroy,
                   bootstyle="secondary").pack(side=LEFT, padx=5)
        
        pat_dialog.update_idletasks()
        self.center_window(pat_dialog)

    def show_download_settings(self):
        """Show download settings dialog"""
        download_dialog = ttk.Toplevel(self.root)
        download_dialog.title("Download Settings")
        download_dialog.geometry("550x550")
        download_dialog.transient(self.root)
        download_dialog.grab_set()

        info_frame = ttk.Frame(download_dialog, padding=20)
        info_frame.pack(fill=BOTH, expand=True)

        ttk.Label(info_frame, text="Download Settings",
                  font=('Segoe UI', 11, 'bold')).pack(pady=(0, 10))

        ttk.Label(info_frame, text="Configure how official HATS packs are downloaded from GitHub.",
                  wraplength=500).pack(pady=(0, 20))

        # Chunk size setting
        chunk_frame = ttk.LabelFrame(info_frame, text="Download Chunk Size", padding=15)
        chunk_frame.pack(fill=X, pady=(0, 15))

        ttk.Label(chunk_frame, text="Larger chunks = faster downloads but less frequent progress updates.\n"
                                   "Smaller chunks = more frequent updates but slightly slower.",
                  wraplength=480, font=('Segoe UI', 8)).pack(pady=(0, 10))

        # Chunk size options
        chunk_size_var = ttk.IntVar(value=self.config_data.get('download_chunk_size', 2097152))

        options_frame = ttk.Frame(chunk_frame)
        options_frame.pack(fill=X)

        ttk.Radiobutton(options_frame, text="512 KB (Slower, more updates)",
                        variable=chunk_size_var, value=524288,
                        bootstyle="primary").pack(anchor=W, pady=2)

        ttk.Radiobutton(options_frame, text="1 MB (Balanced)",
                        variable=chunk_size_var, value=1048576,
                        bootstyle="primary").pack(anchor=W, pady=2)

        ttk.Radiobutton(options_frame, text="2 MB (Recommended)",
                        variable=chunk_size_var, value=2097152,
                        bootstyle="primary").pack(anchor=W, pady=2)

        ttk.Radiobutton(options_frame, text="5 MB (Faster, fewer updates)",
                        variable=chunk_size_var, value=5242880,
                        bootstyle="primary").pack(anchor=W, pady=2)

        # Current size display
        current_size = self.config_data.get('download_chunk_size', 2097152)
        current_mb = current_size / (1024 * 1024)
        current_label = ttk.Label(info_frame, text=f"Current: {current_mb:.1f} MB",
                                  font=('Segoe UI', 9, 'bold'), bootstyle="info")
        current_label.pack(pady=(5, 20))

        # Buttons
        button_frame = ttk.Frame(info_frame)
        button_frame.pack(pady=(15, 0))

        def save_download_settings():
            new_chunk_size = chunk_size_var.get()
            self.config_data['download_chunk_size'] = new_chunk_size
            self.save_config()

            new_mb = new_chunk_size / (1024 * 1024)
            self.show_custom_info("Saved",
                                  f"Download chunk size set to {new_mb:.1f} MB\n\nThis will take effect on the next download.",
                                  parent=download_dialog, height=250)
            download_dialog.destroy()

        ttk.Button(button_frame, text="Save", command=save_download_settings,
                   bootstyle="primary").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=download_dialog.destroy,
                   bootstyle="secondary").pack(side=LEFT, padx=5)

        download_dialog.update_idletasks()
        self.center_window(download_dialog)


def main():
    root = ttk.Window(themename="darkly")
    app = HATSKitProGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()