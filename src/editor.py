"""
editor.py - Component Editor Module
Handles all Component Editor tab logic and functionality
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
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
        self.temp_asset_configs = {}  # Temporary storage for asset configs being edited
        self.selected_asset_item = None  # Track which asset pattern is selected for step editing

        # Connect event handlers
        self.connect_events()
    
    def connect_events(self):
        """Connect event handlers to UI elements"""
        # Listbox selection
        self.gui.editor_listbox.bind('<<TreeviewSelect>>', self.on_editor_selection_change)

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
                    elif text == "Save Changes":
                        child.config(command=self.save_changes)
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
            if not repo:
                self.gui.show_custom_info("Validation Error", "Repository cannot be empty for GitHub releases.")
                comp_id_entry.config(state=DISABLED if not is_new_component else NORMAL)
                return

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
            "asset_info": existing_asset_info
        }

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

    def add_step(self):
        """Add a processing step to the selected asset pattern or legacy component"""
        # Check if we're in legacy mode (no selected asset but component is loaded)
        is_legacy = (not self.selected_asset_item and
                     self.current_selection and
                     self.gui.editor_steps_info.cget('text') == "(legacy single-asset format)")

        if not self.selected_asset_item and not is_legacy:
            self.gui.show_custom_info("No Asset Selected",
                                     "Please select an asset pattern first to add processing steps.")
            return

        self._show_step_dialog()

    def edit_step(self):
        """Edit the selected processing step"""
        # Check if we're in legacy mode
        is_legacy = (not self.selected_asset_item and
                     self.current_selection and
                     self.gui.editor_steps_info.cget('text') == "(legacy single-asset format)")

        if not self.selected_asset_item and not is_legacy:
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
        # Check if we're in legacy mode
        is_legacy = (not self.selected_asset_item and
                     self.current_selection and
                     self.gui.editor_steps_info.cget('text') == "(legacy single-asset format)")

        if not self.selected_asset_item and not is_legacy:
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

    def _show_step_dialog(self, step_to_edit=None, item_id=None):
        """Show dialog to add or edit a processing step"""
        is_edit = step_to_edit is not None

        step_dialog = ttk.Toplevel(self.gui.root)
        step_dialog.title("Edit Step" if is_edit else "Add Step")
        step_dialog.geometry("500x350")
        step_dialog.resizable(False, False)
        step_dialog.transient(self.gui.root)
        step_dialog.grab_set()

        # Form
        form_frame = ttk.Frame(step_dialog, padding=15)
        form_frame.pack(fill=BOTH, expand=True)

        ttk.Label(form_frame, text="Action:", font=('Segoe UI', 9, 'bold')).pack(pady=(5, 2), anchor=W)
        action_var = ttk.StringVar()
        action_combo = ttk.Combobox(form_frame, textvariable=action_var, width=40, state='readonly')
        action_combo['values'] = ['unzip_to_root', 'copy_file', 'find_and_rename', 'delete_file', 'find_and_copy', 'unzip_subfolder_to_root']
        action_combo.pack(pady=(0, 10), fill=X)

        if step_to_edit:
            action_var.set(step_to_edit.get('action', ''))
        else:
            action_combo.current(0)

        # Dynamic fields
        fields_frame = ttk.Frame(form_frame)
        fields_frame.pack(fill=BOTH, expand=True, pady=5)

        field_widgets = {}

        def update_fields(*args):
            """Update fields based on selected action"""
            for widget in fields_frame.winfo_children():
                widget.destroy()
            field_widgets.clear()

            action = action_var.get()

            if action == 'unzip_subfolder_to_root':
                ttk.Label(fields_frame, text="Subfolder Name:", font=('Segoe UI', 9)).pack(pady=5, anchor=W)
                subfolder_entry = ttk.Entry(fields_frame, width=50)
                subfolder_entry.pack(pady=5, fill=X)
                field_widgets['subfolder_name'] = subfolder_entry
                if step_to_edit and 'subfolder_name' in step_to_edit:
                    subfolder_entry.insert(0, step_to_edit['subfolder_name'])

            elif action in ['copy_file', 'find_and_copy', 'find_and_rename']:
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
        button_frame.pack(pady=10)

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