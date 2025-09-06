from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, 
    QCheckBox, QFileDialog, QMessageBox, QDialogButtonBox, QGridLayout, QWidget,
    QGroupBox, QButtonGroup, QRadioButton, QFrame, QScrollArea, QListWidget, QListWidgetItem,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsSimpleTextItem
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QColor, QPalette, QPainter, QFont
from taco_geo_processor.core import config
from taco_geo_processor.utils import utils
from taco_geo_processor.processing import data_processing as dp
import os
import subprocess
import logging
import sys
from pathlib import Path
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

DXF_COLOR_MODES = ["By Entity"]
DEFAULT_DXF_COLOR_MODE = "By Entity"

class SettingsDialogBase(QDialog):
    def __init__(self, parent, current_settings, title):
        super().__init__(parent)
        self.setWindowTitle(title); self.setModal(True)
        self._settings = current_settings; self._result_settings = None
        self.main_layout = QVBoxLayout(self)
        self.setLayout(self.main_layout)
        self.widgets = {}
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Create a container widget for centering the content
        centering_container = QWidget()
        centering_layout = QHBoxLayout(centering_container)
        centering_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_widget = QWidget()
        self.content_layout = QGridLayout(self.scroll_widget)
        
        # Add the main content widget to the centering layout with stretches
        centering_layout.addStretch()
        centering_layout.addWidget(self.scroll_widget)
        centering_layout.addStretch()
        
        self.main_layout.addWidget(self.scroll_area)
        self.scroll_area.setWidget(centering_container)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.try_accept)
        self.button_box.rejected.connect(self.reject)
        
        self.create_widgets()
        self.add_custom_buttons() # Allow subclasses to add more buttons
        
        self.main_layout.addWidget(self.button_box)
        
        self.load_initial_values()
        self.adjustSize()
        
        self.resize(600, 500)
        self.setMinimumSize(400, 300)

    def create_widgets(self): raise NotImplementedError
    def add_custom_buttons(self): pass # Can be overridden by subclasses
    def load_initial_values(self): raise NotImplementedError
    def validate_and_get_values(self): raise NotImplementedError

    def try_accept(self):
        try:
            validated_settings = self.validate_and_get_values()
            if validated_settings is not None:
                self._result_settings = validated_settings
                # Update the original settings dictionary in-place
                self._settings.clear()
                self._settings.update(validated_settings)
                super().accept()
        except ValueError as ve:
            QMessageBox.warning(self, config.UI_CFG['kml_preview_validation_error_title'], str(ve))
        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error", f"Error validating settings:\n{e}")

    def get_validated_settings(self):
        return self._result_settings

    def _add_label_entry(self, layout, row, label_text, setting_key, placeholder_text="", colspan=1):
        label = QLabel(label_text)
        entry = QLineEdit()
        entry.setObjectName(setting_key)
        if placeholder_text:
            entry.setPlaceholderText(placeholder_text)
        
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(entry, row, 1, 1, colspan)
        
        self.widgets[setting_key] = entry
        return entry

    def _add_label_combobox(self, layout, row, label_text, setting_key, options, current_val_data=None, colspan=1):
        label = QLabel(label_text)
        combo = QComboBox()
        
        for i, option in enumerate(options):
            if isinstance(option, tuple):
                display_text, data_value = option
                combo.addItem(display_text, data_value)
            else:
                combo.addItem(option)
        
        if current_val_data is not None:
            # Find by data first, then by text
            index_to_set = combo.findData(current_val_data)
            if index_to_set == -1:
                index_to_set = combo.findText(str(current_val_data))
            if index_to_set != -1:
                combo.setCurrentIndex(index_to_set)

        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(combo, row, 1, 1, colspan)
        
        self.widgets[setting_key] = combo
        return combo

    def _add_grid_checkbutton(self, layout, row, col, text, setting_key, columnspan=1):
        checkbox = QCheckBox(text)
        layout.addWidget(checkbox, row, col, 1, columnspan)
        self.widgets[setting_key] = checkbox
        return checkbox

    def _add_hbox_checkbutton(self, layout, text, setting_key):
        checkbox = QCheckBox(text)
        layout.addWidget(checkbox)
        self.widgets[setting_key] = checkbox
        return checkbox
    def _add_color_button(self, layout, row, label_text, setting_key, color_type='aci', default_color_val='#ff0000'):
        label = QLabel(label_text)
        entry = QLineEdit(str(default_color_val))
        entry.setObjectName(setting_key)
        
        if color_type == 'kml':
            entry.setFixedWidth(90)
            entry.setToolTip("Color in AABBGGRR format (Alpha-Blue-Green-Red)")
        elif color_type == 'aci':
            entry.setFixedWidth(90)
            entry.setToolTip("Color in AABBGGRR format (Alpha-Blue-Green-Red)")
        elif color_type == 'aci':
            entry.setFixedWidth(90)
            entry.setToolTip("You can enter an ACI number or a hex color like #ff0000")

        preview_btn = QPushButton()
        preview_btn.setFixedSize(35, 25)
        preview_btn.setToolTip("Preview color")
        preview_btn.setStyleSheet("QPushButton { border: 2px solid #666; border-radius: 3px; }")
        
        picker_btn = QPushButton("Choose")
        picker_btn.setToolTip("Choose a new color")
        
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft)
        
        color_widget_hbox = QHBoxLayout()
        color_widget_hbox.setContentsMargins(0, 0, 0, 0)
        color_widget_hbox.setSpacing(5)
        color_widget_hbox.addWidget(entry)
        color_widget_hbox.addWidget(preview_btn)
        color_widget_hbox.addWidget(picker_btn)
        color_widget_hbox.addStretch()

        layout.addLayout(color_widget_hbox, row, 1, 1, -1)

        self.widgets[setting_key] = entry
        self.widgets[f"{setting_key}_preview"] = preview_btn
        self.widgets[f"{setting_key}_button"] = picker_btn
        
        # Pass color_type to the picker, and use a different handler for KML
        picker_btn.clicked.connect(lambda: self._pick_color(entry, color_type))

        if color_type == 'kml':
            # For KML, we don't want to force conversion to #rrggbb, just update the preview
            entry.textChanged.connect(lambda: self._update_color_preview(entry, preview_btn, color_type))
        else:
            # For ACI, use the existing handler that converts color names to hex values
            def on_entry_changed():
                # Convert any value to hex immediately
                import webcolors
                val = entry.text().strip()
                def name_to_hex(val):
                    try:
                        if val.startswith('#'):
                            return val
                        if val.isdigit():
                            aci = int(val)
                            if aci in dp.ACI_COLOR_MAP:
                                rgb = dp.ACI_COLOR_MAP[aci]
                                return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
                        try:
                            rgb = webcolors.name_to_rgb(val)
                            return '#{:02x}{:02x}{:02x}'.format(rgb.red, rgb.green, rgb.blue)
                        except Exception:
                            pass
                        aci = dp.COLOR_NAME_TO_ACI.get(val.lower())
                        if aci is not None and aci in dp.ACI_COLOR_MAP:
                            rgb = dp.ACI_COLOR_MAP[aci]
                            return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
                        return '#ff0000'
                    except Exception:
                        return '#ff0000'
                
                hex_val = name_to_hex(val)
                
                # Block signals to prevent recursion when setting text
                if val != hex_val:
                    entry.blockSignals(True)
                    entry.setText(hex_val)
                    entry.blockSignals(False)
                
                self._update_color_preview(entry, preview_btn, color_type)

            entry.textChanged.connect(on_entry_changed)
        
        # The preview will be updated by load_initial_values, no need to call it here.
        return entry

    def _pick_color(self, entry_widget, color_type='aci'):
        from PySide6.QtWidgets import QColorDialog
        
        current_color_text = entry_widget.text().strip()
        initial_color = QColor()

        # Try to parse current text as a QColor
        if QColor.isValidColor(current_color_text):
            initial_color.setNamedColor(current_color_text)
        elif color_type == 'kml' and len(current_color_text) == 8 and all(c in "0123456789abcdefABCDEF" for c in current_color_text.lower()):
            # KML AABBGGRR format to QColor #AARRGGBB
            try:
                a = int(current_color_text[0:2], 16)
                b = int(current_color_text[2:4], 16)
                g = int(current_color_text[4:6], 16)
                r = int(current_color_text[6:8], 16)
                initial_color.setRgb(r, g, b, a)
            except ValueError: pass
        elif color_type == 'aci' and current_color_text.isdigit(): # ACI color
            try:
                aci_val = int(current_color_text)
                if aci_val in dp.ACI_COLOR_MAP:
                    rgb = dp.ACI_COLOR_MAP[aci_val]
                    initial_color.setRgb(*rgb)
            except ValueError: pass

        # If initial_color is still invalid, use white as default
        if not initial_color.isValid():
            initial_color = Qt.GlobalColor.white

        # For KML, we need the alpha channel
        dialog_options = QColorDialog.ColorDialogOption.ShowAlphaChannel if color_type == 'kml' else QColorDialog.ColorDialogOption.DontUseNativeDialog
        color = QColorDialog.getColor(initial=initial_color, parent=self, options=dialog_options)
        
        if color.isValid():
            if color_type == 'kml':
                # Convert the QColor to the KML's AABBGGRR format
                kml_color_str = f"{color.alpha():02x}{color.blue():02x}{color.green():02x}{color.red():02x}".lower()
                entry_widget.setText(kml_color_str)
            else:
                # For ACI colors, store the color name or hex value (#rrggbb)
                entry_widget.setText(color.name())

    def _update_color_preview(self, entry_widget, preview_btn, color_type):
        from PySide6.QtGui import QColor
        import webcolors
        color_text = entry_widget.text().strip()
        qt_color = QColor() # Start with an invalid color

        # First, try to create a QColor directly. This handles #rrggbb, "red", etc.
        if QColor.isValidColor(color_text):
            qt_color.setNamedColor(color_text)
        # If the above fails and it's for ACI, it might be an ACI index number
        elif color_type == 'aci':
            try:
                aci_val = int(color_text)
                if aci_val in dp.ACI_COLOR_MAP:
                    rgb = dp.ACI_COLOR_MAP[aci_val]
                    qt_color.setRgb(*rgb)
            except (ValueError, TypeError):
                pass # Not a valid integer, so color remains invalid
        # If it's for KML, it might be in AABBGGRR format
        elif color_type == 'kml':
            try:
                if len(color_text) == 8 and all(c in "0123456789abcdefABCDEF" for c in color_text.lower()):
                    # KML is AABBGGRR, QColor wants #AARRGGBB
                    a = int(color_text[0:2], 16)
                    b = int(color_text[2:4], 16)
                    g = int(color_text[4:6], 16)
                    r = int(color_text[6:8], 16)
                    qt_color.setRgb(r, g, b, a)
            except (ValueError, TypeError):
                pass
        # If still invalid, try to convert color name to hex and retry
        if not qt_color.isValid() and color_text and not color_text.startswith('#'):
            try:
                rgb = webcolors.name_to_rgb(color_text)
                qt_color.setRgb(rgb.red, rgb.green, rgb.blue)
            except Exception:
                aci = dp.COLOR_NAME_TO_ACI.get(color_text.lower())
                if aci is not None and aci in dp.ACI_COLOR_MAP:
                    rgb = dp.ACI_COLOR_MAP[aci]
                    qt_color.setRgb(*rgb)
        
        # Update the button's appearance based on whether the color is valid
        # Using stylesheets is more reliable for dynamic color changes than QPalette.
        base_style = "QPushButton { border: 2px solid #666; border-radius: 3px; }"
        if qt_color.isValid():
            color_hex = qt_color.name()
            preview_btn.setStyleSheet(f"background-color: {color_hex}; {base_style}")
            preview_btn.setToolTip(f"Valid color: {color_hex}")
        else:
            preview_btn.setStyleSheet(f"background-color: #808080; {base_style}") # Gray for invalid
            preview_btn.setToolTip("Invalid color format")


