"""
editor.py - Component Editor Module
Handles all Component Editor tab logic and functionality
HATSKit Pro v2.0.1
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import json
import urllib.request
import urllib.error
import urllib.parse
import threading
import datetime
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from tkinter import filedialog


class ComponentEditor:
    """Handles Component Editor functionality"""
    
    def __init__(self, main_gui):
        """Initialize with reference to main GUI"""
        self.gui = main_gui
        self.current_selection = None
        self.temp_asset_configs = {}  # Temporary storage for asset configs being edited
        self.selected_asset_item = None  # Track which asset pattern is selected for step editing

        # Connect event handlers
        self.connect_events()
    
    def connect_events(self):
        """Connect event handlers to UI elements"""
        # Listbox selection
        self.gui.editor_listbox.bind('<<TreeviewSelect>>', self.on_editor_selection_change)
        self.gui.editor_listbox.bind('<Button-1>', self.on_editor_list_click)

        # Asset pattern selection
        self.gui.editor_assets_list.bind('<<TreeviewSelect>>', self.on_asset_selection_change)

        # Search
        self.gui.editor_search.bind('<KeyRelease>', self.filter_editor_list)

        # Connect buttons
        self._connect_editor_buttons()
    
    def _connect_editor_buttons(self):
        """Find and connect editor tab buttons"""
        def find_buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    text = child.cget('text')
                    if text == "Add New":
                        child.config(command=self.add_new_component)
                    elif text == "Delete":
                        child.config(command=self.delete_component)
                    elif text == "Edit Skeleton":
                        child.config(command=self.open_skeleton_editor)
                    elif text == "Edit Extras":
                        child.config(command=self.open_component_extras_editor)
                    elif text == "Scan Repo":
                        child.config(command=self.autofill_from_github_repo)
                    elif text == "Save Changes":
                        child.config(command=self.save_changes)
                    elif text == "Load Preset":
                        child.config(command=self.load_editor_preset)
                    elif text == "Save Preset":
                        child.config(command=self.save_editor_preset)
                    elif text == "Delete Preset":
                        child.config(command=self.delete_editor_preset)
                find_buttons(child)
        
        find_buttons(self.gui.editor_tab)

        # Find the assets button frame and add buttons vertically
        def find_btn_frame(parent, depth=0, max_depth=3):
            if depth > max_depth:
                return None
            for child in parent.winfo_children():
                if isinstance(child, ttk.Frame):
                    # Check if this looks like a button frame (empty or has only buttons)
                    children = child.winfo_children()
                    if len(children) == 0:  # Empty frame - this is our button frame
                        return child
                    result = find_btn_frame(child, depth + 1, max_depth)
                    if result:
                        return result
            return None

        assets_btn_frame = find_btn_frame(self.gui.editor_assets_frame)
        if assets_btn_frame:
            ttk.Button(assets_btn_frame, text="+ Add", bootstyle="success-outline", command=self.add_asset_pattern, width=10).pack(pady=2)
            ttk.Button(assets_btn_frame, text="Edit", bootstyle="info-outline", command=self.edit_asset_pattern, width=10).pack(pady=2)
            ttk.Button(assets_btn_frame, text="Remove", bootstyle="danger-outline", command=self.remove_asset_pattern, width=10).pack(pady=2)

        # Connect step management buttons
        steps_frame = self.gui.editor_form.grid_slaves(row=12, column=0)[0]
        for widget in steps_frame.winfo_children():
            if isinstance(widget, ttk.Button):
                text = widget.cget('text')
                if text == "Add Step":
                    widget.config(command=self.add_step)
                elif text == "Edit Step":
                    widget.config(command=self.edit_step)
                elif text == "Remove Step":
                    widget.config(command=self.remove_step)

    # ==================== Skeleton ZIP Editor ====================

    def open_skeleton_editor(self):
        """Open a lightweight editor for assets/skeleton.zip contents."""
        skeleton_path = Path("assets") / "skeleton.zip"
        if not skeleton_path.exists():
            self.gui.show_custom_info(
                "Skeleton Not Found",
                f"Could not find:\n{skeleton_path}\n\nCreate or restore the skeleton ZIP first.",
                width=500,
                height=240
            )
            return

        dialog = ttk.Toplevel(self.gui.root)
        dialog.title("Skeleton Editor")
        dialog.geometry("850x560")
        dialog.transient(self.gui.root)
        dialog.grab_set()

        root_frame = ttk.Frame(dialog, padding=12)
        root_frame.pack(fill=BOTH, expand=True)

        header_frame = ttk.Frame(root_frame)
        header_frame.pack(fill=X, pady=(0, 8))
        ttk.Label(
            header_frame,
            text="assets/skeleton.zip",
            font=('Segoe UI', 10, 'bold')
        ).pack(side=LEFT)
        skeleton_status = ttk.Label(header_frame, text="", bootstyle="secondary")
        skeleton_status.pack(side=LEFT, padx=(10, 0))

        body_frame = ttk.Frame(root_frame)
        body_frame.pack(fill=BOTH, expand=True)

        list_frame = ttk.Frame(body_frame)
        list_frame.pack(side=LEFT, fill=BOTH, expand=True)

        tree_scroll = ttk.Scrollbar(list_frame, orient=VERTICAL, bootstyle="primary-round")
        tree_scroll.pack(side=RIGHT, fill=Y)

        skeleton_tree = ttk.Treeview(
            list_frame,
            columns=('type', 'size'),
            show='tree headings',
            yscrollcommand=tree_scroll.set,
            selectmode='browse',
            bootstyle="primary"
        )
        skeleton_tree.heading('#0', text='Path', anchor=W)
        skeleton_tree.heading('type', text='Type', anchor=CENTER)
        skeleton_tree.heading('size', text='Size', anchor=E)
        skeleton_tree.column('#0', width=500, minwidth=260)
        skeleton_tree.column('type', width=90, minwidth=70, anchor=CENTER, stretch=False)
        skeleton_tree.column('size', width=90, minwidth=70, anchor=E, stretch=False)
        skeleton_tree.pack(side=LEFT, fill=BOTH, expand=True)
        tree_scroll.config(command=skeleton_tree.yview)

        button_frame = ttk.Frame(body_frame)
        button_frame.pack(side=RIGHT, fill=Y, padx=(8, 0))

        text_extensions = {
            '.ini', '.txt', '.config', '.cfg', '.json', '.xml', '.md', '.lst',
            '.conf', '.properties', '.log'
        }

        def classify(path):
            suffix = Path(path).suffix.lower()
            if suffix in text_extensions:
                return "text"
            return "file"

        def format_size(size):
            if size < 1024:
                return f"{size} B"
            if size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            return f"{size / (1024 * 1024):.1f} MB"

        def selected_path():
            selected = skeleton_tree.selection()
            if not selected:
                return None
            return skeleton_tree.item(selected[0], 'text')

        def load_entries():
            for item in skeleton_tree.get_children():
                skeleton_tree.delete(item)

            try:
                with zipfile.ZipFile(skeleton_path, 'r') as zip_ref:
                    infos = [
                        info for info in zip_ref.infolist()
                        if not info.is_dir()
                    ]
            except Exception as e:
                self.gui.show_custom_info(
                    "Skeleton Error",
                    f"Failed to read skeleton ZIP:\n{e}",
                    parent=dialog,
                    width=500,
                    height=220
                )
                return

            for info in sorted(infos, key=lambda item: item.filename.lower()):
                path = info.filename.replace('\\', '/')
                skeleton_tree.insert(
                    '',
                    END,
                    text=path,
                    values=(classify(path), format_size(info.file_size))
                )
            skeleton_status.config(text=f"{len(infos)} files")

        def rewrite_skeleton(updates=None, deletes=None):
            updates = updates or {}
            deletes = set(deletes or [])

            temp_dir = Path(tempfile.mkdtemp(prefix="hats_skeleton_"))
            temp_zip = temp_dir / "skeleton.zip"
            try:
                with zipfile.ZipFile(skeleton_path, 'r') as src_zip, \
                        zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as dst_zip:
                    for info in src_zip.infolist():
                        normalized_name = info.filename.replace('\\', '/')
                        if normalized_name in deletes or normalized_name in updates:
                            continue
                        dst_zip.writestr(info, src_zip.read(info.filename))

                    for arcname, payload in updates.items():
                        normalized_name = arcname.replace('\\', '/').lstrip('/')
                        if isinstance(payload, bytes):
                            dst_zip.writestr(normalized_name, payload)
                        else:
                            dst_zip.write(payload, normalized_name)

                shutil.move(str(temp_zip), str(skeleton_path))
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

            load_entries()

        def edit_text_file():
            path = selected_path()
            if not path:
                self.gui.show_custom_info("No Selection", "Please select a skeleton file to edit.", parent=dialog)
                return

            if classify(path) != "text":
                self.gui.show_custom_info(
                    "Binary File",
                    "This file type is treated as binary/resource data.\nUse Replace File instead.",
                    parent=dialog,
                    width=450,
                    height=220
                )
                return

            try:
                with zipfile.ZipFile(skeleton_path, 'r') as zip_ref:
                    raw = zip_ref.read(path)
                content = raw.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    content = raw.decode('utf-8-sig')
                except Exception:
                    self.gui.show_custom_info(
                        "Encoding Error",
                        "Could not decode this file as UTF-8 text.",
                        parent=dialog,
                        width=450,
                        height=200
                    )
                    return
            except Exception as e:
                self.gui.show_custom_info("Read Error", f"Failed to read file:\n{e}", parent=dialog)
                return

            editor = ttk.Toplevel(dialog)
            editor.title(f"Edit {path}")
            editor.geometry("820x620")
            editor.transient(dialog)
            editor.grab_set()

            editor_frame = ttk.Frame(editor, padding=10)
            editor_frame.pack(fill=BOTH, expand=True)

            ttk.Label(editor_frame, text=path, font=('Segoe UI', 9, 'bold')).pack(anchor=W, pady=(0, 6))

            text_frame = ttk.Frame(editor_frame)
            text_frame.pack(fill=BOTH, expand=True)
            text_scroll = ttk.Scrollbar(text_frame, orient=VERTICAL, bootstyle="primary-round")
            text_scroll.pack(side=RIGHT, fill=Y)
            text_widget = ttk.Text(text_frame, wrap='none', undo=True, yscrollcommand=text_scroll.set)
            text_widget.pack(side=LEFT, fill=BOTH, expand=True)
            text_scroll.config(command=text_widget.yview)
            text_widget.insert('1.0', content)

            buttons = ttk.Frame(editor_frame)
            buttons.pack(fill=X, pady=(10, 0))

            def save_text():
                new_content = text_widget.get('1.0', END)
                if new_content.endswith('\n'):
                    # Tk Text always appends a final newline. Keep one, not two.
                    new_content = new_content[:-1]
                rewrite_skeleton(updates={path: new_content.encode('utf-8')})
                editor.destroy()
                self.gui.show_custom_info("Saved", f"Updated:\n{path}", parent=dialog, width=450, height=180)

            ttk.Button(buttons, text="Save Text", bootstyle="success", command=save_text).pack(side=RIGHT, padx=4)
            ttk.Button(buttons, text="Cancel", bootstyle="secondary", command=editor.destroy).pack(side=RIGHT, padx=4)
            self.gui.center_window(editor)

        def prompt_target_path(title, default_value=""):
            prompt = ttk.Toplevel(dialog)
            prompt.title(title)
            prompt.geometry("560x210")
            prompt.transient(dialog)
            prompt.grab_set()

            prompt_frame = ttk.Frame(prompt, padding=18)
            prompt_frame.pack(fill=BOTH, expand=True)
            ttk.Label(prompt_frame, text="Target path inside skeleton.zip:", font=('Segoe UI', 9, 'bold')).pack(anchor=W)
            target_entry = ttk.Entry(prompt_frame)
            target_entry.pack(fill=X, pady=(6, 10))
            target_entry.insert(0, default_value.replace('\\', '/').lstrip('/'))
            target_entry.focus_set()

            result = {'path': None}

            def accept():
                target = target_entry.get().strip().replace('\\', '/').lstrip('/')
                if not target:
                    self.gui.show_custom_info("Missing Path", "Please enter a target path.", parent=prompt)
                    return
                result['path'] = target
                prompt.destroy()

            buttons = ttk.Frame(prompt_frame)
            buttons.pack(fill=X)
            ttk.Button(buttons, text="OK", bootstyle="primary", command=accept).pack(side=RIGHT, padx=4)
            ttk.Button(buttons, text="Cancel", bootstyle="secondary", command=prompt.destroy).pack(side=RIGHT, padx=4)

            prompt.bind('<Return>', lambda _event: accept())
            self.gui.center_window(prompt)
            prompt.wait_window()
            return result['path']

        def add_or_replace_file(replace=False):
            current_path = selected_path() if replace else ""
            file_path = filedialog.askopenfilename(
                title="Select file to add to skeleton",
                parent=dialog,
                filetypes=[("All files", "*.*")]
            )
            if not file_path:
                return

            default_target = current_path or Path(file_path).name
            target = prompt_target_path("Replace File" if replace else "Add File", default_target)
            if not target:
                return

            if target != current_path and self._skeleton_member_exists(skeleton_path, target):
                if not self.gui.show_custom_confirm(
                    "Overwrite Existing File",
                    f"'{target}' already exists in skeleton.zip.\n\nOverwrite it?",
                    yes_text="Overwrite",
                    style="warning",
                    width=500,
                    height=240
                ):
                    return

            rewrite_skeleton(updates={target: Path(file_path)})
            self.gui.show_custom_info("Saved", f"Added/updated:\n{target}", parent=dialog, width=450, height=180)

        def add_text_file():
            target = prompt_target_path("Add Text File", "")
            if not target:
                return
            if self._skeleton_member_exists(skeleton_path, target):
                if not self.gui.show_custom_confirm(
                    "Overwrite Existing File",
                    f"'{target}' already exists in skeleton.zip.\n\nOverwrite it?",
                    yes_text="Overwrite",
                    style="warning",
                    width=500,
                    height=240
                ):
                    return
            rewrite_skeleton(updates={target: b""})
            load_entries()
            for item in skeleton_tree.get_children():
                if skeleton_tree.item(item, 'text') == target:
                    skeleton_tree.selection_set(item)
                    skeleton_tree.focus(item)
                    skeleton_tree.see(item)
                    break

            edit_text_file()

        def delete_file():
            path = selected_path()
            if not path:
                self.gui.show_custom_info("No Selection", "Please select a skeleton file to remove.", parent=dialog)
                return
            if not self.gui.show_custom_confirm(
                "Remove Skeleton File",
                f"Remove this file from skeleton.zip?\n\n{path}",
                yes_text="Remove",
                style="danger",
                width=500,
                height=240
            ):
                return
            rewrite_skeleton(deletes=[path])

        ttk.Button(button_frame, text="Edit Text", bootstyle="primary-outline", width=16, command=edit_text_file).pack(pady=3)
        ttk.Button(button_frame, text="Add Text", bootstyle="success-outline", width=16, command=add_text_file).pack(pady=3)
        ttk.Button(button_frame, text="Add File", bootstyle="success-outline", width=16, command=lambda: add_or_replace_file(False)).pack(pady=3)
        ttk.Button(button_frame, text="Replace File", bootstyle="info-outline", width=16, command=lambda: add_or_replace_file(True)).pack(pady=3)
        ttk.Button(button_frame, text="Remove", bootstyle="danger-outline", width=16, command=delete_file).pack(pady=3)
        ttk.Button(button_frame, text="Refresh", bootstyle="secondary-outline", width=16, command=load_entries).pack(pady=(16, 3))
        ttk.Button(button_frame, text="Close", bootstyle="secondary", width=16, command=dialog.destroy).pack(side=BOTTOM, pady=3)

        skeleton_tree.bind('<Double-Button-1>', lambda _event: edit_text_file())

        load_entries()
        self.gui.center_window(dialog)

    def _skeleton_member_exists(self, skeleton_path, member_path):
        """Return True when a normalized member path exists in skeleton.zip."""
        normalized = member_path.replace('\\', '/').lstrip('/')
        try:
            with zipfile.ZipFile(skeleton_path, 'r') as zip_ref:
                return normalized in {name.replace('\\', '/') for name in zip_ref.namelist()}
        except Exception:
            return False

    def _parse_github_repo(self, repo_value):
        """Return owner/repo from a GitHub repo field or URL."""
        repo_value = repo_value.strip()
        if not repo_value:
            return None

        if repo_value.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(repo_value)
            if parsed.netloc.lower() not in ("github.com", "www.github.com"):
                return None
            parts = [part for part in parsed.path.strip('/').split('/') if part]
            if len(parts) < 2:
                return None
            owner, repo = parts[0], parts[1]
        else:
            parts = [part for part in repo_value.strip('/').split('/') if part]
            if len(parts) != 2:
                return None
            owner, repo = parts

        if repo.endswith(".git"):
            repo = repo[:-4]

        valid = re.compile(r"^[A-Za-z0-9_.-]+$")
        if not valid.match(owner) or not valid.match(repo):
            return None
        return f"{owner}/{repo}"

    def _default_component_id_from_repo(self, repo_name):
        """Build a component ID candidate from a repository name."""
        comp_id = repo_name.lower().replace('-', '_').replace('.', '_')
        comp_id = re.sub(r"[^a-z0-9_]+", "_", comp_id)
        comp_id = re.sub(r"_+", "_", comp_id).strip('_')
        return comp_id or repo_name.lower()

    def autofill_from_github_repo(self):
        """Fetch GitHub repository metadata and fill empty component fields."""
        if self.gui.editor_source_type.get() != 'github_release':
            self.gui.show_custom_info("Scan Repo", "Set Source Type to github_release first.", width=420, height=180)
            return

        repo = self._parse_github_repo(self.gui.editor_repo.get())
        if not repo:
            self.gui.show_custom_info("Invalid Repository",
                                      "Enter a GitHub repository as owner/repo or a full github.com URL.",
                                      width=460, height=190)
            return

        self.gui.editor_repo.delete(0, END)
        self.gui.editor_repo.insert(0, repo)
        threading.Thread(target=self._worker_autofill_from_github_repo, args=(repo,), daemon=True).start()

    def _worker_autofill_from_github_repo(self, repo):
        try:
            api_url = f"https://api.github.com/repos/{repo}"
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": "HATSKitPro"
            }
            token = self.gui.github_pat.get().strip() if hasattr(self.gui, 'github_pat') else ''
            if token:
                headers["Authorization"] = f"token {token}"

            request = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(request, timeout=15) as response:
                repo_data = json.loads(response.read().decode('utf-8'))

            self.gui.root.after(0, lambda: self._apply_github_repo_autofill(repo, repo_data))
        except urllib.error.HTTPError as e:
            message = f"GitHub API returned HTTP {e.code} for {repo}."
            self.gui.root.after(0, lambda: self.gui.show_custom_info("Scan Failed", message, width=460, height=190))
        except Exception as e:
            message = f"Failed to scan {repo}:\n{e}"
            self.gui.root.after(0, lambda: self.gui.show_custom_info("Scan Failed", message, width=500, height=220))

    def _apply_github_repo_autofill(self, repo, repo_data):
        repo_name = repo_data.get('name') or repo.split('/')[-1]
        full_name = repo_data.get('full_name') or repo
        display_name = repo_data.get('name') or repo_name
        description = repo_data.get('description') or ''

        if not self.gui.editor_id.get().strip():
            comp_id = self._default_component_id_from_repo(repo_name)
            if comp_id in self.gui.components_data:
                owner = full_name.split('/')[0].lower()
                comp_id = self._default_component_id_from_repo(f"{owner}_{repo_name}")
            self.gui.editor_id.insert(0, comp_id)

        if not self.gui.editor_name.get().strip():
            self.gui.editor_name.insert(0, display_name)

        current_desc = self.gui.editor_description.get('1.0', END).strip()
        if description and not current_desc:
            self.gui.editor_description.insert('1.0', description)

        self.gui.show_custom_info("Repo Scanned",
                                  f"Loaded metadata from {full_name}.\n\nEmpty Component ID, Name, and Description fields were populated.",
                                  width=500, height=220)

    # ==================== Component Extras Editor ====================

    def open_component_extras_editor(self):
        """Open the component-owned extras editor for the selected component."""
        comp_id = self.current_selection
        if not comp_id:
            self.gui.show_custom_info(
                "No Component",
                "Please save or select a component before editing extras.",
                width=450,
                height=200
            )
            return

        comp_data = self.gui.components_data.get(comp_id)
        if not comp_data:
            self.gui.show_custom_info("No Component", "Selected component was not found.", width=400)
            return

        extras_dir = Path("assets") / "component_extras" / comp_id
        extras_dir.mkdir(parents=True, exist_ok=True)

        dialog = ttk.Toplevel(self.gui.root)
        dialog.title(f"Component Extras - {comp_data.get('name', comp_id)}")
        dialog.geometry("1080x620")
        dialog.minsize(1040, 600)
        dialog.transient(self.gui.root)
        dialog.grab_set()

        root_frame = ttk.Frame(dialog, padding=12)
        root_frame.pack(fill=BOTH, expand=True)

        header = ttk.Frame(root_frame)
        header.pack(fill=X, pady=(0, 8))
        ttk.Label(header, text=comp_data.get('name', comp_id), font=('Segoe UI', 10, 'bold')).pack(side=LEFT)
        extras_status = ttk.Label(header, text="", bootstyle="secondary")
        extras_status.pack(side=LEFT, padx=(10, 0))

        body = ttk.Frame(root_frame)
        body.pack(fill=BOTH, expand=True)

        list_frame = ttk.Frame(body)
        list_frame.pack(side=LEFT, fill=BOTH, expand=True)

        scroll = ttk.Scrollbar(list_frame, orient=VERTICAL, bootstyle="primary-round")
        scroll.pack(side=RIGHT, fill=Y)

        extras_tree = ttk.Treeview(
            list_frame,
            columns=('enabled', 'type', 'target', 'source'),
            show='headings',
            yscrollcommand=scroll.set,
            selectmode='browse',
            bootstyle="primary"
        )
        extras_tree.heading('enabled', text='On', anchor=CENTER)
        extras_tree.heading('type', text='Type', anchor=CENTER)
        extras_tree.heading('target', text='Target Path', anchor=W)
        extras_tree.heading('source', text='Source', anchor=W)
        extras_tree.column('enabled', width=45, minwidth=40, anchor=CENTER, stretch=False)
        extras_tree.column('type', width=70, minwidth=60, anchor=CENTER, stretch=False)
        extras_tree.column('target', width=280, minwidth=160)
        extras_tree.column('source', width=360, minwidth=200)
        extras_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.config(command=extras_tree.yview)

        button_frame = ttk.Frame(body)
        button_frame.pack(side=RIGHT, fill=Y, padx=(12, 0))
        button_frame.configure(width=170)
        button_frame.pack_propagate(False)

        def normalize_target(target):
            target = target.strip().replace('\\', '/').lstrip('/')
            if not target or target.startswith('../') or '/..' in target or target == '..':
                return None
            return target

        def default_source_for(target):
            return extras_dir / target

        def is_text_target(path):
            return Path(path).suffix.lower() in {
                '.ini', '.txt', '.config', '.cfg', '.json', '.xml', '.md',
                '.lst', '.conf', '.properties', '.log'
            }

        def get_extras():
            return comp_data.setdefault('component_extras', [])

        def selected_index():
            selected = extras_tree.selection()
            if not selected:
                return None
            return int(selected[0])

        def refresh_list():
            for item in extras_tree.get_children():
                extras_tree.delete(item)

            extras = get_extras()
            for idx, extra in enumerate(extras):
                enabled = "[x]" if extra.get('enabled', True) else "[ ]"
                extra_type = extra.get('type', 'file')
                target = extra.get('target', '')
                source = extra.get('source', '')
                extras_tree.insert('', END, iid=str(idx), values=(enabled, extra_type, target, source))

            extras_status.config(text=f"{len(extras)} extras")
            if hasattr(self.gui, 'editor_extras_info'):
                self.gui.editor_extras_info.config(text=f"{len(extras)} extras")

        def persist():
            self.gui.components_data[comp_id] = comp_data
            self.gui.save_components_file()
            refresh_list()

        def prompt_target(title, default_value="", label="Target path inside pack:", allow_empty=False):
            prompt = ttk.Toplevel(dialog)
            prompt.title(title)
            prompt.geometry("560x210")
            prompt.transient(dialog)
            prompt.grab_set()

            frame = ttk.Frame(prompt, padding=18)
            frame.pack(fill=BOTH, expand=True)
            ttk.Label(frame, text=label, font=('Segoe UI', 9, 'bold')).pack(anchor=W)
            entry = ttk.Entry(frame)
            entry.pack(fill=X, pady=(6, 10))
            entry.insert(0, default_value)
            entry.focus_set()

            if label.startswith("Target folder"):
                ttk.Label(
                    frame,
                    text="The selected file name will be kept automatically.",
                    font=('Segoe UI', 8),
                    foreground='gray'
                ).pack(anchor=W, pady=(0, 8))

            result = {'target': None}

            def accept():
                raw_target = entry.get().strip()
                if allow_empty and raw_target in ("", "/", "\\"):
                    result['target'] = ""
                    prompt.destroy()
                    return

                target = normalize_target(raw_target)
                if not target:
                    self.gui.show_custom_info("Invalid Target", "Enter a relative pack path.", parent=prompt)
                    return
                result['target'] = target
                prompt.destroy()

            buttons = ttk.Frame(frame)
            buttons.pack(fill=X)
            ttk.Button(buttons, text="OK", bootstyle="primary", command=accept).pack(side=RIGHT, padx=4)
            ttk.Button(buttons, text="Cancel", bootstyle="secondary", command=prompt.destroy).pack(side=RIGHT, padx=4)
            prompt.bind('<Return>', lambda _event: accept())
            self.gui.center_window(prompt)
            prompt.wait_window()
            return result['target']

        def prompt_target_folder(title, default_value=""):
            target = prompt_target(title, default_value, label="Target folder inside pack:", allow_empty=True)
            if target is None:
                return None
            if target == "":
                return ""
            return target.rstrip('/') + '/'

        def edit_target_path():
            idx = selected_index()
            if idx is None:
                self.gui.show_custom_info("No Selection", "Please select an extra to edit.", parent=dialog)
                return

            extras = get_extras()
            extra = extras[idx]
            old_target = extra.get('target', '')
            new_target = prompt_target("Edit Target Path", old_target)
            if new_target is None or new_target == old_target:
                return

            source_path = Path(extra.get('source')) if extra.get('source') else default_source_for(old_target)
            new_source_path = default_source_for(new_target)
            moved_source = False

            try:
                source_path.resolve().relative_to(extras_dir.resolve())
                source_is_component_owned = True
            except ValueError:
                source_is_component_owned = False

            if source_is_component_owned and source_path.exists() and not new_source_path.exists():
                new_source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_path), str(new_source_path))
                moved_source = True

            extra['target'] = new_target
            extra['type'] = "text" if is_text_target(new_target) else "file"
            if moved_source:
                extra['source'] = str(new_source_path).replace('\\', '/')

            persist()

            if source_is_component_owned and source_path.exists() and new_source_path.exists():
                self.gui.show_custom_info(
                    "Target Path Updated",
                    "The target path was updated, but the source file was not moved because a file already exists at the new component extras path.",
                    parent=dialog,
                    width=560,
                    height=220
                )

        def edit_text_extra(existing_index):
            extras = get_extras()
            extra = extras[existing_index]
            target = extra.get('target', '')
            if not target:
                return

            source_path = Path(extra.get('source')) if extra.get('source') else default_source_for(target)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            content = ""
            if source_path.exists():
                try:
                    content = source_path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    self.gui.show_custom_info(
                        "Encoding Error",
                        "This text extra is not valid UTF-8.",
                        parent=dialog,
                        width=450,
                        height=200
                    )
                    return

            editor = ttk.Toplevel(dialog)
            editor.title(f"Edit Text Extra - {target}")
            editor.geometry("820x620")
            editor.transient(dialog)
            editor.grab_set()

            frame = ttk.Frame(editor, padding=10)
            frame.pack(fill=BOTH, expand=True)
            ttk.Label(frame, text=target, font=('Segoe UI', 9, 'bold')).pack(anchor=W, pady=(0, 6))

            text_frame = ttk.Frame(frame)
            text_frame.pack(fill=BOTH, expand=True)
            text_scroll = ttk.Scrollbar(text_frame, orient=VERTICAL, bootstyle="primary-round")
            text_scroll.pack(side=RIGHT, fill=Y)
            text_widget = ttk.Text(text_frame, wrap='none', undo=True, yscrollcommand=text_scroll.set)
            text_widget.pack(side=LEFT, fill=BOTH, expand=True)
            text_scroll.config(command=text_widget.yview)
            text_widget.insert('1.0', content)

            buttons = ttk.Frame(frame)
            buttons.pack(fill=X, pady=(10, 0))

            def save_text():
                new_content = text_widget.get('1.0', END)
                if new_content.endswith('\n'):
                    new_content = new_content[:-1]
                source_path.write_text(new_content, encoding='utf-8')

                new_extra = {
                    "type": "text",
                    "target": target,
                    "source": str(source_path).replace('\\', '/'),
                    "enabled": extra.get('enabled', True),
                    "overwrite": extra.get('overwrite', True)
                }
                extras[existing_index] = new_extra
                persist()
                editor.destroy()

            ttk.Button(buttons, text="Save Text", bootstyle="success", command=save_text).pack(side=RIGHT, padx=4)
            ttk.Button(buttons, text="Cancel", bootstyle="secondary", command=editor.destroy).pack(side=RIGHT, padx=4)
            self.gui.center_window(editor)

        def add_file_extra(existing_index=None):
            extras = get_extras()
            extra = extras[existing_index] if existing_index is not None else None
            picked = filedialog.askopenfilename(
                title="Select extra file",
                parent=dialog,
                filetypes=[("All files", "*.*")]
            )
            if not picked:
                return

            picked_name = Path(picked).name
            default_folder = ""
            if extra and extra.get('target'):
                target_path = Path(extra.get('target').replace('\\', '/'))
                default_folder = str(target_path.parent).replace('\\', '/')
                if default_folder == ".":
                    default_folder = ""
            target_folder = prompt_target_folder("Replace File Extra" if extra else "Add File Extra", default_folder)
            if target_folder is None:
                return
            target = f"{target_folder}{picked_name}"

            dest = default_source_for(target)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(picked, dest)

            new_extra = {
                "type": "text" if is_text_target(target) else "file",
                "target": target,
                "source": str(dest).replace('\\', '/'),
                "enabled": extra.get('enabled', True) if extra else True,
                "overwrite": extra.get('overwrite', True) if extra else True
            }
            if existing_index is None:
                extras.append(new_extra)
            else:
                extras[existing_index] = new_extra
            persist()

        def scan_extras_folder():
            extras = get_extras()
            existing_by_target = {
                extra.get('target'): extra
                for extra in extras
                if extra.get('target')
            }

            files = sorted(path for path in extras_dir.rglob('*') if path.is_file())
            if not files:
                self.gui.show_custom_info(
                    "No Files Found",
                    f"No files found in:\n{extras_dir}",
                    parent=dialog,
                    width=500,
                    height=220
                )
                return

            added = 0
            updated = 0
            for path in files:
                target = str(path.relative_to(extras_dir)).replace('\\', '/')
                source = str(path).replace('\\', '/')
                extra_type = "text" if is_text_target(target) else "file"

                if target in existing_by_target:
                    existing_by_target[target].update({
                        "type": extra_type,
                        "source": source
                    })
                    updated += 1
                else:
                    extras.append({
                        "type": extra_type,
                        "target": target,
                        "source": source,
                        "enabled": True,
                        "overwrite": True
                    })
                    added += 1

            persist()
            self.gui.show_custom_info(
                "Scan Complete",
                f"Scanned:\n{extras_dir}\n\nAdded: {added}\nUpdated: {updated}",
                parent=dialog,
                width=520,
                height=260
            )

        def edit_selected():
            idx = selected_index()
            if idx is None:
                self.gui.show_custom_info("No Selection", "Please select an extra to edit.", parent=dialog)
                return
            extra = get_extras()[idx]
            if extra.get('type') == 'text':
                edit_text_extra(idx)
            else:
                add_file_extra(idx)

        def toggle_selected():
            idx = selected_index()
            if idx is None:
                self.gui.show_custom_info("No Selection", "Please select an extra to toggle.", parent=dialog)
                return
            extras = get_extras()
            extras[idx]['enabled'] = not extras[idx].get('enabled', True)
            persist()

        def remove_selected():
            idx = selected_index()
            if idx is None:
                self.gui.show_custom_info("No Selection", "Please select an extra to remove.", parent=dialog)
                return
            extra = get_extras()[idx]
            if not self.gui.show_custom_confirm(
                "Remove Extra",
                f"Remove this component extra?\n\n{extra.get('target', '')}",
                yes_text="Remove",
                style="danger",
                width=500,
                height=240
            ):
                return
            del get_extras()[idx]
            persist()

        ttk.Button(button_frame, text="Add File", bootstyle="success-outline", command=lambda: add_file_extra()).pack(fill=X, pady=3)
        ttk.Button(button_frame, text="Scan Folder", bootstyle="primary", command=scan_extras_folder).pack(fill=X, pady=3)
        ttk.Button(button_frame, text="Edit", bootstyle="info-outline", command=edit_selected).pack(fill=X, pady=3)
        ttk.Button(button_frame, text="Edit Target Path", bootstyle="info-outline", command=edit_target_path).pack(fill=X, pady=3)
        ttk.Button(button_frame, text="Enable/Disable", bootstyle="warning-outline", command=toggle_selected).pack(fill=X, pady=3)
        ttk.Button(button_frame, text="Remove", bootstyle="danger-outline", command=remove_selected).pack(fill=X, pady=3)
        ttk.Button(button_frame, text="Close", bootstyle="secondary", command=dialog.destroy).pack(side=BOTTOM, fill=X, pady=3)

        extras_tree.bind('<Double-Button-1>', lambda _event: edit_selected())
        refresh_list()
        self.gui.center_window(dialog)
    
    def populate_editor_list(self):
        """Populate editor component list"""
        for item in self.gui.editor_listbox.get_children():
            self.gui.editor_listbox.delete(item)
        
        self.filter_editor_list()

    def filter_editor_list(self, event=None):
        """Filter the editor list based on the search term."""
        search_term = self.gui.editor_search.get().lower()
        
        # Remember selection
        selected_id = self.current_selection

        # Clear list
        for item in self.gui.editor_listbox.get_children():
            self.gui.editor_listbox.delete(item)

        # Re-populate with filtered items
        for comp_id, comp_data in sorted(self.gui.components_data.items(), key=lambda x: x[1]['name']):
            name = comp_data.get('name', comp_id).lower()
            if search_term and search_term not in name:
                continue
            
            checked = "[x]" if comp_id in self.gui.editor_preset_components else "[ ]"
            display_name = comp_data.get('name', comp_id)
            if comp_data.get('component_extras'):
                display_name = f"{display_name}  [extras]"
            self.gui.editor_listbox.insert('', END, iid=comp_id,
                                           values=(checked, display_name))

        # Re-apply selection
        if selected_id and self.gui.editor_listbox.exists(selected_id):
            self.gui.editor_listbox.selection_set(selected_id)
            self.gui.editor_listbox.focus(selected_id)
            self.gui.editor_listbox.see(selected_id)

    def on_editor_selection_change(self, event):
        """Load selected component data into editor form"""
        selected = self.gui.editor_listbox.selection()
        if not selected:
            self.current_selection = None
            self.clear_form()
            return
        
        comp_id = selected[0]
        if comp_id == self.current_selection:
            return # Avoid reloading if selection hasn't changed

        self.current_selection = comp_id
        self.load_component_to_form(comp_id)

    def on_editor_list_click(self, event):
        """Toggle preset inclusion when clicking the checkbox column."""
        region = self.gui.editor_listbox.identify_region(event.x, event.y)
        column = self.gui.editor_listbox.identify_column(event.x)
        item = self.gui.editor_listbox.identify_row(event.y)

        if region != "cell" or column != "#1" or not item:
            return

        if item in self.gui.editor_preset_components:
            self.gui.editor_preset_components.remove(item)
        else:
            self.gui.editor_preset_components.add(item)

        values = list(self.gui.editor_listbox.item(item, 'values'))
        if values:
            values[0] = "[x]" if item in self.gui.editor_preset_components else "[ ]"
            self.gui.editor_listbox.item(item, values=values)

        return "break"

    def load_editor_preset(self):
        """Load a named preset into the editor checkbox column."""
        preset_name = self.gui.editor_preset_dropdown.get().strip()
        if not preset_name:
            self.gui.show_custom_info("No Preset", "Please select a preset to load.")
            return

        preset = self.gui.presets_data.get(preset_name)
        if not preset:
            self.gui.show_custom_info("Preset Not Found", f"Preset '{preset_name}' was not found.")
            return

        self.gui.current_editor_preset = preset_name
        self.gui.editor_preset_components = set(preset.get('components', []))
        self.gui.editor_preset_name.delete(0, END)
        self.gui.editor_preset_name.insert(0, preset_name)
        self.filter_editor_list()

    def save_editor_preset(self):
        """Save checked components as a named preset."""
        preset_name = self.gui.editor_preset_name.get().strip()
        if not preset_name:
            preset_name = self.gui.editor_preset_dropdown.get().strip()

        if not preset_name:
            self.gui.show_custom_info("Preset Name Required", "Please enter a preset name.")
            return

        selected_components = sorted([
            comp_id for comp_id in self.gui.editor_preset_components
            if comp_id in self.gui.components_data
        ])
        if not selected_components:
            self.gui.show_custom_info("No Components", "Please check at least one component for this preset.")
            return

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        existing = self.gui.presets_data.get(preset_name, {})
        self.gui.presets_data[preset_name] = {
            "components": selected_components,
            "manual_versions": existing.get("manual_versions", {}),
            "created_at": existing.get("created_at", now),
            "updated_at": now
        }
        self.gui.save_presets_file()
        self.gui.current_editor_preset = preset_name
        self.gui.refresh_preset_controls()
        self.gui.editor_preset_dropdown.set(preset_name)
        if hasattr(self.gui, 'builder_preset_dropdown'):
            self.gui.builder_preset_dropdown.set(preset_name)
        self.gui.show_custom_info("Preset Saved", f"Preset '{preset_name}' saved with {len(selected_components)} components.")

    def delete_editor_preset(self):
        """Delete a named preset from presets.json."""
        preset_name = self.gui.editor_preset_dropdown.get().strip()
        if not preset_name:
            self.gui.show_custom_info("No Preset", "Please select a preset to delete.")
            return

        if preset_name not in self.gui.presets_data:
            self.gui.show_custom_info("Preset Not Found", f"Preset '{preset_name}' was not found.")
            return

        if not self.gui.show_custom_confirm("Delete Preset",
                                            f"Delete preset '{preset_name}'?",
                                            yes_text="Delete",
                                            style="danger"):
            return

        del self.gui.presets_data[preset_name]
        self.gui.save_presets_file()
        self.gui.refresh_preset_controls()
        self.gui.editor_preset_dropdown.set('')
        self.gui.editor_preset_name.delete(0, END)
        if hasattr(self.gui, 'builder_preset_dropdown') and self.gui.builder_preset_dropdown.get() == preset_name:
            self.gui.builder_preset_dropdown.set('')

        if self.gui.current_editor_preset == preset_name:
            self.gui.current_editor_preset = None
            self.gui.editor_preset_components = set(self.gui.components_data.keys())
            self.filter_editor_list()

        self.gui.show_custom_info("Preset Deleted", f"Preset '{preset_name}' has been deleted.")

    def load_component_to_form(self, comp_id):
        """Load a component's data into the editor form."""
        self.clear_form()
        comp_data = self.gui.components_data.get(comp_id, {})

        # Populate form fields
        self.gui.editor_id.config(state=NORMAL)
        self.gui.editor_id.delete(0, END)
        self.gui.editor_id.insert(0, comp_id)
        self.gui.editor_id.config(state=DISABLED) # ID is not editable once loaded

        self.gui.editor_name.delete(0, END)
        self.gui.editor_name.insert(0, comp_data.get('name', ''))

        self.gui.editor_category.set(comp_data.get('category', ''))

        if hasattr(self.gui, 'editor_extras_info'):
            extras_count = len(comp_data.get('component_extras', []))
            self.gui.editor_extras_info.config(text=f"{extras_count} extras")

        # Enhanced description handling - supports both dict and string formats
        self.gui.editor_description.delete('1.0', END)
        desc_obj = comp_data.get('description', comp_data.get('descriptions', ''))
        if isinstance(desc_obj, dict):
            # Handle nested dict structures like {'descriptions': {'en': 'text'}} or {'en': 'text'}
            if 'descriptions' in desc_obj and isinstance(desc_obj['descriptions'], dict):
                desc = desc_obj['descriptions'].get('en', json.dumps(desc_obj, indent=2))
            else:
                desc = desc_obj.get('en', json.dumps(desc_obj, indent=2))
        else:
            desc = str(desc_obj) if desc_obj else ''
        self.gui.editor_description.insert('1.0', desc)

        # Set source type and trigger dynamic field visibility
        source_type = comp_data.get('source_type', 'github_release')
        self.gui.editor_source_type.set(source_type)

        # Trigger the event to show the correct fields
        self.gui.editor_source_type.event_generate('<<ComboboxSelected>>')

        # Populate source fields based on type
        if source_type == 'direct_url':
            self.gui.editor_url.delete(0, END)
            self.gui.editor_url.insert(0, comp_data.get('repo', ''))

            # Load processing steps for direct_url
            self.gui.editor_steps_info.config(text="(direct URL)")
            steps = comp_data.get('processing_steps', [])
            for step in steps:
                action = step.get('action', 'N/A')
                details = ', '.join([f"{k}='{v}'" for k, v in step.items() if k != 'action'])
                display = f"{action}: {details}" if details else action
                self.gui.editor_steps_list.insert('', END, values=(display,))
        else:  # github_release
            self.gui.editor_repo.delete(0, END)
            self.gui.editor_repo.insert(0, comp_data.get('repo', ''))

            # Check if multi-asset or single asset
            if 'asset_patterns' in comp_data:
                # Multi-asset format - populate assets list and temp storage
                self.temp_asset_configs.clear()
                for asset_config in comp_data['asset_patterns']:
                    pattern = asset_config.get('pattern', '')
                    item_id = self.gui.editor_assets_list.insert('', END, values=(pattern,))
                    self.temp_asset_configs[item_id] = asset_config
            else:
                # Single asset format - for backward compatibility
                # Need to show the legacy pattern field and hide the multi-asset UI
                self.gui.editor_assets_label.grid_remove()
                self.gui.editor_assets_frame.grid_remove()
                self.gui.editor_pattern_label.grid(row=8, column=0, sticky='w', pady=5, padx=(0, 10))
                self.gui.editor_pattern.grid(row=8, column=1, sticky='ew', pady=5, padx=(0, 10))

                self.gui.editor_pattern.delete(0, END)
                self.gui.editor_pattern.insert(0, comp_data.get('asset_pattern', ''))

                # Load legacy processing steps
                self.gui.editor_steps_info.config(text="(legacy single-asset format)")
                steps = comp_data.get('processing_steps', [])
                for step in steps:
                    action = step.get('action', 'N/A')
                    details = ', '.join([f"{k}='{v}'" for k, v in step.items() if k != 'action'])
                    display = f"{action}: {details}" if details else action
                    self.gui.editor_steps_list.insert('', END, values=(display,))

    def on_asset_selection_change(self, event):
        """Handle asset pattern selection and load its processing steps"""
        selected = self.gui.editor_assets_list.selection()
        if not selected:
            self.selected_asset_item = None
            self.clear_steps_list()
            self.gui.editor_steps_info.config(text="(no asset selected)")
            return

        item_id = selected[0]
        self.selected_asset_item = item_id

        # Get the asset config from temp storage
        if item_id in self.temp_asset_configs:
            asset_config = self.temp_asset_configs[item_id]
            pattern = asset_config.get('pattern', 'Unknown')
            self.gui.editor_steps_info.config(text=f"{pattern}")

            # Load processing steps
            self.clear_steps_list()
            steps = asset_config.get('processing_steps', [])
            for step in steps:
                action = step.get('action', 'N/A')
                details = ', '.join([f"{k}='{v}'" for k, v in step.items() if k != 'action'])
                display = f"{action}: {details}" if details else action
                self.gui.editor_steps_list.insert('', END, values=(display,))

    def clear_steps_list(self):
        """Clear the processing steps list"""
        for item in self.gui.editor_steps_list.get_children():
            self.gui.editor_steps_list.delete(item)

    def clear_form(self):
        """Clear all fields in the editor form."""
        self.gui.editor_id.config(state=NORMAL)
        self.gui.editor_id.delete(0, END)
        self.gui.editor_name.delete(0, END)
        self.gui.editor_category.set('')
        self.gui.editor_description.delete('1.0', END)
        self.gui.editor_source_type.set('')
        self.gui.editor_repo.delete(0, END)
        self.gui.editor_pattern.delete(0, END)
        self.gui.editor_url.delete(0, END)
        for item in self.gui.editor_assets_list.get_children():
            self.gui.editor_assets_list.delete(item)
        self.temp_asset_configs.clear()
        self.selected_asset_item = None
        self.clear_steps_list()
        self.gui.editor_steps_info.config(text="(no asset selected)")
        if hasattr(self.gui, 'editor_extras_info'):
            self.gui.editor_extras_info.config(text="0 extras")

    def add_new_component(self):
        """Add new component with proper initialization"""
        # Check if there are unsaved changes
        if self.current_selection:
            if not self.gui.show_custom_confirm("Unsaved Changes",
                                                "You may have unsaved changes. Continue to add new component?",
                                                yes_text="Continue"):
                return

        self.current_selection = None
        if self.gui.editor_listbox.selection():
            self.gui.editor_listbox.selection_remove(self.gui.editor_listbox.selection())

        self.clear_form()
        self.gui.editor_id.config(state=NORMAL)

        # Set default values for new component
        self.gui.editor_source_type.set('github_release')
        self.gui.editor_source_type.event_generate('<<ComboboxSelected>>')

        self.gui.editor_id.focus_set()
        self.gui.show_custom_info("Add New Component",
                                 "Form cleared. Enter a unique Component ID and fill in the details, then click 'Save Changes'.",
                                 width=450)
    
    def delete_component(self):
        """Delete selected component"""
        if not self.current_selection:
            self.gui.show_custom_info("No Selection", "Please select a component to delete.")
            return
        
        comp_name = self.gui.components_data[self.current_selection].get('name', self.current_selection)
        if not self.gui.show_custom_confirm("Confirm Delete", f"Are you sure you want to permanently delete '{comp_name}'?",
                                            yes_text="Delete", style="danger"):
            return

        # Delete from data
        del self.gui.components_data[self.current_selection]
        
        # Save to file
        self.gui.save_components_file()

        # Refresh UI
        self.current_selection = None
        self.clear_form()
        self.gui.reload_components(show_info=False) # Reload all lists
        self.gui.show_custom_info("Deleted", f"'{comp_name}' has been deleted.")
    
    def save_changes(self):
        """Save component changes with enhanced validation"""
        comp_id_entry = self.gui.editor_id
        comp_id_entry.config(state=NORMAL)
        comp_id = comp_id_entry.get().strip()
        is_new_component = self.current_selection is None

        # Validation: Component ID
        if not comp_id:
            self.gui.show_custom_info("Validation Error", "Component ID cannot be empty.")
            comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
            return

        # Validation: Component ID format (no spaces, alphanumeric with underscores/hyphens)
        if not comp_id.replace('_', '').replace('-', '').isalnum():
            self.gui.show_custom_info("Validation Error",
                                     "Component ID must contain only letters, numbers, underscores, and hyphens.",
                                     width=450)
            comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
            return

        # If it's a new component, check if ID already exists
        if is_new_component and comp_id in self.gui.components_data:
            self.gui.show_custom_info("Validation Error",
                                     f"Component ID '{comp_id}' already exists. Please choose a unique ID.",
                                     width=450)
            return

        # Validation: Component name
        comp_name = self.gui.editor_name.get().strip()
        if not comp_name:
            self.gui.show_custom_info("Validation Error", "Component name cannot be empty.")
            comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
            return

        # Validation: Category
        category = self.gui.editor_category.get()
        if not category:
            self.gui.show_custom_info("Validation Error", "Please select a category.")
            comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
            return

        source_type = self.gui.editor_source_type.get()

        # Validation: Source type
        if not source_type:
            self.gui.show_custom_info("Validation Error", "Please select a source type.")
            comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
            return

        # Validation: Source-specific fields
        if source_type == 'direct_url':
            url = self.gui.editor_url.get().strip()
            if not url:
                self.gui.show_custom_info("Validation Error", "Direct URL cannot be empty.")
                comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
                return
            repo_value = url
            asset_pattern = "not_applicable"

            # Extract version from URL (e.g., .../658/DBI.nro -> "658")
            import re
            version_match = re.search(r'/(\d+(?:\.\d+)*)/[^/]+$', url)
            if version_match:
                extracted_version = version_match.group(1)
            else:
                extracted_version = "N/A"
        else:  # github_release
            repo = self._parse_github_repo(self.gui.editor_repo.get())
            if not repo:
                self.gui.show_custom_info("Validation Error",
                                          "Repository must be owner/repo or a full GitHub repository URL.",
                                          width=460)
                comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
                return
            self.gui.editor_repo.delete(0, END)
            self.gui.editor_repo.insert(0, repo)

            # Check if using multi-asset or single-asset format
            asset_list_items = self.gui.editor_assets_list.get_children()

            if asset_list_items:
                # Multi-asset format - must have at least one asset
                repo_value = repo
                asset_pattern = None  # Not used in multi-asset format
                extracted_version = None
            else:
                # Single-asset format (backward compatibility)
                pattern = self.gui.editor_pattern.get().strip()
                if not pattern:
                    self.gui.show_custom_info("Missing Asset Pattern",
                                             "Please add at least one asset pattern.\n\n"
                                             "Click '+ Add' in the Asset Patterns section to add patterns with their processing steps.\n\n"
                                             "This new format allows each asset to have its own processing steps for better flexibility.",
                                             height=320)
                    comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
                    return
                repo_value = repo
                asset_pattern = pattern
                extracted_version = None  # Will be fetched later

        # Collect data from form
        # Preserve existing asset_info or create new one
        existing_component_data = self.gui.components_data.get(self.current_selection or comp_id, {})
        existing_asset_info = existing_component_data.get('asset_info', {})

        # Update version in asset_info if extracted from direct URL
        if extracted_version:
            existing_asset_info['version'] = extracted_version

        new_data = {
            "name": comp_name,
            "category": category,
            "description": self.gui.editor_description.get('1.0', END).strip(),
            "source_type": source_type,
            "repo": repo_value,
            "asset_info": existing_asset_info
        }
        if existing_component_data.get('component_extras'):
            new_data['component_extras'] = existing_component_data.get('component_extras', [])

        # Handle asset patterns (multi-asset vs single-asset)
        if source_type == 'github_release':
            asset_list_items = self.gui.editor_assets_list.get_children()

            if asset_list_items:
                # Multi-asset format
                asset_patterns = []

                # Get asset configs from temp storage
                for item_id in asset_list_items:
                    if item_id in self.temp_asset_configs:
                        asset_patterns.append(self.temp_asset_configs[item_id])
                    else:
                        # Fallback: try to get from existing component data
                        pattern = self.gui.editor_assets_list.item(item_id, 'values')[0]
                        comp_data = self.gui.components_data.get(self.current_selection or comp_id, {})
                        existing_asset_patterns = comp_data.get('asset_patterns', [])

                        asset_config = None
                        for existing_asset in existing_asset_patterns:
                            if existing_asset.get('pattern') == pattern:
                                asset_config = existing_asset
                                break

                        if asset_config:
                            asset_patterns.append(asset_config)
                        else:
                            # Default config if not found
                            asset_patterns.append({
                                'pattern': pattern,
                                'processing_steps': []
                            })

                new_data['asset_patterns'] = asset_patterns
            else:
                # Single-asset format (backward compatibility)
                # This format is deprecated but still supported for existing components
                new_data['asset_pattern'] = asset_pattern
                # Read processing_steps from the UI (user may have edited them)
                processing_steps = []
                for item_id in self.gui.editor_steps_list.get_children():
                    step_str = self.gui.editor_steps_list.item(item_id, 'values')[0]
                    processing_steps.append(self._parse_step_string(step_str))
                new_data['processing_steps'] = processing_steps
        else:
            # direct_url source type - read processing_steps from UI
            new_data['asset_pattern'] = asset_pattern
            processing_steps = []
            for item_id in self.gui.editor_steps_list.get_children():
                step_str = self.gui.editor_steps_list.item(item_id, 'values')[0]
                processing_steps.append(self._parse_step_string(step_str))
            new_data['processing_steps'] = processing_steps

        # If we are renaming a component (ID changed), we need to remove the old one
        if not is_new_component and comp_id != self.current_selection:
            if not self.gui.show_custom_confirm("Confirm ID Change",
                                                f"Changing the component ID from '{self.current_selection}' to '{comp_id}'.\n\n"
                                                "This will create a new component entry. Continue?",
                                                yes_text="Yes, Change ID"):
                comp_id_entry.config(state=DISABLED)
                return
            del self.gui.components_data[self.current_selection]

        # Update the main data dictionary
        self.gui.components_data[comp_id] = new_data

        # Save to file
        self.gui.save_components_file()

        # Refresh UI
        self.current_selection = comp_id  # Update current selection to new ID
        self.gui.reload_components(show_info=False)

        # Re-select the item
        if self.gui.editor_listbox.exists(comp_id):
            self.gui.editor_listbox.selection_set(comp_id)
            self.gui.editor_listbox.focus(comp_id)
            self.gui.editor_listbox.see(comp_id)

        comp_id_entry.config(state=DISABLED)
        self.gui.show_custom_info("Saved", f"Changes for '{new_data['name']}' have been saved to components.json.")

    def _parse_step_string(self, step_str):
        """Convert a display string back into a step dictionary with robust error handling."""
        try:
            if ':' not in step_str:
                # Handle actions with no parameters, like 'unzip_to_root'
                return {"action": step_str.strip()}

            action, params_str = step_str.split(':', 1)
            params = {}

            # Parse parameters - handle both quoted and unquoted values
            params_str = params_str.strip()
            if params_str:
                # Split by comma but respect quotes
                parts = []
                current_part = ""
                in_quotes = False

                for char in params_str:
                    if char == "'" or char == '"':
                        in_quotes = not in_quotes
                    elif char == ',' and not in_quotes:
                        if current_part:
                            parts.append(current_part.strip())
                        current_part = ""
                        continue
                    current_part += char

                if current_part:
                    parts.append(current_part.strip())

                # Parse each key=value pair
                for part in parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        # Remove surrounding quotes if present
                        value = value.strip()
                        if (value.startswith("'") and value.endswith("'")) or \
                           (value.startswith('"') and value.endswith('"')):
                            value = value[1:-1]
                        params[key.strip()] = value

            return {"action": action.strip(), **params}

        except Exception as e:
            # If parsing fails completely, return a basic action
            print(f"Warning: Failed to parse step string '{step_str}': {e}")
            return {"action": step_str.strip()}

    # ==================== Processing Steps Management ====================

    def _can_edit_processing_steps(self):
        """Check if the current state allows direct editing of processing steps"""
        # Mode 1: Asset pattern selected (multi-asset github_release)
        if self.selected_asset_item:
            return True

        # Mode 2: Legacy single-asset format
        if self.gui.editor_steps_info.cget('text') == "(legacy single-asset format)":
            return True

        # Mode 3: Direct URL source type (single file with processing steps)
        # Check both existing component data and the UI dropdown value
        source_type = self.gui.editor_source_type.get()

        # If adding new component with direct_url selected
        if source_type == 'direct_url':
            return True

        # If editing existing direct_url component
        if self.current_selection:
            comp_data = self.gui.components_data.get(self.current_selection, {})
            if comp_data.get('source_type') == 'direct_url':
                return True

        return False

    def add_step(self):
        """Add a processing step to the selected asset pattern, legacy component, or direct_url component"""
        # Check if we're in a mode that allows direct step editing
        # Modes: legacy single-asset, direct_url, or asset pattern selected
        can_edit_steps = self._can_edit_processing_steps()

        if not can_edit_steps:
            self.gui.show_custom_info("No Asset Selected",
                                     "Please select an asset pattern first to add processing steps.")
            return

        self._show_step_dialog()

    def edit_step(self):
        """Edit the selected processing step"""
        # Check if we're in a mode that allows direct step editing
        can_edit_steps = self._can_edit_processing_steps()

        if not can_edit_steps:
            self.gui.show_custom_info("No Asset Selected",
                                     "Please select an asset pattern first.")
            return

        selected = self.gui.editor_steps_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select a step to edit.")
            return

        item_id = selected[0]
        step_str = self.gui.editor_steps_list.item(item_id, 'values')[0]
        step_dict = self._parse_step_string(step_str)
        self._show_step_dialog(step_to_edit=step_dict, item_id=item_id)

    def remove_step(self):
        """Remove the selected processing step"""
        # Check if we're in a mode that allows direct step editing
        can_edit_steps = self._can_edit_processing_steps()

        if not can_edit_steps:
            self.gui.show_custom_info("No Asset Selected",
                                     "Please select an asset pattern first.")
            return

        selected = self.gui.editor_steps_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select a step to remove.")
            return

        if self.gui.show_custom_confirm("Confirm Remove",
                                        "Remove this processing step?",
                                        yes_text="Remove",
                                        style="danger"):
            item_id = selected[0]
            self.gui.editor_steps_list.delete(item_id)

            # Update the asset config in temp storage (only for multi-asset mode)
            if self.selected_asset_item:
                self._update_asset_config_steps()
            else:
                # For direct_url and legacy single-asset, no temp storage to update
                pass

    def _show_step_dialog(self, step_to_edit=None, item_id=None):
        """Show dialog to add or edit a processing step"""
        is_edit = step_to_edit is not None

        step_dialog = ttk.Toplevel(self.gui.root)
        step_dialog.title("Edit Step" if is_edit else "Add Step")
        step_dialog.geometry("500x450")
        step_dialog.resizable(False, False)
        step_dialog.transient(self.gui.root)
        step_dialog.grab_set()

        # Form
        form_frame = ttk.Frame(step_dialog, padding=15)
        form_frame.pack(fill=BOTH, expand=False, side=TOP)

        ttk.Label(form_frame, text="Action:", font=('Segoe UI', 9, 'bold')).pack(pady=(5, 2), anchor=W)
        action_var = ttk.StringVar()
        action_combo = ttk.Combobox(form_frame, textvariable=action_var, width=40, state='readonly')
        action_combo['values'] = ['unzip_to_root', 'unzip_to_path', 'copy_file', 'copy_file_to_auto_folder', 'find_and_rename', 'delete_file', 'find_and_copy', 'unzip_subfolder_to_path']
        action_combo.pack(pady=(0, 10), fill=X)

        if step_to_edit:
            action_var.set(step_to_edit.get('action', ''))
        else:
            action_combo.current(0)

        # Dynamic fields
        fields_frame = ttk.Frame(form_frame)
        fields_frame.pack(fill=X, expand=False, pady=5)

        field_widgets = {}

        def update_fields(*args):
            """Update fields based on selected action"""
            for widget in fields_frame.winfo_children():
                widget.destroy()
            field_widgets.clear()

            action = action_var.get()

            if action == 'unzip_to_path':
                ttk.Label(fields_frame, text="Target Path:", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                path_entry = ttk.Entry(fields_frame, width=50)
                path_entry.pack(pady=5, fill=X)
                field_widgets['target_path'] = path_entry
                if step_to_edit and 'target_path' in step_to_edit:
                    path_entry.insert(0, step_to_edit['target_path'])

                # Add helpful hint
                ttk.Label(fields_frame, text="Example: switch/DBI/ or atmosphere/contents/",
                         font=('Segoe UI', 8), foreground='gray').pack(pady=(0, 5), anchor=W)

            elif action == 'unzip_subfolder_to_path':
                ttk.Label(fields_frame, text="Source Subfolder:", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                subfolder_entry = ttk.Entry(fields_frame, width=50)
                subfolder_entry.pack(pady=5, fill=X)
                field_widgets['subfolder_name'] = subfolder_entry
                if step_to_edit and 'subfolder_name' in step_to_edit:
                    subfolder_entry.insert(0, step_to_edit['subfolder_name'])

                ttk.Label(fields_frame, text="Target Path (optional):", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                target_entry = ttk.Entry(fields_frame, width=50)
                target_entry.pack(pady=5, fill=X)
                field_widgets['target_path'] = target_entry
                if step_to_edit and 'target_path' in step_to_edit:
                    target_entry.insert(0, step_to_edit['target_path'])

                # Add helpful hints
                ttk.Label(fields_frame, text="Source: e.g., 'SdOut' or 'theme-patches-master/systemPatches'",
                         font=('Segoe UI', 8), foreground='gray').pack(pady=(0, 2), anchor=W)
                ttk.Label(fields_frame, text="Target: e.g., 'themes/' or leave empty for root",
                         font=('Segoe UI', 8), foreground='gray').pack(pady=(0, 5), anchor=W)

            elif action in ['copy_file', 'copy_file_to_auto_folder', 'find_and_copy', 'find_and_rename']:
                if action in ['find_and_rename', 'find_and_copy']:
                    ttk.Label(fields_frame, text="Source File Pattern:", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                    pattern_entry = ttk.Entry(fields_frame, width=50)
                    pattern_entry.pack(pady=5, fill=X)
                    field_widgets['source_file_pattern'] = pattern_entry
                    if step_to_edit and 'source_file_pattern' in step_to_edit:
                        pattern_entry.insert(0, step_to_edit['source_file_pattern'])

                ttk.Label(fields_frame, text="Target Path:", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                target_entry = ttk.Entry(fields_frame, width=50)
                target_entry.pack(pady=5, fill=X)
                field_widgets['target_path'] = target_entry
                if step_to_edit and 'target_path' in step_to_edit:
                    target_entry.insert(0, step_to_edit['target_path'])

                # Add helpful hint for copy_file_to_auto_folder
                if action == 'copy_file_to_auto_folder':
                    ttk.Label(fields_frame, text="A folder will be auto-created from the filename (without extension)",
                             font=('Segoe UI', 8), foreground='gray').pack(pady=(0, 5), anchor=W)
                    ttk.Label(fields_frame, text="Example: switch/ creates switch/FilenameWithoutExt/Filename.ext",
                             font=('Segoe UI', 8), foreground='gray').pack(pady=(0, 5), anchor=W)

                if action == 'find_and_rename':
                    ttk.Label(fields_frame, text="Target Filename:", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                    filename_entry = ttk.Entry(fields_frame, width=50)
                    filename_entry.pack(pady=5, fill=X)
                    field_widgets['target_filename'] = filename_entry
                    if step_to_edit and 'target_filename' in step_to_edit:
                        filename_entry.insert(0, step_to_edit['target_filename'])

            elif action == 'delete_file':
                ttk.Label(fields_frame, text="Path to Delete:", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                path_entry = ttk.Entry(fields_frame, width=50)
                path_entry.pack(pady=5, fill=X)
                field_widgets['path'] = path_entry
                if step_to_edit and 'path' in step_to_edit:
                    path_entry.insert(0, step_to_edit['path'])

        action_combo.bind('<<ComboboxSelected>>', update_fields)
        update_fields()

        # Buttons
        button_frame = ttk.Frame(step_dialog)
        button_frame.pack(side=BOTTOM, pady=10)

        def save_step():
            """Save the step"""
            action = action_var.get()
            if not action:
                self.gui.show_custom_info("Missing Action", "Please select an action.", parent=step_dialog)
                return

            step_dict = {'action': action}

            # Collect field values
            for key, widget in field_widgets.items():
                value = widget.get().strip()
                if value:
                    step_dict[key] = value

            # Format for display
            details = ', '.join([f"{k}='{v}'" for k, v in step_dict.items() if k != 'action'])
            display_str = f"{action}: {details}" if details else action

            # Update or add step
            if is_edit and item_id:
                self.gui.editor_steps_list.item(item_id, values=(display_str,))
            else:
                self.gui.editor_steps_list.insert('', END, values=(display_str,))

            # Update the asset config in temp storage (only for multi-asset mode)
            if self.selected_asset_item:
                self._update_asset_config_steps()

            step_dialog.destroy()

        ttk.Button(button_frame, text="Save Step", command=save_step, bootstyle="success").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=step_dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

        self.gui.center_window(step_dialog)

    def _update_asset_config_steps(self):
        """Update the asset config in temp storage with current steps from the list"""
        if not self.selected_asset_item:
            return

        # Collect steps from the UI
        steps = []
        for step_item in self.gui.editor_steps_list.get_children():
            step_str = self.gui.editor_steps_list.item(step_item, 'values')[0]
            step_dict = self._parse_step_string(step_str)
            steps.append(step_dict)

        # Update temp storage
        if self.selected_asset_item in self.temp_asset_configs:
            self.temp_asset_configs[self.selected_asset_item]['processing_steps'] = steps

    # ==================== Multi-Asset Pattern Management ====================

    def add_asset_pattern(self, asset_to_edit=None, item_id=None):
        """Add or edit an asset pattern (steps are managed in the main form)"""
        asset_dialog = ttk.Toplevel(self.gui.root)
        asset_dialog.title("Add Asset Pattern" if not asset_to_edit else "Edit Asset Pattern")
        asset_dialog.geometry("500x300")
        asset_dialog.resizable(False, False)
        asset_dialog.transient(self.gui.root)
        asset_dialog.grab_set()

        # Form
        form_frame = ttk.Frame(asset_dialog, padding=20)
        form_frame.pack(fill=BOTH, expand=True)

        # Asset pattern entry
        ttk.Label(form_frame, text="Asset Pattern:", font=('Segoe UI', 9, 'bold')).pack(pady=(5, 5), anchor=W)
        pattern_entry = ttk.Entry(form_frame, width=50)
        pattern_entry.pack(pady=(0, 10), fill=X)

        if asset_to_edit:
            pattern_entry.insert(0, asset_to_edit.get('pattern', ''))

        # Info label
        ttk.Label(form_frame, text="Note: After adding/editing, select the asset above to manage its processing steps.",
                 font=('Segoe UI', 8), foreground='gray', wraplength=450).pack(pady=(5, 15), anchor=W)

        # Save/Cancel buttons
        button_frame = ttk.Frame(asset_dialog)
        button_frame.pack(side=BOTTOM, pady=15)

        def save_asset():
            """Save the asset pattern"""
            pattern = pattern_entry.get().strip()
            if not pattern:
                self.gui.show_custom_info("Missing Pattern", "Please enter an asset pattern.", parent=asset_dialog)
                return

            # Preserve existing processing steps if editing
            processing_steps = []
            if item_id and item_id in self.temp_asset_configs:
                processing_steps = self.temp_asset_configs[item_id].get('processing_steps', [])
            elif asset_to_edit:
                processing_steps = asset_to_edit.get('processing_steps', [])

            # Create asset config
            asset_config = {
                'pattern': pattern,
                'processing_steps': processing_steps
            }

            # Update or add to the assets list
            if item_id:
                # Editing existing - update the values and temp storage
                self.gui.editor_assets_list.item(item_id, values=(pattern,))
                self.temp_asset_configs[item_id] = asset_config
            else:
                # Adding new
                new_item_id = self.gui.editor_assets_list.insert('', END, values=(pattern,))
                self.temp_asset_configs[new_item_id] = asset_config

            asset_dialog.destroy()

        ttk.Button(button_frame, text="Save", command=save_asset, bootstyle="success").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=asset_dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

        self.gui.center_window(asset_dialog)

    def edit_asset_pattern(self):
        """Edit the selected asset pattern"""
        selected = self.gui.editor_assets_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select an asset to edit.")
            return

        item_id = selected[0]
        pattern = self.gui.editor_assets_list.item(item_id, 'values')[0]

        # Retrieve the full asset config from current component data
        comp_id = self.current_selection
        if comp_id:
            comp_data = self.gui.components_data.get(comp_id, {})
            asset_patterns = comp_data.get('asset_patterns', [])

            # Find the matching asset config
            asset_to_edit = None
            for asset_config in asset_patterns:
                if asset_config.get('pattern') == pattern:
                    asset_to_edit = asset_config
                    break

            if asset_to_edit:
                self.add_asset_pattern(asset_to_edit=asset_to_edit, item_id=item_id)
            else:
                # Create a minimal config if not found
                self.add_asset_pattern(asset_to_edit={'pattern': pattern, 'processing_steps': []}, item_id=item_id)

    def remove_asset_pattern(self):
        """Remove the selected asset pattern"""
        selected = self.gui.editor_assets_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select an asset to remove.")
            return

        if self.gui.show_custom_confirm("Confirm Remove", "Remove this asset pattern?", yes_text="Remove", style="danger"):
            for item in selected:
                # Clear steps if this is the currently selected asset
                if item == self.selected_asset_item:
                    self.selected_asset_item = None
                    self.clear_steps_list()
                    self.gui.editor_steps_info.config(text="(no asset selected)")

                # Remove from temp configs and list
                if item in self.temp_asset_configs:
                    del self.temp_asset_configs[item]
                self.gui.editor_assets_list.delete(item)
