"""
editor.py - Component Editor Module
Handles all Component Editor tab logic and functionality
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
import json
import urllib.request
import urllib.error
import threading


class ComponentEditor:
    """Handles Component Editor functionality"""
    
    def __init__(self, main_gui):
        """Initialize with reference to main GUI"""
        self.gui = main_gui
        self.current_selection = None
        
        # Connect event handlers
        self.connect_events()
    
    def connect_events(self):
        """Connect event handlers to UI elements"""
        # Listbox selection
        self.gui.editor_listbox.bind('<<TreeviewSelect>>', self.on_editor_selection_change)
        
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
                    elif text == "Save Changes":
                        child.config(command=self.save_changes)
                find_buttons(child)
        
        find_buttons(self.gui.editor_tab)

        # Find buttons in the steps frame
        steps_frame = self.gui.editor_form.grid_slaves(row=12, column=0)[0]
        ttk.Button(steps_frame, text="Add Step", bootstyle="success-outline", command=self.add_step).pack(side=LEFT, padx=2)
        ttk.Button(steps_frame, text="Edit Step", bootstyle="info-outline", command=self.edit_step).pack(side=LEFT, padx=2)
        ttk.Button(steps_frame, text="Remove Step", bootstyle="danger-outline", command=self.remove_step).pack(side=LEFT, padx=2)
    
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
            
            self.gui.editor_listbox.insert('', END, iid=comp_id, text=comp_data.get('name', comp_id))

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
        else:  # github_release
            self.gui.editor_repo.delete(0, END)
            self.gui.editor_repo.insert(0, comp_data.get('repo', ''))
            self.gui.editor_pattern.delete(0, END)
            self.gui.editor_pattern.insert(0, comp_data.get('asset_pattern', ''))

        # Populate processing steps
        steps = comp_data.get('processing_steps', [])
        for step in steps:
            action = step.get('action', 'N/A')
            details = ', '.join([f"{k}='{v}'" for k, v in step.items() if k != 'action'])
            display = f"{action}: {details}" if details else action
            self.gui.editor_steps_list.insert('', END, values=(display,))

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
        for item in self.gui.editor_steps_list.get_children():
            self.gui.editor_steps_list.delete(item)

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
            repo = self.gui.editor_repo.get().strip()
            pattern = self.gui.editor_pattern.get().strip()
            if not repo:
                self.gui.show_custom_info("Validation Error", "Repository cannot be empty for GitHub releases.")
                comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
                return
            if not pattern:
                self.gui.show_custom_info("Validation Error", "Asset pattern cannot be empty for GitHub releases.")
                comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
                return
            repo_value = repo
            asset_pattern = pattern
            extracted_version = None  # Will be fetched later

        # Collect data from form
        # Preserve existing asset_info or create new one
        existing_asset_info = self.gui.components_data.get(self.current_selection or comp_id, {}).get('asset_info', {})

        # Update version in asset_info if extracted from direct URL
        if extracted_version:
            existing_asset_info['version'] = extracted_version

        new_data = {
            "name": comp_name,
            "category": category,
            "description": self.gui.editor_description.get('1.0', END).strip(),
            "source_type": source_type,
            "repo": repo_value,
            "asset_pattern": asset_pattern,
            "asset_info": existing_asset_info,
            "processing_steps": []  # Will be populated below
        }

        # Rebuild processing_steps from the Treeview
        for item_id in self.gui.editor_steps_list.get_children():
            step_str = self.gui.editor_steps_list.item(item_id, 'values')[0]
            new_data['processing_steps'].append(self._parse_step_string(step_str))

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

    def add_step(self, step_to_edit=None, item_id=None):
        """Show a dialog to add or edit a processing step."""
        is_edit = step_to_edit is not None

        step_dialog = ttk.Toplevel(self.gui.root)
        step_dialog.title("Edit Step" if is_edit else "Add Step")
        # Set fixed size to show all fields consistently
        step_dialog.geometry("600x400")
        step_dialog.resizable(False, False)
        step_dialog.transient(self.gui.root)
        step_dialog.grab_set()

        # --- UI Elements ---
        form_frame = ttk.Frame(step_dialog, padding=15)
        form_frame.pack(fill=BOTH, expand=True)

        ttk.Label(form_frame, text="Action Type:", font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, sticky=W, pady=5, padx=(0, 10))
        action_var = ttk.StringVar()
        action_combo = ttk.Combobox(form_frame, textvariable=action_var, state="readonly", width=35,
                                      values=["unzip_to_root", "unzip_subfolder_to_root", "copy_file",
                                              "find_and_copy", "find_and_rename", "delete_file"])
        action_combo.grid(row=0, column=1, sticky=EW, pady=5, padx=(0, 10))

        # --- Corrected Widget Management ---
        # This dictionary will hold references to our widgets
        widget_map = {}

        def create_entry(key, label_text, row):
            """Creates a label and an entry, and stores them in the widget_map."""
            label = ttk.Label(form_frame, text=label_text)
            entry = ttk.Entry(form_frame, width=35)
            widget_map[key] = {'label': label, 'entry': entry, 'row': row}
        
        # Create all possible dynamic widgets and store them
        create_entry('subfolder_name', "Subfolder Name:", 2)
        create_entry('source_pattern', "Source Pattern/Path:", 3)
        create_entry('target_path', "Target Directory:", 4)
        create_entry('target_filename', "Target Filename:", 5)
        create_entry('delete_path', "Path & Filename to Delete:", 6)

        def update_fields(*args):
            action = action_var.get()

            # 1. Show all widgets but disable them first
            for key, widgets in widget_map.items():
                widgets['label'].grid(row=widgets['row'], column=0, sticky=W, pady=5, padx=(0, 10))
                widgets['entry'].grid(row=widgets['row'], column=1, sticky=EW, pady=5, padx=(0, 10))
                widgets['entry'].config(state=DISABLED)
                widgets['label'].config(foreground='gray')

            # 2. Enable only the widgets needed for the selected action
            required_widgets = []
            if action == "unzip_subfolder_to_root":
                required_widgets = ['subfolder_name']
            elif action == "copy_file":
                # copy_file only needs target directory (copies downloaded file directly)
                required_widgets = ['target_path']
            elif action == "find_and_copy":
                # Update label to indicate source is required for find_and_copy
                widget_map['source_pattern']['label'].config(text="Source Pattern:")
                required_widgets = ['source_pattern', 'target_path']
            elif action == "find_and_rename":
                widget_map['source_pattern']['label'].config(text="Source Pattern:")
                required_widgets = ['source_pattern', 'target_path', 'target_filename']
            elif action == "delete_file":
                required_widgets = ['delete_path']

            for key in required_widgets:
                widgets = widget_map[key]
                widgets['entry'].config(state=NORMAL)
                widgets['label'].config(foreground='')

            # Configure column weight for proper resizing
            form_frame.columnconfigure(1, weight=1)

        action_var.trace_add('write', update_fields)

        # --- Logic with enhanced validation ---
        def on_save():
            action = action_var.get()
            if not action:
                messagebox.showwarning("Invalid Input", "Please select an action type.")
                return

            params = {}
            validation_errors = []

            if action == "unzip_subfolder_to_root":
                subfolder = widget_map['subfolder_name']['entry'].get().strip()

                if not subfolder:
                    validation_errors.append("Subfolder name cannot be empty")

                params['subfolder_name'] = subfolder

            elif action == "copy_file":
                # For copy_file, just copy the downloaded file directly to target directory
                target = widget_map['target_path']['entry'].get().strip()

                if not target:
                    validation_errors.append("Target directory cannot be empty (e.g., /switch/ftpd/)")

                params['target_path'] = target

            elif action == "find_and_copy":
                # For find_and_copy, source_file_pattern is REQUIRED
                # It needs to search for files within the downloaded archive
                source = widget_map['source_pattern']['entry'].get().strip()
                target = widget_map['target_path']['entry'].get().strip()

                if not source:
                    validation_errors.append("Source pattern/path is required for find_and_copy")
                if not target:
                    validation_errors.append("Target directory cannot be empty (e.g., /switch/ftpd/)")

                params['source_file_pattern'] = source
                params['target_path'] = target

            elif action == "find_and_rename":
                source = widget_map['source_pattern']['entry'].get().strip()
                target = widget_map['target_path']['entry'].get().strip()
                filename = widget_map['target_filename']['entry'].get().strip()

                if not source:
                    validation_errors.append("Source pattern/path cannot be empty")
                if not target:
                    validation_errors.append("Target directory cannot be empty (e.g., /switch/ftpd/)")
                if not filename:
                    validation_errors.append("Target filename cannot be empty")

                params['source_file_pattern'] = source
                params['target_path'] = target
                params['target_filename'] = filename

            elif action == "delete_file":
                path = widget_map['delete_path']['entry'].get().strip()

                if not path:
                    validation_errors.append("Path to delete cannot be empty")

                params['path'] = path

            # Show validation errors if any
            if validation_errors:
                messagebox.showwarning("Validation Error", "\n".join(validation_errors))
                return

            # Build display string
            details = ', '.join([f"{k}='{v}'" for k, v in params.items()])
            display_str = f"{action}: {details}" if details else action

            # Update or insert the step
            if is_edit:
                self.gui.editor_steps_list.item(item_id, values=(display_str,))
            else:
                self.gui.editor_steps_list.insert('', END, values=(display_str,))

            step_dialog.destroy()

        # --- Populate if editing ---
        if is_edit:
            action = step_to_edit.get('action')
            action_var.set(action)
            widget_map['subfolder_name']['entry'].insert(0, step_to_edit.get('subfolder_name', ''))
            widget_map['source_pattern']['entry'].insert(0, step_to_edit.get('source_file_pattern', ''))
            widget_map['target_path']['entry'].insert(0, step_to_edit.get('target_path', ''))
            widget_map['target_filename']['entry'].insert(0, step_to_edit.get('target_filename', ''))
            widget_map['delete_path']['entry'].insert(0, step_to_edit.get('path', ''))

        update_fields()  # Set initial field visibility

        # --- Buttons ---
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=7, column=0, columnspan=2, pady=(20, 5))
        ttk.Button(button_frame, text="Save" if is_edit else "Add", command=on_save, bootstyle="success").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=step_dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

        # Center the popup
        self.gui.center_window(step_dialog)

    def edit_step(self):
        """Edit the selected processing step."""
        selected = self.gui.editor_steps_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select a step to edit.")
            return
        item_id = selected[0]
        step_str = self.gui.editor_steps_list.item(item_id, 'values')[0]
        step_dict = self._parse_step_string(step_str)
        self.add_step(step_to_edit=step_dict, item_id=item_id)

    def remove_step(self):
        """Remove the selected processing step."""
        selected = self.gui.editor_steps_list.selection()
        if not selected:
            self.gui.show_custom_info("No Selection", "Please select a step to remove.")
            return

        if self.gui.show_custom_confirm("Confirm Remove", "Are you sure you want to remove the selected step?",
                                        yes_text="Remove", style="danger"):
            for item_id in selected:
                self.gui.editor_steps_list.delete(item_id)