class DXFSettingsDialog(SettingsDialogBase):
    """
    Dialog for DXF export settings, allowing the user to customize export options.
    """
    def __init__(self, parent, current_settings):
        # We need access to the main window's data for the preview
        self.main_window = parent 
        super().__init__(parent, current_settings, "DXF Settings")
        self._settings = config.PROFILE_CFG.get('dxf', {})
        self._apply_styles()

    def _apply_styles(self):
        stylesheet = """
            QDialog, QScrollArea, QWidget {
                background-color: #F8F9FA;
                color: #212529;
            }
            QGroupBox {
                font-size: 10pt;
                font-weight: bold;
                border: 1px solid #DEE2E6;
                border-radius: 8px;
                margin-top: 10px;
                padding: 15px;
                background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 10px;
                color: #005A9E;
                background-color: #FFFFFF;
            }
            QLabel, QCheckBox, QRadioButton {
                font-size: 9pt;
                color: #212529; /* Explicitly dark color */
                background-color: transparent;
            }
            QLabel[cssClass="header"] {
                font-size: 11pt;
                font-weight: bold;
                color: #005A9E; /* Header color */
                margin-top: 10px;
                margin-bottom: 5px;
                border-bottom: 2px solid #E9ECEF;
                padding-bottom: 4px;
            }
            QLineEdit, QComboBox {
                padding: 6px;
                border: 1px solid #CED4DA;
                border-radius: 4px;
                background-color: white;
                font-size: 9pt;
                color: #212529; /* Ensure input text is dark */
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #80BDFF;
            }
            QPushButton {
                background-color: #6C757D;
                color: white;
                font-size: 9pt;
                font-weight: bold;
                padding: 7px 15px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #5A6268;
            }
            QDialogButtonBox QPushButton, QPushButton[cssClass="primary"] {
                background-color: #007BFF;
            }
            QDialogButtonBox QPushButton:hover, QPushButton[cssClass="primary"]:hover {
                background-color: #0069D9;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
        """
        self.setStyleSheet(stylesheet)

    def add_custom_buttons(self):
        self.preview_button = QPushButton("Preview in AutoCAD")
        self.preview_button.setToolTip(config.UI_CFG['kml_preview_tooltip'])
        self.preview_button.setProperty("cssClass", "primary")
        self.button_box.addButton(self.preview_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.preview_button.clicked.connect(self._generate_dxf_preview)

    def _generate_dxf_preview(self):
        """Generates and displays a preview of the DXF file."""
        try:
            # 1. Get current settings from the dialog
            settings = self.validate_and_get_values()
            if not settings:
                # Validation failed, message already shown by try_accept
                return

            # 2. Get data from the main table
            if not hasattr(self.main_window, 'get_current_data_for_export'):
                 QMessageBox.critical(self, "Error", "Cannot access the main table data for preview.")
                 return
            
            points_data = self.main_window.get_current_data_for_export()
            if not points_data:
                QMessageBox.information(self, config.UI_CFG['export_no_data_title'], config.UI_CFG['export_no_data_text'])
                return

            # 3. Generate DXF in a temporary location
            temp_dir = utils.get_temp_dir()
            temp_filepath = os.path.join(temp_dir, "preview.dxf")
            
            # Corrected function call
            import pandas as pd
            points_df = pd.DataFrame(points_data)
            for col in [dp.COL_E, dp.COL_N, dp.COL_Z]:
                if col in points_df.columns:
                    points_df[col] = pd.to_numeric(points_df[col], errors='coerce').fillna(0.0)
            dp.export_dxf_file(points_df, Path(temp_filepath), settings)

            # 4. Open the generated file with the default system application
            if os.path.exists(temp_filepath):
                # Use a cross-platform way to open the file
                import subprocess, sys
                try:
                    if sys.platform == "win32":
                        os.startfile(temp_filepath)
                    elif sys.platform == "darwin": # macOS
                        subprocess.run(["open", temp_filepath], check=True)
                    else: # linux
                        subprocess.run(["xdg-open", temp_filepath], check=True)
                except Exception as e:
                    QMessageBox.critical(self, config.UI_CFG['kml_preview_error_title'], f"Could not open the DXF file. Make sure a DXF viewer is installed.\n\nError: {e}")
            else:
                QMessageBox.warning(self, config.UI_CFG['kml_preview_error_title'], "Failed to create the temporary DXF file for preview.")

        except ValueError as ve:
            # This will catch validation errors from validate_and_get_values
            QMessageBox.warning(self, config.UI_CFG['kml_preview_validation_error_title'], str(ve))
        except Exception as e:
            logging.error(f"DXF preview generation failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Unexpected Error", f"An error occurred while creating the preview:\n{e}")

    def create_widgets(self):
        layout = self.content_layout
        layout.setColumnStretch(1, 1)
        layout.setVerticalSpacing(12) # Add vertical spacing
        row_num = 0

        def add_header(text):
            nonlocal row_num
            header_label = QLabel(text)
            header_label.setProperty("cssClass", "header")
            layout.addWidget(header_label, row_num, 0, 1, 3)
            row_num += 1

        add_header("General")
        
        self._add_label_combobox(layout, row_num, "Export Format", 'export_format', ["DXF", "DWG"], current_val_data=self._settings.get('export_format', 'DXF'))
        row_num += 1

        self._add_label_entry(layout, row_num, "Base Layer Name", 'layer_name', placeholder_text="Survey_Export")
        row_num += 1
        
        color_mode_combo = QComboBox()
        color_mode_combo.addItems(DXF_COLOR_MODES)
        color_mode_combo.setCurrentText(self._settings.get('color_mode', DEFAULT_DXF_COLOR_MODE))
        self.widgets['color_mode'] = color_mode_combo
        self.widgets['color_mode_explanation_lbl'] = QLabel("")
        
        self._add_grid_checkbutton(layout, row_num, 0, "Use 'Code' as layer name for points/blocks", 'use_code_as_layer', columnspan=3)
        row_num += 1
        self._add_label_entry(layout, row_num, "Line Layer Prefix (DXF)", 'dxf_line_layer_prefix', placeholder_text="LINE_")
        row_num += 1
        self._add_label_entry(layout, row_num, "Polyline Layer Prefix (DXF)", 'dxf_polyline_layer_prefix', placeholder_text="POLYLINE_")
        row_num += 1
        self._add_label_entry(layout, row_num, "Polygon Layer Prefix (DXF)", 'dxf_poly_layer_prefix', placeholder_text="POLY_")
        row_num += 1
        
        add_header("Geometry Types")
        geom_frame=QWidget(); geom_layout=QHBoxLayout(geom_frame); geom_layout.setContentsMargins(0,0,0,0)
        self.widgets['export_points'] = self._add_hbox_checkbutton(geom_layout, "Export Points", 'export_points')
        self.widgets['export_lines'] = self._add_hbox_checkbutton(geom_layout, "Export Lines", 'export_lines')
        self.widgets['export_polylines'] = self._add_hbox_checkbutton(geom_layout, "Export Polylines", 'export_polylines')
        self.widgets['export_polygons'] = self._add_hbox_checkbutton(geom_layout, "Export Polygons", 'export_polygons')
        layout.addWidget(geom_frame, row_num, 0, 1, 3); row_num += 1
        
        add_header("Geometry Appearance")
        self._add_color_button(layout, row_num, "Point Color (ACI)", 'point_color', color_type='aci', default_color_val="1"); row_num += 1
        self._add_color_button(layout, row_num, "Line Color (ACI)", 'line_color', color_type='aci', default_color_val="3"); row_num += 1
        self._add_color_button(layout, row_num, "Polygon Color (ACI)", 'poly_color', color_type='aci', default_color_val="5"); row_num += 1
        self._add_grid_checkbutton(layout, row_num, 0, "Points as Blocks", 'export_as_blocks', columnspan=3); row_num += 1
        
        # Point Style Group
        point_style_group = QGroupBox("Point Style (PDMODE)")
        point_style_layout = QGridLayout(point_style_group)
        point_style_layout.setSpacing(10)
        
        self.point_style_button_group = QButtonGroup(self)
        self.widgets['point_style_radios'] = {}
        styles_data = list(dp.DXF_POINT_STYLE_MAP.items())
        grid_row, grid_col = 0, 0
        for style_name, style_val in styles_data:
            display_name = style_name.replace("_", " ").title()
            radio_btn = QRadioButton("")
            icon = utils.get_icon(f"{style_name}_style.png", size=32)
            if not icon.isNull(): radio_btn.setIcon(icon)
            radio_btn.setIconSize(QSize(32, 32))
            radio_btn.setToolTip(display_name)
            radio_btn.setProperty("style_key_name", style_name)
            self.point_style_button_group.addButton(radio_btn)
            self.widgets['point_style_radios'][style_name] = radio_btn
            point_style_layout.addWidget(radio_btn, grid_row, grid_col)
            grid_col += 1
            if grid_col > 3: grid_col = 0; grid_row += 1
        
        layout.addWidget(point_style_group, row_num, 0, 1, 3); row_num += 1
        self._add_label_entry(layout, row_num, "Point Size (PDSIZE)", 'point_size', placeholder_text="0.1")
        row_num += 1
        
        self.dxf_line_settings_group = QGroupBox("Line/Polygon Connection")
        dxf_line_layout = QGridLayout(self.dxf_line_settings_group)
        line_conn_opts = [("Sequential (by current order)", "sequential"), ("By Point Number (PT)", "by_pt"), ("By Code", "code"), ("By Description", "description"), ("Custom Column", "custom")]
        line_grp_row = 0
        dxf_line_logic_combo = self._add_label_combobox(dxf_line_layout, line_grp_row, "Connection Logic:", 'line_connection_logic_key', line_conn_opts, colspan=2, current_val_data=self._settings.get('line_connection_logic_key','sequential'))
        self.widgets['dxf_line_connection_logic'] = dxf_line_logic_combo
        self.widgets['dxf_line_connection_logic'].currentIndexChanged.connect(self._update_dxf_custom_column_visibility)
        line_grp_row +=1
        self.dxf_custom_line_column_label = QLabel("Custom Grouping Column Name:")
        self.widgets['dxf_custom_line_grouping_column'] = QLineEdit()
        dxf_line_layout.addWidget(self.dxf_custom_line_column_label, line_grp_row, 0)
        dxf_line_layout.addWidget(self.widgets['dxf_custom_line_grouping_column'], line_grp_row, 1, 1, 2); line_grp_row += 1
        self._add_grid_checkbutton(dxf_line_layout, line_grp_row, 0, "Sort Points in Group (by PT)", 'sort_points_in_line_group', columnspan=3)
        layout.addWidget(self.dxf_line_settings_group, row_num, 0, 1, 3); row_num += 1
        
        add_header("Text Labels")
        labels_frame=QWidget(); labels_layout=QHBoxLayout(labels_frame); labels_layout.setContentsMargins(0,0,0,0); self.widgets['export_options_checkboxes'] = {}
        for label_type_disp in ['Point Number', 'Description', 'Elevation', 'Code']:
            chk_key = f"export_option_{label_type_disp.replace(' ', '_')}"
            self.widgets['export_options_checkboxes'][label_type_disp] = self._add_hbox_checkbutton(labels_layout, label_type_disp, chk_key)
        layout.addWidget(labels_frame, row_num, 0, 1, 3); row_num +=1
        
        self._add_label_entry(layout, row_num, "Text Layer Prefix", 'text_layer_prefix', placeholder_text="Text_")
        row_num += 1
        self._add_label_entry(layout, row_num, "Text Rotation (degrees)", 'text_rotation', placeholder_text="0.0")
        row_num += 1
        
        text_details_group = QGroupBox("Text Label Details")
        text_details_layout = QGridLayout(text_details_group)
        td_row = 0
        for label_type_setting in ['Point Number','Description','Elevation','Code']:
             key_base = label_type_setting.replace(" ","_")
             text_details_layout.addWidget(QLabel(f"<b>{label_type_setting}</b>:"), td_row, 0, 1, 4)
             td_row += 1
             self._add_label_entry(text_details_layout, td_row, " Height", f"{key_base}_height", placeholder_text=str(self._settings.get(f'{key_base}_height',0.2)))
             td_row += 1
             self._add_label_entry(text_details_layout, td_row, " Y Offset Factor", f"{key_base}_offset", placeholder_text=str(self._settings.get(f'{key_base}_offset',0.1)))
             td_row += 1
             self._add_color_button(text_details_layout, td_row, " Color (ACI)", f"{key_base}_color", color_type='aci', default_color_val='7')
             td_row += 1
             if label_type_setting != 'Code':
                 sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine); text_details_layout.addWidget(sep, td_row, 0, 1, 4)
                 td_row +=1
        layout.addWidget(text_details_group, row_num, 0, 1, 3); row_num += 1
        
        self.widgets['color_mode'].currentIndexChanged.connect(self._on_color_mode_change)
        self.widgets['export_lines'].stateChanged.connect(self._update_dxf_line_settings_visibility)
        self.widgets['export_polylines'].stateChanged.connect(self._update_dxf_line_settings_visibility)
        self.widgets['export_polygons'].stateChanged.connect(self._update_dxf_line_settings_visibility)
        
        self._on_color_mode_change()
        self._update_dxf_line_settings_visibility()

    def _on_color_mode_change(self):
        # This function is kept for compatibility, but since color mode is now fixed to "By Entity",
        # all related widgets will always be enabled.
        is_by_entity_mode = True
        self.widgets['color_mode_explanation_lbl'].setText("A color is assigned to each individual entity.")
        
        keys_to_toggle = ['point_color', 'line_color', 'poly_color', 
                          'Point_Number_color', 'Description_color', 'Elevation_color', 'Code_color']
                          
        for key in keys_to_toggle:
            if key in self.widgets:
                self.widgets[key].setEnabled(is_by_entity_mode)
            if f"{key}_preview" in self.widgets:
                self.widgets[f"{key}_preview"].setEnabled(is_by_entity_mode)
            if f"{key}_button" in self.widgets:
                self.widgets[f"{key}_button"].setEnabled(is_by_entity_mode)

    def _update_dxf_line_settings_visibility(self):
        is_lines_or_polys_enabled = self.widgets['export_lines'].isChecked() or self.widgets['export_polygons'].isChecked() or self.widgets['export_polylines'].isChecked()
        self.dxf_line_settings_group.setVisible(is_lines_or_polys_enabled)
        self._update_dxf_custom_column_visibility()

    def _update_dxf_custom_column_visibility(self):
        is_custom_logic = self.widgets['dxf_line_connection_logic'].currentData() == "custom"
        show_custom_fields = self.dxf_line_settings_group.isVisible() and is_custom_logic
        self.dxf_custom_line_column_label.setVisible(show_custom_fields)
        self.widgets['dxf_custom_line_grouping_column'].setVisible(show_custom_fields)

    def update_dependent_visibilities(self):
        self._on_color_mode_change()
        self._update_dxf_line_settings_visibility()

    def load_initial_values(self):
        s=self._settings
        self.widgets['export_format'].setCurrentText(s.get('export_format', 'DXF'))
        self.widgets['layer_name'].setText(s.get('layer_name','Survey_Export'))
        self.widgets['use_code_as_layer'].setChecked(s.get('use_code_as_layer', True))
        self.widgets['dxf_line_layer_prefix'].setText(s.get('dxf_line_layer_prefix','LINE_'))
        self.widgets['dxf_polyline_layer_prefix'].setText(s.get('dxf_polyline_layer_prefix', 'POLYLINE_'))
        self.widgets['dxf_poly_layer_prefix'].setText(s.get('dxf_poly_layer_prefix','POLY_'))
        self.widgets['export_points'].setChecked(s.get('export_points',True))
        self.widgets['export_lines'].setChecked(s.get('export_lines',False))
        self.widgets['export_polylines'].setChecked(s.get('export_polylines', False))
        self.widgets['export_polygons'].setChecked(s.get('export_polygons',False))

        # The textChanged signal will trigger the color preview update
        self.widgets['point_color'].setText(str(s.get('point_color','#ffff7f')))
        self.widgets['line_color'].setText(str(s.get('line_color','#ffaa00')))
        self.widgets['poly_color'].setText(str(s.get('poly_color','#ff557f')))

        self.widgets['export_as_blocks'].setChecked(s.get('export_as_blocks',True))
        
        current_style_key = s.get('point_style', 'circle_cross')
        radio_to_check = self.widgets['point_style_radios'].get(current_style_key)
        if radio_to_check:
            radio_to_check.setChecked(True)
        else:
            # Fallback to the first radio button if the key is invalid
            if self.widgets['point_style_radios']:
                first_radio = next(iter(self.widgets['point_style_radios'].values()))
                first_radio.setChecked(True)
        
        self.widgets['point_size'].setText(str(s.get('point_size',0.1)))
        self.widgets['dxf_custom_line_grouping_column'].setText(s.get('custom_line_grouping_column', ''))
        self.widgets['sort_points_in_line_group'].setChecked(s.get('sort_points_in_line_group', True))
        
        current_export_options = s.get('export_options',[])
        for label_disp_name, chk_box in self.widgets['export_options_checkboxes'].items():
            chk_box.setChecked(label_disp_name in current_export_options)
            
        self.widgets['text_layer_prefix'].setText(s.get('text_layer_prefix','Text_'))
        self.widgets['text_rotation'].setText(str(s.get('text_rotation',0.0)))
        
        for label_type_setting in ['Point Number','Description','Elevation','Code']:
             key_base = label_type_setting.replace(" ","_")
             self.widgets[f'{key_base}_height'].setText(str(s.get(f'{key_base}_height',0.2)))
             self.widgets[f'{key_base}_offset'].setText(str(s.get(f'{key_base}_offset',0.1)))
             
             color_val = s.get(f'{key_base}_color', '#55aaff')
             self.widgets[f'{key_base}_color'].setText(str(color_val))
             
        self.update_dependent_visibilities()
        
        # The color previews are now updated automatically via the textChanged signal
        # when setText is called. The explicit calls below are redundant and have been removed.

    def validate_and_get_values(self):
        import webcolors
        new_s = {}; errors = []
        new_s['export_format'] = self.widgets['export_format'].currentText()
        new_s['layer_name']=self.widgets['layer_name'].text().strip() or 'Survey_Export'
        new_s['color_mode']=self.widgets['color_mode'].currentText()
        new_s['use_code_as_layer'] = self.widgets['use_code_as_layer'].isChecked()
        new_s['dxf_line_layer_prefix'] = self.widgets['dxf_line_layer_prefix'].text().strip() or 'LINE_'
        new_s['dxf_polyline_layer_prefix'] = self.widgets['dxf_polyline_layer_prefix'].text().strip() or 'POLYLINE_'
        new_s['dxf_poly_layer_prefix'] = self.widgets['dxf_poly_layer_prefix'].text().strip() or 'POLY_'
        new_s['export_points']=self.widgets['export_points'].isChecked()
        new_s['export_lines']=self.widgets['export_lines'].isChecked()
        new_s['export_polylines'] = self.widgets['export_polylines'].isChecked()
        new_s['export_polygons']=self.widgets['export_polygons'].isChecked()
        new_s['export_as_blocks']=self.widgets['export_as_blocks'].isChecked()
        
        checked_button = self.point_style_button_group.checkedButton()
        if checked_button:
            new_s['point_style'] = checked_button.property("style_key_name")
        else:
            # Fallback if somehow no button is checked
            new_s['point_style'] = 'dot'
        
        try: new_s['point_size'] = float(self.widgets['point_size'].text())
        except ValueError: errors.append("Invalid Point Size (PDSIZE). Must be a number."); new_s['point_size'] = 0.1
        
        new_s['line_connection_logic_key'] = self.widgets['dxf_line_connection_logic'].currentData()
        new_s['custom_line_grouping_column'] = self.widgets['dxf_custom_line_grouping_column'].text().strip()
        new_s['sort_points_in_line_group'] = self.widgets['sort_points_in_line_group'].isChecked()
        if new_s['line_connection_logic_key'] == 'custom' and not new_s['custom_line_grouping_column'] and (new_s['export_lines'] or new_s['export_polygons'] or new_s['export_polylines']):
             errors.append("Custom grouping column name is required when 'Custom Column' connection logic is selected.")
             
        new_s['export_options'] = [label_disp for label_disp, chk_box in self.widgets['export_options_checkboxes'].items() if chk_box.isChecked()]
        if not any([new_s['export_points'], new_s['export_lines'], new_s['export_polylines'], new_s['export_polygons']]) and not new_s['export_options']:
            errors.append("At least one geometry type or text label must be selected for export.")
            
        new_s['text_layer_prefix'] = self.widgets['text_layer_prefix'].text().strip() or 'Text_'
        try: new_s['text_rotation'] = float(self.widgets['text_rotation'].text())
        except ValueError: errors.append("Invalid Text Rotation. Must be a number."); new_s['text_rotation'] = 0.0
        
        # Always save color values as hex text (supports names)
        def name_to_hex(val):
            try:
                if val.startswith('#'):
                    return val
                if val.isdigit():
                    aci = int(val)
                    if aci in dp.ACI_COLOR_MAP:
                        rgb = dp.ACI_COLOR_MAP[aci]
                        return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
                # Try webcolors
                try:
                    rgb = webcolors.name_to_rgb(val)
                    return '#{:02x}{:02x}{:02x}'.format(rgb.red, rgb.green, rgb.blue)
                except Exception:
                    pass
                # Try COLOR_NAME_TO_ACI
                aci = dp.COLOR_NAME_TO_ACI.get(val.lower())
                if aci is not None and aci in dp.ACI_COLOR_MAP:
                    rgb = dp.ACI_COLOR_MAP[aci]
                    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
                # If all fails, fallback to a default color and warn
                print(f"[WARNING] Unknown color name: {val}, using default #ff0000")
                return '#ff0000'
            except Exception as e:
                print(f"[ERROR] Failed to convert color: {val}, error: {e}")
                return '#ff0000'
        new_s['point_color'] = name_to_hex(self.widgets['point_color'].text().strip())
        new_s['line_color'] = name_to_hex(self.widgets['line_color'].text().strip())
        new_s['poly_color'] = name_to_hex(self.widgets['poly_color'].text().strip())
        
        for label_type_setting in ['Point Number', 'Description', 'Elevation', 'Code']:
            key_base = label_type_setting.replace(" ", "_")
            try: new_s[f'{key_base}_height'] = float(self.widgets[f'{key_base}_height'].text())
            except ValueError: errors.append(f"Invalid '{label_type_setting}' text height."); new_s[f'{key_base}_height'] = 0.2
            try: new_s[f'{key_base}_offset'] = float(self.widgets[f'{key_base}_offset'].text())
            except ValueError: errors.append(f"Invalid '{label_type_setting}' text offset."); new_s[f'{key_base}_offset'] = 0.1
            new_s[f'{key_base}_color'] = name_to_hex(self.widgets[f'{key_base}_color'].text().strip())
            
        if errors:
            raise ValueError("Please correct the following errors:\n" + "\n".join(f"- {e}" for e in errors))
            
        return new_s


class KMLSettingsDialog(SettingsDialogBase):
    """
    Dialog for KML export settings, allowing customization of icons, colors,
    geometry types, and point connection logic.
    """
    def __init__(self, parent, current_settings):
        self.line_connection_options = [("Sequential (by current order)", "sequential"),
                                        ("By Point Number (PT)", "by_pt"),
                                        ("By Code", "code"),
                                        ("By Description", "description"),
                                        ("Custom Column", "custom")]
        super().__init__(parent, current_settings, "KML Settings")
        self._settings = config.PROFILE_CFG.get('kml', {})
        self._apply_styles()

    def _apply_styles(self):
        # This stylesheet is similar to the DXF dialog for a consistent look and feel.
        stylesheet = """
            QDialog, QScrollArea, QWidget {
                background-color: #F8F9FA;
                color: #212529;
            }
            QGroupBox {
                font-size: 10pt;
                font-weight: bold;
                border: 1px solid #DEE2E6;
                border-radius: 8px;
                margin-top: 10px;
                padding: 15px;
                background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 10px;
                color: #005A9E;
                background-color: #FFFFFF;
            }
            QLabel, QCheckBox {
                font-size: 9pt;
                color: #212529;
                background-color: transparent;
            }
            QLabel[cssClass="header"] {
                font-size: 11pt;
                font-weight: bold;
                color: #005A9E;
                margin-top: 10px;
                margin-bottom: 5px;
                border-bottom: 2px solid #E9ECEF;
                padding-bottom: 4px;
            }
            QLineEdit, QComboBox {
                padding: 6px;
                border: 1px solid #CED4DA;
                border-radius: 4px;
                background-color: white;
                font-size: 9pt;
                color: #212529;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #80BDFF;
            }
            QPushButton {
                background-color: #6C757D;
                color: white;
                font-size: 9pt;
                font-weight: bold;
                padding: 7px 15px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #5A6268;
            }
            QDialogButtonBox QPushButton {
                background-color: #007BFF;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #0069D9;
            }
        """
        self.setStyleSheet(stylesheet)

    def create_widgets(self):
        layout = self.content_layout
        layout.setColumnStretch(1, 1)
        layout.setVerticalSpacing(12)
        row_num = 0

        def add_header(text):
            nonlocal row_num
            header_label = QLabel(text)
            header_label.setProperty("cssClass", "header")
            layout.addWidget(header_label, row_num, 0, 1, 3)
            row_num += 1

        add_header("General Settings")
        
        self._add_label_entry(layout, row_num, "Document Name", 'name', placeholder_text="Survey Export"); row_num += 1
        self._add_label_combobox(layout, row_num, "File Format", 'kml_format', ["KML", "KMZ"], current_val_data=self._settings.get('kml_format','KML')); row_num += 1
        
        utm_zone_hbox = QHBoxLayout()
        self.widgets['zone_number_entry'] = QLineEdit()
        self.widgets['zone_number_entry'].setToolTip("UTM Zone Number (1-60)"); self.widgets['zone_number_entry'].setFixedWidth(50)
        self.widgets['zone_letter_entry'] = QLineEdit()
        self.widgets['zone_letter_entry'].setToolTip("UTM Zone Letter (C-X, no I, O)"); self.widgets['zone_letter_entry'].setFixedWidth(30)
        utm_zone_hbox.addWidget(QLabel("UTM Zone:"))
        utm_zone_hbox.addWidget(self.widgets['zone_number_entry'])
        utm_zone_hbox.addWidget(self.widgets['zone_letter_entry'])
        utm_zone_hbox.addStretch()
        layout.addLayout(utm_zone_hbox, row_num, 1, 1, 1); row_num += 1
        self._add_grid_checkbutton(layout, row_num, 0, "Open file after saving", 'open_after_save', columnspan=3); row_num += 1
        
        add_header("Geometry Export")
        geom_frame = QWidget(); geom_layout = QHBoxLayout(geom_frame); geom_layout.setContentsMargins(0,0,0,0); self.widgets['geometry_type_checkboxes'] = {}
        for geom_name in ['Point', 'Line', 'Polygon']:
            chk = self._add_hbox_checkbutton(geom_layout, geom_name, f'geom_type_{geom_name}' )
            chk.stateChanged.connect(self.update_dependent_visibilities)
            self.widgets['geometry_type_checkboxes'][geom_name] = chk
        layout.addWidget(geom_frame, row_num, 0, 1, 3); row_num += 1
        
        self.point_settings_group = QGroupBox("Point Style"); point_layout = QGridLayout(self.point_settings_group); p_row = 0
        self._add_label_entry(point_layout, p_row, "Icon URL", 'icon_url', placeholder_text=dp.DEFAULT_KML_ICON); p_row += 1
        self._add_label_entry(point_layout, p_row, "Icon Scale", 'scale', placeholder_text="1.0"); p_row += 1
        self._add_color_button(point_layout, p_row, "Icon Color", 'color', 'kml', default_color_val="ffffffff"); p_row += 1
        
        label_content_options = ['Point Number (PT)' , 'Code', 'Description', 'Elevation', 'None']
        self._add_label_combobox(point_layout, p_row, "Label Content", 'label_content', label_content_options, current_val_data=self._settings.get('label_content','Point Number (PT)')); p_row += 1
        self._add_label_entry(point_layout, p_row, "Label Scale", 'label_scale', placeholder_text="0.8"); p_row += 1
        self._add_color_button(point_layout, p_row, "Label Color", 'label_color', 'kml', default_color_val="ffffffff"); p_row += 1
        layout.addWidget(self.point_settings_group, row_num, 0, 1, 3); row_num += 1
        
        self.line_poly_group = QGroupBox("Line/Polygon Style & Connection"); lp_layout = QGridLayout(self.line_poly_group); lp_row = 0
        line_logic_combo = self._add_label_combobox(lp_layout, lp_row, "Connection Logic:", 'line_connection_logic_key',
                                                                              self.line_connection_options, colspan=2,
                                                                              current_val_data=self._settings.get('line_connection_logic_key','sequential'))
        self.widgets['kml_line_connection_logic'] = line_logic_combo
        self.widgets['kml_line_connection_logic'].currentIndexChanged.connect(self._update_kml_custom_column_visibility)
        lp_row +=1
        
        self.kml_custom_col_lbl = QLabel("Custom Grouping Column:");
        self.widgets['kml_custom_line_grouping_column'] = QLineEdit()
        lp_layout.addWidget(self.kml_custom_col_lbl, lp_row, 0, Qt.AlignmentFlag.AlignLeft)
        lp_layout.addWidget(self.widgets['kml_custom_line_grouping_column'], lp_row, 1, 1, 2); lp_row += 1
        
        self.widgets['kml_sort_points_in_line_group'] = self._add_grid_checkbutton(lp_layout, lp_row, 0, "Sort Points in Group (by PT)", 'sort_points_in_line_group', columnspan=3); lp_row += 1
        self._add_label_entry(lp_layout, lp_row, "Line Width", 'line_width', placeholder_text="2"); lp_row +=1
        self._add_color_button(lp_layout, lp_row, "Line Color", 'line_color', 'kml', default_color_val="ff00aaff"); lp_row +=1
        layout.addWidget(self.line_poly_group, row_num, 0, 1, 3); row_num += 1
        
        self.poly_style_group = QGroupBox("Polygon Style"); poly_layout = QGridLayout(self.poly_style_group); poly_row = 0
        self._add_grid_checkbutton(poly_layout, poly_row, 0, "Fill Polygon", 'poly_fill', columnspan=3); poly_row += 1
        self._add_color_button(poly_layout, poly_row, "Fill Color", 'fill_color', 'kml', default_color_val="8000aaff"); poly_row += 1
        self._add_label_entry(poly_layout, poly_row, "Outline Width", 'poly_outline_width', placeholder_text="1"); poly_row += 1
        self._add_color_button(poly_layout, poly_row, "Outline Color", 'poly_outline_color', 'kml', default_color_val="ff00aaff"); poly_row += 1
        layout.addWidget(self.poly_style_group, row_num, 0, 1, 3); row_num += 1
        
        self.update_dependent_visibilities()

    def update_dependent_visibilities(self):
        is_point_checked = self.widgets['geometry_type_checkboxes']['Point'].isChecked()
        is_line_checked = self.widgets['geometry_type_checkboxes']['Line'].isChecked()
        is_poly_checked = self.widgets['geometry_type_checkboxes']['Polygon'].isChecked()
        
        self.point_settings_group.setVisible(is_point_checked)
        self.line_poly_group.setVisible(is_line_checked or is_poly_checked)
        self.poly_style_group.setVisible(is_poly_checked)
        self._update_kml_custom_column_visibility()

    def _update_kml_custom_column_visibility(self):
        is_custom_logic_selected = self.widgets['kml_line_connection_logic'].currentData() == "custom"
        show_custom_fields = self.line_poly_group.isVisible() and is_custom_logic_selected
        self.kml_custom_col_lbl.setVisible(show_custom_fields)
        self.widgets['kml_custom_line_grouping_column'].setVisible(show_custom_fields)

    def load_initial_values(self):
        s = self._settings
        self.widgets['name'].setText(s.get('name', 'Survey Export KML'))
        self.widgets['zone_number_entry'].setText(str(s.get('zone_number', 36)))
        self.widgets['zone_letter_entry'].setText(str(s.get('zone_letter', 'N')).upper())
        self.widgets['open_after_save'].setChecked(s.get('open_after_save', False))
        # --- [الإصلاح] تحميل أنواع الهندسة كما هي من الإعدادات ---
        
        current_geom_types = s.get('geometry_type', ['Point', 'Line', 'Polygon'])
        for geom_name, chk_box in self.widgets['geometry_type_checkboxes'].items():
            chk_box.setChecked(geom_name in current_geom_types)
            
        self.widgets['icon_url'].setText(s.get('icon_url', dp.DEFAULT_KML_ICON))
        self.widgets['scale'].setText(str(s.get('scale', 1.0)))
        self.widgets['color'].setText(s.get('color', 'ffffffff'))
        self.widgets['label_scale'].setText(str(s.get('label_scale', 0.8)))
        self.widgets['label_color'].setText(s.get('label_color', 'ffffffff'))
        self.widgets['label_content'].setCurrentText(s.get('label_content', 'Point Number (PT)'))
        
        self.widgets['line_width'].setText(str(s.get('line_width', 2)))
        self.widgets['line_color'].setText(s.get('line_color', 'ff00aaff'))
        self.widgets['kml_custom_line_grouping_column'].setText(s.get('custom_line_grouping_column', ''))
        self.widgets['kml_sort_points_in_line_group'].setChecked(s.get('sort_points_in_line_group', True))
        
        self.widgets['poly_fill'].setChecked(s.get('poly_fill', True))
        self.widgets['fill_color'].setText(s.get('fill_color', '8000aaff'))
        self.widgets['poly_outline_width'].setText(str(s.get('poly_outline_width', 1)))
        self.widgets['poly_outline_color'].setText(s.get('poly_outline_color', 'ff00aaff'))
        
        self.update_dependent_visibilities()
        
        # The color previews are now updated automatically via the textChanged signal
        # when setText is called. The explicit calls below are redundant and have been removed.

    def validate_and_get_values(self):
        new_s = {}; errors = []
        
        new_s['name'] = self.widgets['name'].text().strip() or "KML Survey Export"
        new_s['kml_format'] = self.widgets['kml_format'].currentText()
        try:
            zn = int(self.widgets['zone_number_entry'].text())
            zl = self.widgets['zone_letter_entry'].text().strip().upper()
            if not (1 <= zn <= 60): errors.append("UTM Zone Number must be between 1 and 60.")
            if not (len(zl) == 1 and 'C' <= zl <= 'X' and zl not in ['I', 'O']):
                errors.append("Invalid UTM Zone Letter (must be C-X, excluding I, O).")
            if not errors: new_s['zone_number'], new_s['zone_letter'] = zn, zl
        except ValueError: errors.append("UTM Zone Number must be an integer.")
        
        new_s['open_after_save'] = self.widgets['open_after_save'].isChecked()
        
        new_s['geometry_type'] = [name for name, chk in self.widgets['geometry_type_checkboxes'].items() if chk.isChecked()]
        if not new_s['geometry_type']: errors.append("At least one geometry type must be selected.")
        
        if 'Point' in new_s['geometry_type']:
            new_s['icon_url'] = self.widgets['icon_url'].text().strip() or dp.DEFAULT_KML_ICON
            try: new_s['scale'] = float(self.widgets['scale'].text())
            except ValueError: errors.append("Invalid Point Icon Scale."); new_s['scale'] = 1.0
            new_s['color'] = self.widgets['color'].text().strip() or 'ffffffff'
            new_s['label_content'] = self.widgets['label_content'].currentText()
            try: new_s['label_scale'] = float(self.widgets['label_scale'].text())
            except ValueError: errors.append("Invalid Point Label Scale."); new_s['label_scale'] = 0.8
            new_s['label_color'] = self.widgets['label_color'].text().strip() or 'ffffffff'
            
        if 'Line' in new_s['geometry_type'] or 'Polygon' in new_s['geometry_type']:
            new_s['line_connection_logic_key'] = self.widgets['kml_line_connection_logic'].currentData()
            new_s['custom_line_grouping_column'] = self.widgets['kml_custom_line_grouping_column'].text().strip()
            new_s['sort_points_in_line_group'] = self.widgets['kml_sort_points_in_line_group'].isChecked()
            if new_s['line_connection_logic_key'] == 'custom' and not new_s['custom_line_grouping_column']:
                 errors.append("Custom grouping column name is required when 'Custom Column' logic is selected.")
            try: new_s['line_width'] = int(self.widgets['line_width'].text())
            except ValueError: errors.append("Invalid Line Width."); new_s['line_width'] = 2
            new_s['line_color'] = self.widgets['line_color'].text().strip() or 'ff00aaff'
            
        if 'Polygon' in new_s['geometry_type']:
            new_s['poly_fill'] = self.widgets['poly_fill'].isChecked()
            new_s['fill_color'] = self.widgets['fill_color'].text().strip() or '8000aaff'
            try: new_s['poly_outline_width'] = int(self.widgets['poly_outline_width'].text())
            except ValueError: errors.append("Invalid Polygon Outline Width."); new_s['poly_outline_width'] = 1
            new_s['poly_outline_color'] = self.widgets['poly_outline_color'].text().strip() or 'ff00aaff'
            
        if errors:
            raise ValueError("Please correct the following errors:\n" + "\n".join(f"- {e}" for e in errors))
            
        return new_s

class FindDialog(QDialog):
    """Advanced search dialog for the table"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(config.UI_CFG['find_dialog_title'])
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        # Get column names from the source model
        self.source_model = parent.table_model if parent else None
        self.column_names = []
        if self.source_model:
            self.column_names = [self.source_model.headerData(i, Qt.Orientation.Horizontal) 
                               for i in range(self.source_model.columnCount())]
        
        self.main_layout = QVBoxLayout(self)
        self._create_search_section()
        self._create_options_section()
        # إزالة قسم الأعمدة نهائياً والبحث دائماً في جميع الأعمدة
        self._create_buttons_section()
        
        # Connect signals
        self.match_type_combo.currentTextChanged.connect(self._on_match_type_changed)
        
    def _create_search_section(self):
        """Create the main search section"""
        search_group = QGroupBox("Search Text")
        search_layout = QVBoxLayout(search_group)
        
        # Search field
        search_hbox = QHBoxLayout()
        search_hbox.addWidget(QLabel("Search Text:"))
        self.find_text_edit = QLineEdit()
        self.find_text_edit.setPlaceholderText("Enter text to search for...")
        search_hbox.addWidget(self.find_text_edit)
        search_layout.addLayout(search_hbox)
        
        # Match type
        match_hbox = QHBoxLayout()
        match_hbox.addWidget(QLabel("Match Type:"))
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems([
            "Partial match (contains)",
            "Exact match",
            "Starts with",
            "Ends with",
            "Regular expression match"
        ])
        match_hbox.addWidget(self.match_type_combo)
        match_hbox.addStretch()
        search_layout.addLayout(match_hbox)
        
        self.main_layout.addWidget(search_group)
        
    def _create_options_section(self):
        """Create the additional options section"""
        options_group = QGroupBox("Search Options")
        options_layout = QVBoxLayout(options_group)
        
        # Match options
        match_options_layout = QHBoxLayout()
        self.match_case_checkbox = QCheckBox("Match case")
        self.match_case_checkbox.setChecked(False)
        match_options_layout.addWidget(self.match_case_checkbox)
        
        self.whole_word_checkbox = QCheckBox("Whole word only")
        self.whole_word_checkbox.setChecked(False)
        match_options_layout.addWidget(self.whole_word_checkbox)
        
        match_options_layout.addStretch()
        options_layout.addLayout(match_options_layout)
        
        # Additional options
        extra_options_layout = QHBoxLayout()
        # البحث دائماً في جميع الأعمدة؛ إزالة مربع الاختيار من الواجهة
        self.export_results_checkbox = QCheckBox("Export results to file")
        self.export_results_checkbox.setChecked(False)
        extra_options_layout.addWidget(self.export_results_checkbox)
        
        extra_options_layout.addStretch()
        options_layout.addLayout(extra_options_layout)
        
        self.main_layout.addWidget(options_group)
        
    # [تمت الإزالة] قسم اختيار الأعمدة وكل أزراره، ليصبح البحث دائماً في كل الأعمدة
        
    def _create_buttons_section(self):
        """Create the buttons section"""
        button_layout = QHBoxLayout()
        
        # Search buttons
        self.search_btn = QPushButton("Search")
        self.search_btn.setDefault(True)
        self.search_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.search_btn)
        
        self.clear_filter_btn = QPushButton("Clear Filter")
        self.clear_filter_btn.clicked.connect(self._clear_filter)
        button_layout.addWidget(self.clear_filter_btn)
        
        button_layout.addStretch()
        
        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.main_layout.addLayout(button_layout)
        
    def _on_match_type_changed(self, text):
        """Update options based on match type"""
        is_regex = "Regular expression" in text
        self.whole_word_checkbox.setEnabled(not is_regex)
        if is_regex:
            self.whole_word_checkbox.setChecked(False)
            
    # [تمت الإزالة] لم يعد هناك تبديل لإظهار/إخفاء قسم الأعمدة
        
    # [تمت الإزالة] أزرار اختيار الأعمدة لم تعد مطلوبة
                
    def _clear_filter(self):
        """Clear the current filter"""
        self.find_text_edit.clear()
        self.accept()  # Close the dialog with a clear filter signal
        
    def get_search_settings(self):
        """إرجاع إعدادات البحث مع تفعيل البحث في جميع الأعمدة دائماً"""
        settings = {
            'text': self.find_text_edit.text().strip(),
            'match_type': self.match_type_combo.currentText(),
            'match_case': self.match_case_checkbox.isChecked(),
            'whole_word': self.whole_word_checkbox.isChecked(),
            'search_all_columns': True,  # دائماً
            'export_results': self.export_results_checkbox.isChecked(),
            'selected_columns': []       # فارغ دائماً لأننا نبحث في الكل
        }
        return settings

class PannableGraphicsView(QGraphicsView):
    """A QGraphicsView that supports panning (with ScrollHandDrag) and zooming."""
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Use Qt's built-in panning mechanism
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMouseTracking(True) # Required for hover events to show tooltips

    def wheelEvent(self, event):
        """Zoom in/out with the mouse wheel, with clamping to prevent extreme zoom levels."""
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor

        # Get the current scale factor, use abs() to handle potential flipped views
        current_scale = abs(self.transform().m11())

        # Define zoom limits
        min_scale = 0.05
        max_scale = 100.0

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        if event.angleDelta().y() > 0:
            # Zoom In
            if current_scale * zoom_in_factor < max_scale:
                self.scale(zoom_in_factor, zoom_in_factor)
        else:
            # Zoom Out
            if current_scale * zoom_out_factor > min_scale:
                self.scale(zoom_out_factor, zoom_out_factor)

class DeveloperDialog(QDialog):
    """
    نافذة المطوّر - نمط عصري ملوّن:
    - عناوين بارزة
    - أيقونات لكل قسم
    - أزرار باللون الأساسي (مستخرج من أيقونة التطبيق)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("نافذة المطوّر")
        self.setModal(True)
        self.setMinimumSize(640, 480)

        self.brand_color = self._extract_brand_color()  # لون أساسي
        self.accent_color = self.brand_color
        self._init_ui()
        self._apply_modern_styles()

    def _extract_brand_color(self):
        # محاولة استخراج اللون الأساسي من أيقونة التطبيق
        try:
            # Corrected path handling
            icon_path = os.path.join(utils.ICONS_DIR, "app_icon.png")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(utils.ICONS_DIR, "app_icon.ico")
            pix = QPixmap(icon_path)
            if not pix.isNull():
                img = pix.toImage()
                # أخذ بكسل من المركز كتمثيل تقريبي
                x = max(0, img.width() // 2)
                y = max(0, img.height() // 2)
                col = QColor(img.pixel(x, y))
                # ضمان سطوع/تشبع مقبولين
                if col.isValid():
                    return col
        except Exception:
            pass
        # لون افتراضي في حال الفشل
        return QColor("#0d6efd")

    def _section_header(self, text, icon_name=None):
        header = QWidget()
        h = QHBoxLayout(header)
        h.setContentsMargins(0, 0, 0, 0)
        if icon_name:
            h.addWidget(QLabel(pixmap=utils.get_icon(icon_name, size=20).pixmap(20, 20)))
        lbl = QLabel(text)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        lbl.setFont(font)
        h.addWidget(lbl)
        h.addStretch()
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(2)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(header)
        container_layout.addWidget(line)
        return container

    def _primary_button(self, text):
        btn = QPushButton(text)
        btn.setProperty("class", "primary")
        return btn

    def _icon_label_row(self, icon, text):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(utils.get_icon(icon, size=18).pixmap(18, 18))
        h.addWidget(icon_lbl)
        h.addWidget(QLabel(text))
        h.addStretch()
        return row

    def _apply_modern_styles(self):
        # تطبيق نمط حديث ملوّن مستند إلى اللون المستخرج
        col = self.accent_color
        r, g, b = col.red(), col.green(), col.blue()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #f7f9fc;
            }}
            QLabel {{
                color: #223042;
            }}
            QGroupBox {{
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 8px;
                margin-top: 12px;
                background: #ffffff;
            }}
            QGroupBox:title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: rgb({r},{g},{b});
                font-weight: 600;
            }}
            QPushButton {{
                border: 1px solid rgba(0,0,0,0.15);
                border-radius: 6px;
                padding: 6px 12px;
                background: #ffffff;
            }}
            QPushButton[class="primary"] {{
                background: rgb({r},{g},{b});
                color: white;
                border: none;
            }}
            QPushButton[class="primary"]:hover {{
                filter: brightness(1.05);
            }}
            QFrame[role="separator"] {{
                background: rgba(0,0,0,0.08);
                height: 1px;
            }}
        """)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # رأس النافذة
        header = QWidget()
        h = QHBoxLayout(header)
        h.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(utils.get_icon("settings_icon.png", size=28).pixmap(28, 28))
        title = QLabel("لوحة المطوّر")
        tfont = QFont(); tfont.setPointSize(13); tfont.setBold(True)
        title.setFont(tfont)
        title.setStyleSheet(f"color: {self.accent_color.name()};")
        h.addWidget(icon_lbl)
        h.addWidget(title)
        h.addStretch()

        root.addWidget(header)

        # قسم معلومات التطبيق/النظام
        info_group = QGroupBox("معلومات")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(6)
        # صفوف معلومات مختصرة مع أيقونات
        info_layout.addWidget(self._icon_label_row("info_icon.png", f"إصدار بايثون: {sys.version.split(' ')[0]}"))
        try:
            import PySide6
            info_layout.addWidget(self._icon_label_row("info_icon.png", f"إصدار PySide6: {PySide6.__version__}"))
        except Exception:
            info_layout.addWidget(self._icon_label_row("info_icon.png", "إصدار PySide6: غير متاح"))
        info_layout.addWidget(self._icon_label_row("info_icon.png", f"النظام: {os.name}"))
        info_layout.addWidget(self._icon_label_row("info_icon.png", f"المجلد الحالي: {os.getcwd()}"))

        # أزرار إجراءات أساسية
        actions_row = QWidget()
        ah = QHBoxLayout(actions_row); ah.setContentsMargins(0, 0, 0, 0)
        btn_copy_diag = self._primary_button("نسخ التشخيص")
        btn_open_settings = self._primary_button("فتح مجلد الإعدادات")
        btn_open_logs = QPushButton("فتح مجلد السجلات")
        ah.addWidget(btn_copy_diag); ah.addWidget(btn_open_settings); ah.addWidget(btn_open_logs); ah.addStretch()
        info_layout.addWidget(actions_row)

        root.addWidget(info_group)

        # قسم الواجهة والألوان
        ui_group = QGroupBox("المظهر")
        ui_layout = QVBoxLayout(ui_group)
        ui_layout.setSpacing(6)
        ui_layout.addWidget(self._icon_label_row("color_icon.png", f"اللون الأساسي: {self.accent_color.name()}"))
        btn_accent_preview = self._primary_button("معاينة تباينات اللون")
        ui_layout.addWidget(btn_accent_preview)
        root.addWidget(ui_group)

        # زر إغلاق
        footer = QWidget()
        fh = QHBoxLayout(footer); fh.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.close)
        fh.addWidget(close_btn)
        root.addWidget(footer)

        # ربط الأزرار
        btn_copy_diag.clicked.connect(self._copy_diagnostics)
        btn_open_settings.clicked.connect(self._open_settings_folder)
        btn_open_logs.clicked.connect(self._open_logs_folder)
        btn_accent_preview.clicked.connect(self._preview_accent)

    def _copy_diagnostics(self):
        try:
            import platform
            text = []
            text.append(f"Python: {sys.version}")
            try:
                import PySide6
                text.append(f"PySide6: {PySide6.__version__}")
            except Exception:
                text.append("PySide6: N/A")
            text.append(f"OS: {platform.platform()}")
            text.append(f"CWD: {os.getcwd()}")
            cb = QApplication.clipboard()
            cb.setText("\n".join(text))
            QMessageBox.information(self, "تم النسخ", "تم نسخ معلومات التشخيص إلى الحافظة.")
        except Exception as e:
            QMessageBox.warning(self, "خطأ", f"تعذر نسخ المعلومات:\n{e}")

    def _open_folder_in_explorer(self, folder_name):
        """Opens a specified folder in the system's file explorer."""
        try:
            # Use BASE_DIR from utils which is correctly set for bundled/dev environments
            folder_path = os.path.join(utils.BASE_DIR, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            
            # Cross-platform way to open a folder
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin": # macOS
                subprocess.run(["open", folder_path], check=True)
            else: # linux
                subprocess.run(["xdg-open", folder_path], check=True)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open the {folder_name} folder:\n{e}")

    def _open_settings_folder(self):
        self._open_folder_in_explorer("settings")

    def _open_logs_folder(self):
        self._open_folder_in_explorer("logs")

    def _preview_accent(self):
        # نافذة صغيرة لعرض تدرجات اللون الأساسي
        dlg = QDialog(self)
        dlg.setWindowTitle("تباينات اللون الأساسي")
        lay = QVBoxLayout(dlg)
        for i in [0.9, 1.0, 1.1, 1.2]:
            shade = QColor(self.accent_color)
            # تعديل طفيف للسطوع
            r = min(255, int(shade.red() * i))
            g = min(255, int(shade.green() * i))
            b = min(255, int(shade.blue() * i))
            swatch = QWidget()
            swatch.setStyleSheet(f"background: rgb({r},{g},{b}); border-radius: 6px;")
            swatch.setMinimumHeight(28)
            lay.addWidget(swatch)
        btn = QPushButton("إغلاق"); btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

class PreviewDialog(QDialog):
    """A dialog to display a 2D graphical preview of the survey data with pan, zoom, and hover info."""
    def __init__(self, parent, data_df):
        super().__init__(parent)
        self.setWindowTitle("2D Data Preview")
        self.setMinimumSize(800, 600)
        
        self.data_df = data_df
        self.has_drawn = False # Flag to ensure initial draw happens only once

        # Default colors
        self.point_color = QColor(Qt.GlobalColor.yellow)
        self.text_color = QColor(Qt.GlobalColor.yellow)
        self.background_color = QColor(Qt.GlobalColor.black)
        
        # Correctly initialize the layout for the dialog
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        
        # --- Color Customization Buttons ---
        color_button_layout = QHBoxLayout()
        
        self.point_color_btn = QPushButton("Point Color")
        self.point_color_btn.clicked.connect(lambda: self.pick_color('point'))
        color_button_layout.addWidget(self.point_color_btn)

        self.text_color_btn = QPushButton("Text Color")
        self.text_color_btn.clicked.connect(lambda: self.pick_color('text'))
        color_button_layout.addWidget(self.text_color_btn)

        self.bg_color_btn = QPushButton("Background Color")
        self.bg_color_btn.clicked.connect(lambda: self.pick_color('background'))
        color_button_layout.addWidget(self.bg_color_btn)
        
        color_button_layout.addStretch()
        layout.addLayout(color_button_layout)
        
        self.scene = QGraphicsScene(self)
        self.graphics_view = PannableGraphicsView(self.scene, self)
        
        layout.addWidget(self.graphics_view)
        
        self.status_label = QLabel("Ready. Scroll to zoom, drag to pan, hover over points for details.")
        layout.addWidget(self.status_label)
        
        # self.draw_data() is now called from showEvent to prevent painting before the widget is ready.

    def showEvent(self, event):
        """Override showEvent to draw data after the dialog is shown for the first time."""
        super().showEvent(event)
        if not self.has_drawn:
            # Use a single shot timer to ensure the event loop has processed the show event
            # before we attempt to draw and fit the view.
            QTimer.singleShot(50, self.initial_draw)

    def initial_draw(self):
        """Performs the initial drawing and fitting of the data."""
        if not self.has_drawn:
            self.draw_data()
            self.has_drawn = True

    def pick_color(self, target):
        from PySide6.QtWidgets import QColorDialog
        
        initial_color = getattr(self, f"{target}_color")
        new_color = QColorDialog.getColor(initial_color, self, f"Select {target.title()} Color")
        
        if new_color.isValid():
            setattr(self, f"{target}_color", new_color)
            self.draw_data() # Redraw with the new color

    def draw_data(self):
        if self.data_df.empty:
            self.status_label.setText("No data to display.")
            return

        self.scene.clear()
        
        eastings = self.data_df.get(dp.COL_E)
        northings = self.data_df.get(dp.COL_N)

        if eastings is None or northings is None or eastings.isnull().all() or northings.isnull().all():
            self.status_label.setText("Easting or Northing columns not found or contain no valid data.")
            return

        min_e, max_e = eastings.min(), eastings.max()
        min_n, max_n = northings.min(), northings.max()

        if min_e == max_e: min_e -= 1; max_e += 1
        if min_n == max_n: min_n -= 1; max_n += 1

        padding = 20
        self.scene.setSceneRect(min_e - padding, -max_n - padding, (max_e - min_e) + 2 * padding, (max_n - min_n) + 2 * padding)
        
        point_size = 5
        
        self.scene.setBackgroundBrush(self.background_color)
        for index, row in self.data_df.iterrows():
            try:
                e = float(row.get(dp.COL_E, 0))
                n = float(row.get(dp.COL_N, 0))
            except (ValueError, TypeError):
                continue # Skip points with non-numeric coordinates

            point = QGraphicsEllipseItem(e - point_size / 2, -n - point_size / 2, point_size, point_size)
            point.setBrush(self.point_color)
            point.setPen(QColor(Qt.GlobalColor.transparent))
            point.setAcceptHoverEvents(True) # Enable hover events for the point
            
            # Store all data in the item for the tooltip
            tooltip_text = ""
            for col, val in row.items():
                tooltip_text += f"<b>{col}:</b> {val}<br>"
            point.setToolTip(tooltip_text)
            
            self.scene.addItem(point)
            
            pt_num = str(row.get(dp.COL_PT, ''))
            if pt_num:
                label = QGraphicsSimpleTextItem(pt_num)
                label.setBrush(self.text_color)
                # Position the label relative to the point, considering scene's inverted Y
                label.setPos(e + point_size / 2, -n - label.boundingRect().height())
                self.scene.addItem(label)

        self.graphics_view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.status_label.setText(f"Displayed {len(self.data_df)} points. Scroll to zoom, drag to pan.")