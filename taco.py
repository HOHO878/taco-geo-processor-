import sys
import pandas as pd
import logging
import os
import re
import datetime
import csv
from pathlib import Path
import json
import io
import gc
import openpyxl
import shutil
import subprocess
import tempfile
from typing import Optional
from collections import OrderedDict

from taco_geo_processor.core import config
from taco_geo_processor.processing import data_processing as dp
try:
    from taco_geo_processor.utils.arabic_text_helper import fix_arabic, initialize_arabic_support
except ImportError:
    # Fallback implementation if the module is not available
    def fix_arabic(text):
        """Fallback function for fixing Arabic text."""
        return text if text else ""
    
    def initialize_arabic_support():
        """Fallback function for initializing Arabic support."""
        return True

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton,
    QFileDialog, QComboBox, QLineEdit, QHBoxLayout, QCheckBox,
    QFrame, QGridLayout, QGroupBox, QMessageBox, QTableView, QHeaderView,
    QDialog, QDialogButtonBox, QScrollArea, QSizePolicy, QColorDialog,
    QInputDialog, QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsLineItem, QGraphicsRectItem, QGraphicsSimpleTextItem, QRadioButton, QButtonGroup,
    QAbstractItemView, QProgressBar, QProgressDialog
)
from PySide6.QtGui import (
    QIcon, QFont, QStandardItem, QClipboard, QColor, QPixmap, QBrush, QPen, QKeySequence, QPainter, QDesktopServices, QAction
)
from PySide6.QtCore import (
    Qt, QSettings, QTimer, QSize, QModelIndex, QRectF, QSortFilterProxyModel, QUrl, QRegularExpression,
    QItemSelectionModel, QItemSelection, QThread, Signal, QObject, QAbstractTableModel, Slot
)

from taco_geo_processor.data.models import HistoryManager, EfficientTableModel, CustomSortFilterProxyModel
from taco_geo_processor.ui.dialogs import SettingsDialogBase, DXFSettingsDialog, KMLSettingsDialog, FindDialog, PreviewDialog
from taco_geo_processor.utils.utils import get_icon, safe_float, TXT_DELIMITER_MAP
from taco_geo_processor.core.workers import Worker, ExportAllWorker
import pyproj

# Enable network access for PROJ to download grid files
os.environ['PROJ_NETWORK'] = 'ON'

# Set the data directory to the user's data directory
try:
    # Try the older pyproj API first
    if hasattr(pyproj, 'datadir') and hasattr(pyproj.datadir, 'set_data_dir'):  # type: ignore
        pyproj.datadir.set_data_dir(pyproj.datadir.get_user_data_dir())  # type: ignore
        logging.info(f"pyproj data directory set to: {pyproj.datadir.get_data_dir()}")  # type: ignore
    else:
        # For newer versions of pyproj, try importing datadir
        try:
            from pyproj import datadir  # type: ignore
            if hasattr(datadir, 'set_data_dir') and hasattr(datadir, 'get_user_data_dir'):
                datadir.set_data_dir(datadir.get_user_data_dir())  # type: ignore
                logging.info(f"pyproj data directory set to: {datadir.get_data_dir()}")
        except ImportError:
            logging.info("pyproj datadir module not available")
except (AttributeError, ImportError) as e:
    logging.warning(f"Could not set pyproj data directory (this is usually OK): {e}")
except Exception as e:
    logging.error(f"Failed to set pyproj data directory: {e}")


class MainWindow(QMainWindow):
    """
    The main window of the application, containing the user interface and controls.
    """
    def __init__(self):
        super().__init__()
        
        # تهيئة دعم العربية
        try:
            initialize_arabic_support()
        except Exception as e:
            logging.warning(f"فشل في تهيئة دعم العربية: {e}")
        
        self.setWindowTitle(config.UI_CFG['window_title'].format(app_title=config.APP_NAME, app_version=config.APP_VERSION))
        self.setMinimumSize(config.UI_CFG['min_window_width'], config.UI_CFG['min_window_height'])
        self.settings_manager = QSettings("MyCompany", "SurveyConverter")
        self.current_file_path = None
        self.kml_settings = config.PROFILE_CFG.get('kml', {})
        self.dxf_settings = config.PROFILE_CFG.get('dxf', {})
        self.worker_thread = None
        self.history_manager = HistoryManager()
        self.table_model = EfficientTableModel()
        self.proxy_model = CustomSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.init_ui()
        self.load_window_settings()
        # Center on first run (no saved geometry)
        if not self.settings_manager.value("geometry"):
            screen = self.screen().availableGeometry() if hasattr(self, 'screen') and self.screen() else self.geometry()
            size = self.size()
            x = (screen.width() - size.width()) // 2
            y = (screen.height() - size.height()) // 2
            self.move(max(0, x), max(0, y))
        self._verify_models_connection()
        self._verify_table_display()
        QTimer.singleShot(1000, self._verify_table_display)
        QTimer.singleShot(3000, self._verify_table_display)
        QTimer.singleShot(5000, self._verify_table_display)
        self.update_status(config.UI_CFG['status_ready'])

    def _verify_models_connection(self):
        """Verify that the models are connected correctly"""
        try:
            # Verify that the proxy model is connected to the source model
            if self.proxy_model.sourceModel() != self.table_model:
                logging.error("Proxy model is not connected to table model!")
                self.proxy_model.setSourceModel(self.table_model)
                logging.info("Proxy model reconnected to table model")
            
            # Verify that the table is using the proxy model
            if self.table_view.model() != self.proxy_model:
                logging.error("Table view is not using proxy model!")
                self.table_view.setModel(self.proxy_model)
                logging.info("Table view reconnected to proxy model")
            
            logging.info("Models connection verified successfully")
            
        except Exception as e:
            logging.error(f"Error verifying models connection: {e}")

    def _verify_table_display(self):
        """Verify that the table displays data correctly"""
        try:
            # Check the number of rows and columns
            rows = self.table_model.rowCount()
            cols = self.table_model.columnCount()
            logging.info(f"Table model has {rows} rows and {cols} columns")

            # Check that the proxy model returns the same numbers
            proxy_rows = self.proxy_model.rowCount()
            proxy_cols = self.proxy_model.columnCount()
            logging.info(f"Proxy model has {proxy_rows} rows and {proxy_cols} columns")

            # Check that the table displays data
            if rows > 0 and cols > 0:
                # Try to access the first cell
                first_cell = self.table_model.data(self.table_model.index(0, 0))
                logging.info(f"First cell content: {first_cell}")

                # Check column headers
                headers = []
                for i in range(min(cols, 6)):  # First 6 columns only
                    header = self.table_model.headerData(i, Qt.Orientation.Horizontal)
                    headers.append(header)
                logging.info(f"Column headers: {headers}")

            logging.info("Table display verification completed")

        except Exception as e:
            logging.error(f"Error verifying table display: {e}")

    def init_ui(self):
        """Creates and places all user interface elements."""

        
        # Setup keyboard shortcuts
        self.setup_shortcuts()

        main_layout = QVBoxLayout(); main_layout.setContentsMargins(10,10,10,10); main_layout.setSpacing(10)
        
        # Top controls moved into tabs to avoid confusion
        # Tab 1: Import/Export
        data_tab_layout = QHBoxLayout(); data_tab_layout.setContentsMargins(10,10,10,10); data_tab_layout.setSpacing(10)
        self.import_group_box = QGroupBox(config.UI_CFG['import_group_title'])
        self.create_import_controls(self.import_group_box)
        data_tab_layout.addWidget(self.import_group_box)
        self.export_group_box = QGroupBox(config.UI_CFG['export_group_title'])
        self.create_export_controls(self.export_group_box)
        data_tab_layout.addWidget(self.export_group_box)
        data_tab_widget = QWidget(); data_tab_widget.setLayout(data_tab_layout)

        # Tabs
        from PySide6.QtWidgets import QTabWidget
        top_tabs = QTabWidget()
        top_tabs.addTab(data_tab_widget, "الاستيراد والتصدير")

        table_widget = QWidget()
        self.create_table(table_widget)
        
        bottom_controls_widget = QWidget()
        self.create_bottom_controls(bottom_controls_widget)
        
        main_layout.addWidget(top_tabs, 0)
        main_layout.addWidget(table_widget, 1)
        main_layout.addWidget(bottom_controls_widget, 0)
        
        central_widget = QWidget(); central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    

    def setup_shortcuts(self):
        """Set up keyboard shortcuts for the application."""
        f1_shortcut = QKeySequence(Qt.Key.Key_F1)
        f1_action = QAction(config.UI_CFG['action_dev_info'], self)
        f1_action.setShortcut(f1_shortcut)
        f1_action.triggered.connect(self.show_info)
        self.addAction(f1_action)
        
        ctrl_f_shortcut = QKeySequence("Ctrl+F")
        ctrl_f_action = QAction(config.UI_CFG['action_find'], self)
        ctrl_f_action.setShortcut(ctrl_f_shortcut)
        ctrl_f_action.triggered.connect(self.show_find_dialog)
        self.addAction(ctrl_f_action)
        
        ctrl_c_shortcut = QKeySequence("Ctrl+C")
        ctrl_c_action = QAction(config.UI_CFG['action_copy'], self)
        ctrl_c_action.setShortcut(ctrl_c_shortcut)
        ctrl_c_action.triggered.connect(self.copy_selected_cells)
        self.addAction(ctrl_c_action)
        
        ctrl_v_shortcut = QKeySequence("Ctrl+V")
        ctrl_v_action = QAction(config.UI_CFG['action_paste'], self)
        ctrl_v_action.setShortcut(ctrl_v_shortcut)
        ctrl_v_action.triggered.connect(self.paste_data_from_clipboard)
        self.addAction(ctrl_v_action)
        
        ctrl_z_shortcut = QKeySequence("Ctrl+Z")
        ctrl_z_action = QAction(config.UI_CFG['action_undo'], self)
        ctrl_z_action.setShortcut(ctrl_z_shortcut)
        ctrl_z_action.triggered.connect(self.undo)
        self.addAction(ctrl_z_action)
        
        ctrl_y_shortcut = QKeySequence("Ctrl+Y")
        ctrl_y_action = QAction(config.UI_CFG['action_redo'], self)
        ctrl_y_action.setShortcut(ctrl_y_shortcut)
        ctrl_y_action.triggered.connect(self.redo)
        self.addAction(ctrl_y_action)

    def create_button_with_icon(self, parent, icon_name, text, command, tooltip=None, icon_size=config.DEFAULT_ICON_SIZE, text_visible=True):
        """
        Helper function to create a button with an icon, optional text, command, and tooltip.
        """
        button = QPushButton(parent)
        button.setIcon(get_icon(f"{icon_name}_icon.png", size=icon_size))
        button.setIconSize(QSize(icon_size, icon_size))
        if text_visible: button.setText(text)
        else: button.setFixedSize(icon_size + 10, icon_size + 10); button.setText("")
        if tooltip: button.setToolTip(tooltip)
        button.clicked.connect(command)
        return button

    def create_import_controls(self, import_group_box):
        """Creates the import controls (buttons and dropdowns)."""
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(10, 20, 10, 10)
        group_layout.setSpacing(8)
        formats_grid_layout = QGridLayout()
        formats_grid_layout.setSpacing(5)
        
        formats = [
            ('SDR33', 'sdr', config.UI_CFG['tooltip_sdr_import'], None),
            ('GSI', 'gsi', config.UI_CFG['tooltip_gsi_import'], None),
            ('DXF', 'dxf', config.UI_CFG['tooltip_dxf_import'], None),
            ('KML', 'kml', config.UI_CFG['tooltip_kml_import'], None),
            ('TXT', 'txt', config.UI_CFG['tooltip_txt_import'], 'txt_import_dropdown'),
            ('CSV', 'csv', config.UI_CFG['tooltip_csv_import'], 'csv_import_dropdown'),
            ('Excel', 'excel', config.UI_CFG['tooltip_excel_import'], 'excel_import_dropdown'),
        ]
        
        current_row = 0
        for fmt, icon_key, tip, dropdown_attr_name in formats:
            btn = self.create_button_with_icon(
                import_group_box, icon_key, fmt,
                lambda checked, f=fmt, da_name=dropdown_attr_name: self.import_data_dialog(f, getattr(self, da_name, None) if da_name else None),
                tooltip=tip, icon_size=config.DEFAULT_ICON_SIZE, text_visible=False
            )
            formats_grid_layout.addWidget(btn, current_row, 0)
            
            if dropdown_attr_name:
                dropdown = self._create_format_dropdown(import_group_box, dropdown_attr_name, is_import=True)
                formats_grid_layout.addWidget(dropdown, current_row, 1, 1, 2)
            elif fmt in ['SDR33', 'GSI', 'DXF', 'DWG', 'KML']:
                info_label = QLabel(f"{fmt}")
                formats_grid_layout.addWidget(info_label, current_row, 1, 1, 2, Qt.AlignmentFlag.AlignLeft)  # type: ignore[attr-defined]
            current_row += 1
            
        group_layout.addLayout(formats_grid_layout)
        
        # Add import options
        import_options_layout = QHBoxLayout()
        
        # Import mode selection button
        self.import_mode_label = QLabel(config.UI_CFG['import_mode_label'])
        import_options_layout.addWidget(self.import_mode_label)
        
        self.import_mode_combo = QComboBox()
        self.import_mode_combo.addItems([config.UI_CFG['import_mode_replace'], config.UI_CFG['import_mode_append']])
        self.import_mode_combo.setToolTip(config.UI_CFG['import_mode_tooltip'])
        self.import_mode_combo.setCurrentText(config.UI_CFG['import_mode_replace'])
        import_options_layout.addWidget(self.import_mode_combo)
        
        import_options_layout.addStretch(1)
        group_layout.addLayout(import_options_layout)
        
        group_layout.addStretch(1)
        import_group_box.setLayout(group_layout)

    def create_export_controls(self, export_group_box):
        """Creates the export controls (buttons, dropdowns, and settings)."""
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(10, 20, 10, 10)
        group_layout.setSpacing(8)

        export_all_btn = self.create_button_with_icon(
            export_group_box, "all_formats", config.UI_CFG['export_all_button_text'], self.export_all_formats_dialog,
            tooltip=config.UI_CFG['export_all_tooltip'],
            icon_size=config.DEFAULT_ICON_SIZE, text_visible=False
        )
        group_layout.addWidget(export_all_btn)

        line_sep = QFrame(); line_sep.setFrameShape(QFrame.Shape.HLine); line_sep.setFrameShadow(QFrame.Shadow.Sunken)
        group_layout.addWidget(line_sep)

        formats_grid_layout = QGridLayout(); formats_grid_layout.setSpacing(5)
        formats = [
            ('SDR33', 'sdr', config.UI_CFG['tooltip_sdr_export'], None),
            ('GSI', 'gsi', config.UI_CFG['tooltip_gsi_export'], None),
            ('DXF', 'dxf', config.UI_CFG['tooltip_dxf_export'], None),
            ('KML', 'kml', config.UI_CFG['tooltip_kml_export'], None),
            ('TXT', 'txt', config.UI_CFG['tooltip_txt_export'], 'txt_export_dropdown'),
            ('CSV', 'csv', config.UI_CFG['tooltip_csv_export'], 'csv_export_dropdown'),
            ('Excel', 'excel', config.UI_CFG['tooltip_excel_export'], 'excel_export_dropdown'),
        ]

        current_row = 0
        for fmt, icon_key, tip, dropdown_attr_name in formats:
            btn = self.create_button_with_icon(
                export_group_box, icon_key, fmt,
                lambda checked, f=fmt, da_name=dropdown_attr_name: self.export_data_dialog(f, getattr(self, da_name, None) if da_name else None),
                tooltip=tip, icon_size=config.DEFAULT_ICON_SIZE, text_visible=False
            )
            formats_grid_layout.addWidget(btn, current_row, 0)

            col_offset = 1

            # DXF settings button
            if fmt == 'DXF':
                dxf_settings_btn = self.create_button_with_icon(
                    export_group_box, "settings", "", self.get_dxf_export_settings,
                    tooltip=config.UI_CFG['tooltip_dxf_settings'], icon_size=20, text_visible=False
                )
                formats_grid_layout.addWidget(dxf_settings_btn, current_row, col_offset)
                col_offset += 1

            # KML settings button only (no dropdown)
            if fmt == 'KML':
                kml_settings_btn = self.create_button_with_icon(
                    export_group_box, "settings", "", self.get_kml_export_settings,
                    tooltip=config.UI_CFG['tooltip_kml_settings'], icon_size=20, text_visible=False
                )
                formats_grid_layout.addWidget(kml_settings_btn, current_row, col_offset)
                col_offset += 1

            if fmt == 'SDR33':
                self.sdr_coord_group = QButtonGroup(self)
                self.sdr_en_radio = QRadioButton("N-E")
                self.sdr_en_radio.setToolTip("تصدير الإحداثيات بترتيب شماليات-شرقيات (Northing, Easting)")
                self.sdr_en_radio.setChecked(True)
                self.sdr_ne_radio = QRadioButton("E-N")
                self.sdr_ne_radio.setToolTip("تصدير الإحداثيات بترتيب شرقيات-شماليات (Easting, Northing)")
                
                self.sdr_coord_group.addButton(self.sdr_en_radio, 1)
                self.sdr_coord_group.addButton(self.sdr_ne_radio, 2)

                sdr_coord_layout = QHBoxLayout()
                sdr_coord_layout.addWidget(self.sdr_en_radio)
                sdr_coord_layout.addWidget(self.sdr_ne_radio)
                
                formats_grid_layout.addLayout(sdr_coord_layout, current_row, col_offset); col_offset += 1

            if dropdown_attr_name:
                dropdown = self._create_format_dropdown(export_group_box, dropdown_attr_name, is_import=False)
                formats_grid_layout.addWidget(dropdown, current_row, col_offset, 1, 1); col_offset +=1

                if fmt in ['TXT', 'CSV']:
                    delimiter_dropdown = QComboBox()
                    delimiter_dropdown.addItems(config.TXT_DELIMITERS)
                    delimiter_dropdown.setToolTip(config.UI_CFG['tooltip_delimiter_select'])
                    delimiter_dropdown.setCurrentText('Auto-detect' if fmt == 'CSV' else 'Tab (\t)')
                    formats_grid_layout.addWidget(QLabel("Delimiter:"), current_row, col_offset)
                    formats_grid_layout.addWidget(delimiter_dropdown, current_row, col_offset+1)
                    setattr(self, f"{fmt.lower()}_delimiter_dropdown", delimiter_dropdown)
                    col_offset += 2
            elif fmt in ['GSI'] and fmt not in ['DXF', 'KML']:
                info_label = QLabel(f"{fmt}")
                formats_grid_layout.addWidget(info_label, current_row, col_offset, 1, 1, Qt.AlignmentFlag.AlignLeft); col_offset += 1

            current_row += 1

        group_layout.addLayout(formats_grid_layout)
        export_group_box.setLayout(group_layout)

    # Coordinate transformation UI and helpers removed per request: functions and widgets
    # previously implemented here (CRS selectors, transform button, helpers) were removed to
    # delete the "تحويل الإحداثيات" tab and related behavior.

    def _create_format_dropdown(self, parent, attribute_name, is_import=True):
        """
        Creates a dropdown for column order options.
        is_import: True if for import (includes Auto-detect), False if for export (includes All Columns).
        """
        # Common column order presets
        common_orders = [
            f"{dp.COL_PT},{dp.COL_E},{dp.COL_N},{dp.COL_Z},{dp.COL_CODE},{dp.COL_DESC}",
            f"{dp.COL_PT},{dp.COL_N},{dp.COL_E},{dp.COL_Z},{dp.COL_CODE},{dp.COL_DESC}",
            f"{dp.COL_E},{dp.COL_N},{dp.COL_Z},{dp.COL_PT},{dp.COL_CODE},{dp.COL_DESC}",
            "Point,Easting,Northing,Elevation,Code",
            "Point,Northing,Easting,Elevation,Code",
            "P,X,Y,Z,CD",
            "P,Y,X,Z,CD",
            f"{dp.COL_PT},{dp.COL_E},{dp.COL_N},{dp.COL_Z},{dp.COL_CODE}",
            f"{dp.COL_PT},{dp.COL_E},{dp.COL_N},{dp.COL_Z}",
            f"{dp.COL_PT},{dp.COL_E},{dp.COL_N}",
            "ID,X,Y"
        ]
        # New default option
        default_order = f"{dp.COL_PT},{dp.COL_E},{dp.COL_N},{dp.COL_Z},{dp.COL_CODE},{dp.COL_DESC}"
        # Set options based on import vs. export
        options = ["Auto-detect Columns"] + common_orders if is_import else common_orders + ["All Columns (Original Order)"]
        # If the format is txt, csv, or excel, set the default to default_order
        dropdown = QComboBox(parent)
        dropdown.addItems(options)
        # Set the property name to identify the list type
        if attribute_name.lower() in ["txt_import_dropdown", "csv_import_dropdown", "excel_import_dropdown", "txt_export_dropdown", "csv_export_dropdown", "excel_export_dropdown"]:
            dropdown.setCurrentText(default_order)
        else:
            dropdown.setCurrentText("Auto-detect Columns" if is_import else common_orders[0])
        setattr(self, attribute_name, dropdown) # Store dropdown widget as attribute (e.g., self.txt_import_dropdown)
        return dropdown

    def create_table(self, parent_widget):
        """Creates and initializes the QTableView for displaying data."""
        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        
        self.table_view.setSortingEnabled(False)
        self.table_view.horizontalHeader().setSectionsMovable(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setEditTriggers(QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.AnyKeyPressed | QTableView.EditTrigger.SelectedClicked)
        
        layout = QVBoxLayout(); layout.setContentsMargins(0,0,0,0); layout.addWidget(self.table_view)
        parent_widget.setLayout(layout)

    

    def select_columns_by_header(self, visual_clicked_index):
        """Selects the cells of the column(s) whose header was clicked."""
        header = self.table_view.horizontalHeader()
        selected_visual_indices = [idx.column() for idx in header.selectionModel().selectedIndexes()]
        
        if not selected_visual_indices and visual_clicked_index != -1:
            selected_visual_indices = [visual_clicked_index]
        
        if not selected_visual_indices or visual_clicked_index == -1: return
        
        self.table_view.clearSelection()
        selection_model = self.table_view.selectionModel()
        
        for visual_col_idx in selected_visual_indices:
            proxy_col_idx = visual_col_idx
            start_index = self.proxy_model.index(0, proxy_col_idx)
            if self.proxy_model.rowCount() == 0:
                 self.update_status(config.UI_CFG['status_no_rows_to_select'])
                 return
            end_index = self.proxy_model.index(self.proxy_model.rowCount() - 1, proxy_col_idx)
            if start_index.isValid() and end_index.isValid():
                selection = QItemSelection(start_index, end_index)
                selection_model.select(selection, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Columns)
                
        selected_names = [self.proxy_model.headerData(idx, Qt.Orientation.Horizontal) for idx in selected_visual_indices]
        self.update_status(config.UI_CFG['status_selected_columns'].format(columns=', '.join(selected_names)))

    def delete_selected_columns_by_header(self, visual_clicked_index):
        """Deletes the selected columns from the DataFrame."""
        header = self.table_view.horizontalHeader()
        selected_visual_indices = sorted(list(set(idx.column() for idx in header.selectionModel().selectedIndexes())))
        
        if not selected_visual_indices and visual_clicked_index != -1:
            selected_visual_indices = [visual_clicked_index]
            
        if not selected_visual_indices or visual_clicked_index == -1:
            self.update_status(config.UI_CFG['no_columns_selected_status']); return
            
        column_names_to_delete = []
        for vis_idx in selected_visual_indices:
            col_name = self.proxy_model.headerData(vis_idx, Qt.Orientation.Horizontal)
            if col_name: column_names_to_delete.append(col_name)
        
        column_names_to_delete = [name for name in column_names_to_delete if name]
        if not column_names_to_delete:
            self.update_status("Could not identify columns to delete."); return
            
        reply = QMessageBox.question(self, config.UI_CFG['delete_columns_confirm_title'], config.UI_CFG['delete_columns_confirm_text'].format(columns=', '.join(column_names_to_delete)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            current_df = self.table_model.data_df().copy()
            existing_cols_to_drop = [col_name for col_name in column_names_to_delete if col_name in current_df.columns]
            if not existing_cols_to_drop:
                self.update_status(config.UI_CFG['delete_columns_not_found_status'].format(columns=', '.join(column_names_to_delete))); return
                
            updated_df = current_df.drop(columns=existing_cols_to_drop, errors='ignore')
            self.update_table_data(updated_df)
            self.update_status(config.UI_CFG['delete_columns_status'].format(columns=', '.join(existing_cols_to_drop)))
        else:
            self.update_status(config.UI_CFG['status_column_deletion_cancelled'])

    def update_table_data(self, data_df: pd.DataFrame):
        """Updates the data in the table and resets filters."""
        try:
            if not self.table_model.data_df().equals(data_df):
                self.history_manager.push(self.table_model.data_df())
                
            self.table_model.set_data_df(data_df)
            
            self.proxy_model.setFilterRegularExpression(QRegularExpression())
            self.proxy_model.setFilterByColumns([])
            self.proxy_model.invalidateFilter()
            
            if data_df is not None and not data_df.empty:
                self.update_status(f"Table updated: {len(data_df)} rows, {len(data_df.columns)} columns.")
                logging.info(f"Table updated with {len(data_df)} rows and {len(data_df.columns)} columns")
            else:
                self.update_status("Table cleared or no data loaded.")
                logging.info("Table cleared or no data loaded")
            
            self.update_undo_redo_actions()
            
        except Exception as e:
            logging.error(f"Error updating table data: {e}")
            self.update_status(f"Error updating data: {e}")

    def copy_selected_cells(self):
        """Copies the selected cells to the clipboard in tab-separated format."""
        selection_model = self.table_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            self.update_status(config.UI_CFG['no_cells_selected_copy_status']); return
            
        source_selection = self.proxy_model.mapSelectionToSource(selection_model.selection())
        if not source_selection.indexes(): return
        
        selected_rows = sorted(list(set(index.row() for index in source_selection.indexes())))
        selected_cols = sorted(list(set(index.column() for index in source_selection.indexes())))
        
        if not selected_rows or not selected_cols: return
        
        df_selection = self.table_model.data_df().iloc[selected_rows, selected_cols]
        
        output = io.StringIO()
        df_selection.to_csv(output, sep='\t', index=False, header=True)
        QApplication.clipboard().setText(output.getvalue())
        self.update_status(
            config.UI_CFG['copy_status'].format(
                rows=len(selected_rows),
                cols=len(selected_cols),
                columns=len(selected_cols)
            )
        )

    def cut_selected_cells(self):
        """Cuts the selected cells (copy then delete)."""
        selection_model = self.table_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            self.update_status(config.UI_CFG['no_cells_selected_cut_status']); return
            
        self.copy_selected_cells()
        self.delete_selected_rows()

    def paste_data_from_clipboard(self):
        """Pastes data from the clipboard into the selected cells or the beginning of the table."""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text: self.update_status(config.UI_CFG['clipboard_empty_status']); return
        
        try:
            paste_df = pd.read_csv(io.StringIO(text), sep='\t', header=0, dtype=str, escapechar='\\')
        except Exception:
            try:
                paste_df = pd.read_csv(io.StringIO(text), sep=',', header=0, dtype=str, escapechar='\\')
            except Exception as e:
                self.show_error(config.UI_CFG['clipboard_parse_error_title'], config.UI_CFG['clipboard_parse_error_text'].format(error=e)); return
                
        if paste_df.empty: self.update_status("Clipboard data is empty or invalid format."); return
        
        selected_indexes = self.table_view.selectionModel().selectedIndexes()
        start_row, start_col = 0, 0
        
        if selected_indexes:
            source_index = self.proxy_model.mapToSource(selected_indexes[0])
            start_row, start_col = source_index.row(), source_index.column()
            
        current_df = self.table_model.data_df().copy()
        
        required_rows = start_row + len(paste_df)
        required_cols = start_col + len(paste_df.columns)
        
        if required_cols > len(current_df.columns):
            for i in range(len(current_df.columns), required_cols):
                current_df[f'NewCol_{i+1}'] = pd.NA
        if required_rows > len(current_df):
            empty_rows_df = pd.DataFrame(index=range(len(current_df), required_rows), columns=current_df.columns)
            current_df = pd.concat([current_df, empty_rows_df], ignore_index=True)
            
        current_df.iloc[start_row : start_row + len(paste_df),
                        start_col : start_col + len(paste_df.columns)] = paste_df.iloc[:len(paste_df), :len(paste_df.columns)].values
                        
        self.update_table_data(current_df)
        self.update_status(
            config.UI_CFG['paste_status'].format(
                rows=len(paste_df),
                cols=len(paste_df.columns),
                columns=len(paste_df.columns),
                start_row=start_row + 1,
                start_col=start_col + 1,
            )
        )

    def create_bottom_controls(self, parent_widget):
        """Creates the controls at the bottom (status bar and clear button)."""
        layout = QHBoxLayout(); layout.setContentsMargins(5,5,5,5); parent_widget.setLayout(layout)

        layout.addStretch(1)
        
        self.status_label = QLabel(config.UI_CFG['status_ready']) # Label for status messages
        self.progress_bar = QProgressBar() # Progress bar for long operations
        self.progress_bar.setVisible(False); self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0,100); self.progress_bar.setValue(0)
        
        status_layout = QVBoxLayout() # Layout for status label and progress bar
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        layout.addLayout(status_layout, 1)
        
        button_layout = QHBoxLayout(); button_layout.setContentsMargins(0,0,0,0)
        button_widget = QWidget(); button_widget.setLayout(button_layout)
        
        find_btn = self.create_button_with_icon(button_widget, "search", "", self.show_find_dialog, tooltip=config.UI_CFG['tooltip_find_button'], text_visible=False)
        button_layout.addWidget(find_btn)
        
        show_all_btn = self.create_button_with_icon(button_widget, "settings", "", 
                                                   self.show_all_data,
                                                   tooltip=config.UI_CFG['tooltip_show_all_button'], text_visible=False)
        button_layout.addWidget(show_all_btn)
        
        clear_all_btn = self.create_button_with_icon(button_widget, "clear", "", 
                                                   self.clear_data,
                                                   tooltip=config.UI_CFG['tooltip_clear_all_button'], text_visible=False)
        button_layout.addWidget(clear_all_btn)
        
        info_btn = self.create_button_with_icon(button_widget, "info", "", 
                                               self.show_info,
                                               tooltip=config.UI_CFG['tooltip_info_button'], text_visible=False)
        button_layout.addWidget(info_btn)
        
        layout.addWidget(button_widget, 0)

    def set_ui_busy(self, busy, message=config.UI_CFG['status_processing']):
        """Disables or enables UI elements depending on the operation status."""
        self.import_group_box.setEnabled(not busy)
        self.export_group_box.setEnabled(not busy)
        self.table_view.setEnabled(not busy)
        
        if busy:
            self.progress_bar.setVisible(True)
            self.progress_bar.setFormat(message + " %p%")
            self.update_status(message, duration_ms=0)
        else:
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)

    @Slot(int, str)
    def handle_worker_progress(self, percentage, message):
        """Handler to receive progress updates from the worker thread."""
        self.progress_bar.setValue(percentage)
        self.progress_bar.setFormat(message + " %p%")
        self.status_label.setText(message)

    def load_window_settings(self):
        """Load window settings (size, position, state) from QSettings."""
        geometry = self.settings_manager.value("geometry")
        if geometry: self.restoreGeometry(geometry)
        state = self.settings_manager.value("windowState")
        if state: self.restoreState(state)
        logging.info("Window settings (geometry/state) loaded if available.")

    def save_window_settings(self):
        """Save window settings (size, position, state) to QSettings."""
        self.settings_manager.setValue("geometry", self.saveGeometry())
        self.settings_manager.setValue("windowState", self.saveState())
        logging.info("Window settings (geometry/state) saved.")

    def closeEvent(self, event):
        """Handle the window close event."""
        if (self.worker_thread is not None and self.worker_thread.isRunning()) or (hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None and self.export_all_worker_thread.isRunning()):
            reply = QMessageBox.question(self, config.UI_CFG['close_confirm_title'],
                                       config.UI_CFG['close_confirm_text'],
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            else:
                if self.worker_thread is not None and self.worker_thread.isRunning():
                    self.worker_thread.requestInterruption()
                    if not self.worker_thread.wait(1000):
                        logging.warning("Worker thread did not stop gracefully on close, forcing termination.")
                        self.worker_thread.terminate()
                        self.worker_thread.wait(1000)
                
                if hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None and self.export_all_worker_thread.isRunning():
                    self.export_all_worker_thread.requestInterruption()
                    if not self.export_all_worker_thread.wait(1000):
                        logging.warning("Export All worker thread did not stop gracefully on close, forcing termination.")
                        self.export_all_worker_thread.terminate()
                        self.export_all_worker_thread.wait(1000)
        
        self.save_window_settings()
        logging.info(f"--- {config.APP_NAME} V{config.APP_VERSION} Closing ---")
        event.accept()

    def _save_settings(self):
        """Saves the entire profile settings dictionary."""
        if not config.save_settings(config.PROFILE_CFG, config.PROFILE_SETTINGS_FILE):
            self.show_error(config.UI_CFG['error_saving_settings_title'], config.UI_CFG['error_saving_settings_text'].format(filename=config.PROFILE_SETTINGS_FILE.name))

    def import_data_dialog(self, fmt, dropdown_widget=None):
        """Opens a file dialog to import data in the specified format."""
        if (self.worker_thread is not None and self.worker_thread.isRunning()) or (hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None and self.export_all_worker_thread.isRunning()):
            self.show_error(config.UI_CFG['operation_in_progress_title'], config.UI_CFG['operation_in_progress_text'])
            return
        logging.info(f"Starting import dialog for format: {fmt}")

        # Determine import mode from the dropdown
        import_mode = "replace" if self.import_mode_combo.currentText() == config.UI_CFG['import_mode_replace'] else "append"

        # If there is existing data and the import mode is "replace", confirm with the user
        if not self.table_model.data_df().empty and import_mode == "replace":
            reply = QMessageBox.question(
                self,
                config.UI_CFG.get('import_confirm_replace_title', "Confirm Replace"),
                config.UI_CFG.get('import_confirm_replace_text', "This will replace all existing data. Are you sure?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                self.update_status(config.UI_CFG['status_cancelled']); return

        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_filters = {
            'SDR33': "Sokkia/Topcon SDR33 Files (*.sdr)",
            'GSI': "Leica GSI Files (*.gsi)",
            'DXF': "AutoCAD DXF/DWG Files (*.dxf *.dwg)",
            'KML': "Google Earth KML Files (*.kml *.kmz)",
            'TXT': "Text Files (*.txt);;All Files (*.*)",
            'CSV': "CSV Files (*.csv);;All Files (*.*)",
            'Excel': "Excel Files (*.xlsx *.xls);;All Files (*.*)",
        }
        file_dialog.setNameFilter(file_filters.get(fmt, "All Files (*.*)"))
        file_dialog.setWindowTitle(config.UI_CFG['import_dialog_title'].format(format=fmt))

        last_path = self.settings_manager.value("lastImportPath", str(Path.home()))
        file_dialog.setDirectory(str(last_path))

        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if not selected_files:
                self.update_status(config.UI_CFG['status_cancelled'])
                return

            self.settings_manager.setValue("lastImportPath", str(Path(selected_files[0]).parent))
            
            self.set_ui_busy(True, config.UI_CFG['status_importing'].format(format=fmt))
            QApplication.processEvents() # Allow UI to update

            try:
                all_dfs = []
                for file_str in selected_files:
                    file_path = Path(file_str)
                    self.current_file_path = file_str
                    
                    # Prepare settings for the reader function
                    column_order_str = dropdown_widget.currentText() if dropdown_widget and hasattr(dropdown_widget, 'currentText') else "Auto-detect Columns"
                    read_settings = {'column_order_str': column_order_str}
                    if fmt == 'KML':
                        read_settings.update(self.kml_settings)
                    
                    # Use the new universal reader function
                    df = dp.read_survey_file(file_path, settings=read_settings)
                    if not df.empty:
                        all_dfs.append(df)

                if not all_dfs:
                    self.show_error("Import Failed", "No data could be imported from the selected file(s). The file might be empty or in an unsupported format.")
                    self.set_ui_busy(False)
                    self.update_status("Import failed.", 0)
                    return

                combined_df = pd.concat(all_dfs, ignore_index=True)

                # Handle import mode (replace or append)
                final_df = combined_df
                if import_mode == "append" and not self.table_model.data_df().empty:
                    # Align columns before concatenating to handle mismatched columns
                    existing_df = self.table_model.data_df()
                    combined_df_aligned, existing_df_aligned = combined_df.align(existing_df, join='outer', axis=1)
                    final_df = pd.concat([existing_df_aligned, combined_df_aligned], ignore_index=True)

                self.update_table_data(final_df)
                
                summary_message = f"Successfully imported {len(combined_df)} records from {len(selected_files)} file(s)."
                self.update_status(summary_message, 10000)
                QMessageBox.information(self, config.UI_CFG['import_success_title'], summary_message)

            except Exception as e:
                error_message = f"An error occurred during import: {e}"
                logging.error(error_message, exc_info=True)
                self.show_error(config.UI_CFG['worker_error_import_title'], error_message)
                self.update_status(config.UI_CFG['worker_error_import_status'], 0)
            finally:
                self.set_ui_busy(False)
        else:
            self.update_status(config.UI_CFG['status_cancelled'])

    def export_data_dialog(self, fmt, dropdown_widget=None, specific_path=None):
        """Opens a dialog to save data in the specified format."""
        if (self.worker_thread is not None and self.worker_thread.isRunning()) or (hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None and self.export_all_worker_thread.isRunning()):
            self.show_error(config.UI_CFG['operation_in_progress_title'], config.UI_CFG['operation_in_progress_text'])
            return
        if self.table_model.data_df().empty: self.show_error(config.UI_CFG['export_no_data_title'], config.UI_CFG['export_no_data_text']); return
        
        data_to_export_original = self.table_model.data_df().copy() # Get current data
        file_path_obj = specific_path # Use provided path if available (e.g., from "Export All")

        if not file_path_obj:
            # If no specific path provided, open save file dialog
            default_extension = config.EXPORT_FORMAT_EXTENSIONS.get(fmt, f'.{fmt.lower()}') # Get default extension
            
            # Handle KML/KMZ and DXF/DWG format selection
            if fmt == 'DXF':
                # Check the new setting for export format, default to DXF
                export_format = self.dxf_settings.get('export_format', 'DXF').upper()
                if export_format == 'DWG':
                    default_extension = '.dwg'
                    file_filter = "Autodesk DWG Files (*.dwg);;All Files (*.*)"
                else: # Default to DXF
                    default_extension = '.dxf'
                    file_filter = "AutoCAD DXF Files (*.dxf);;All Files (*.*)"
            elif fmt == 'KML':
                # The format is now part of the settings, not a main window dropdown
                selected_format = self.kml_settings.get('kml_format', 'KML')
                if selected_format == 'KMZ':
                    default_extension = '.kmz'
                    file_filter = "KMZ Files (*.kmz);;All Files (*.*)"
                else: # Default to KML
                    default_extension = '.kml'
                    file_filter = "KML Files (*.kml);;All Files (*.*)"
            else:
                file_filter = f"{fmt} Files (*{default_extension});;All Files (*.*)"
            
            # Determine default filename from last opened file or a generic name
            default_fname = Path(self.current_file_path).stem if self.current_file_path and Path(self.current_file_path).is_file() else "SurveyData"
            
            file_dialog = QFileDialog(self)
            file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave) # Set dialog mode to save
            file_dialog.setDefaultSuffix(default_extension.lstrip('.')) # Set default extension
            file_dialog.setNameFilter(file_filter) # Set file filter
            file_dialog.setWindowTitle(config.UI_CFG['export_dialog_title'].format(format=fmt))
            
            # Set initial directory from last export path
            last_path = self.settings_manager.value("lastExportPath", str(Path(self.current_file_path).parent if self.current_file_path and Path(self.current_file_path).is_file() else Path.home()))
            file_dialog.setDirectory(str(last_path))
            file_dialog.selectFile(f"{default_fname}_Export{default_extension}") # Suggest a default filename
            
            if file_dialog.exec(): # Open dialog and process if user clicks OK
                file_path_str = file_dialog.selectedFiles()[0]
                file_path_obj = Path(file_path_str)
                # Ensure the file has the correct extension
                if file_path_obj.suffix.lower() != default_extension.lower():
                    file_path_obj = file_path_obj.with_suffix(default_extension)
                self.settings_manager.setValue("lastExportPath", str(file_path_obj.parent)) # Save the directory
            else:
                self.update_status(config.UI_CFG['status_cancelled']); return
        
        logging.info(f"Attempting to export data to: {file_path_obj} in format {fmt}")
        
        # Prepare export settings dictionary
        export_settings = {}
        if fmt == 'DXF': export_settings = self.dxf_settings
        elif fmt == 'KML':
            export_settings = self.kml_settings.copy()
            # The KML format is already part of the kml_settings dictionary
            # and is handled by the KMLSettingsDialog. No need to add it here.
        elif fmt == 'SDR33': # Include the swap E/N checkbox state for SDR33
            export_settings['swap_e_n_for_sdr'] = self.sdr_ne_radio.isChecked()
        elif fmt in ['TXT', 'CSV']:
            # Get delimiter from dropdown if available, honoring display→key mapping
            delimiter_dropdown = getattr(self, f"{fmt.lower()}_delimiter_dropdown", None)
            if delimiter_dropdown:
                selected_display = delimiter_dropdown.currentText()
                # Ensure selected_display is not None before using it as a key
                key = config.DISPLAY_DELIMITER_TO_KEY.get(selected_display or '', selected_display or '')
                if key == 'Auto-detect':
                    # For export, fallback to sensible defaults (CSV→comma, TXT→tab)
                    export_settings['txt_delimiter'] = ',' if fmt == 'CSV' else '\t'
                else:
                    export_settings['txt_delimiter'] = TXT_DELIMITER_MAP.get(key or '', '\t')
        
        # Get column order string from dropdown if applicable
        column_order_str = None
        if fmt in ['CSV', 'TXT', 'Excel'] and dropdown_widget and hasattr(dropdown_widget, 'currentText'):
            column_order_str = dropdown_widget.currentText()

        # Start worker thread for export
        self.set_ui_busy(True, config.UI_CFG['status_exporting'].format(format=fmt))
        self.worker_thread = QThread()
        self.worker_object = Worker(task_type="export", file_paths=[str(file_path_obj)], fmt=fmt,
                                    export_settings=export_settings,
                                    data_to_export=data_to_export_original, column_order_str=column_order_str)
        self.worker_object.moveToThread(self.worker_thread)
        
        # Connect signals and slots
        self.worker_thread.started.connect(self.worker_object.run)
        self.worker_object.finished.connect(self.handle_worker_finished)
        self.worker_object.error.connect(self.handle_worker_error)
        self.worker_object.progress.connect(self.handle_worker_progress)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        # We don't delete worker_object here, it will be cleaned up in handle_worker_finished
        
        self.worker_thread.start() # Start the thread

    def export_all_formats_dialog(self):
        """Opens a dialog to select a folder and export data to all supported formats at once."""
        if (self.worker_thread is not None and self.worker_thread.isRunning()) or (hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None and self.export_all_worker_thread.isRunning()):
            self.show_error(config.UI_CFG['operation_in_progress_title'], config.UI_CFG['operation_in_progress_text'])
            return
        if self.table_model.data_df().empty: self.show_error(config.UI_CFG['export_no_data_title'], config.UI_CFG['export_no_data_text']); return

        # Select the parent directory for exports
        export_dir_parent = self.settings_manager.value("lastExportAllPath", str(config.BASE_DIR))
        export_dir = QFileDialog.getExistingDirectory(self, config.UI_CFG['export_all_formats_title'], str(export_dir_parent))
        if not export_dir: self.update_status(config.UI_CFG['status_cancelled']); return
        self.settings_manager.setValue("lastExportAllPath", export_dir) # Save the chosen directory

        # Create a unique sub-directory for this batch export
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_app_name = re.sub(r'[^\w_.-]', '', config.APP_NAME.split(" ")[0]) or "SurveyExport"
        dir_name = f"{safe_app_name}_Batch_{timestamp}"
        full_export_path_obj = Path(export_dir) / dir_name
        
        try:
            full_export_path_obj.mkdir(parents=True, exist_ok=False) # Create directory, fail if it exists
        except FileExistsError:
            self.show_error(config.UI_CFG['export_error_folder_exists_title'], config.UI_CFG['export_error_folder_exists_text'].format(folder_name=dir_name, path=export_dir))
            return
        except OSError as e_mkdir:
            self.show_error(config.UI_CFG['export_error_folder_create_title'], config.UI_CFG['export_error_folder_create_text'].format(path=full_export_path_obj, error=e_mkdir))
            return

        # Determine base filename from current file or generic name
        base_filename = Path(self.current_file_path).stem if self.current_file_path and Path(self.current_file_path).is_file() else "SurveyData"
        
        # Inform user about the export directory
        QMessageBox.information(self, config.UI_CFG['export_all_info_title'],
                                config.UI_CFG['export_all_info_text'].format(path=full_export_path_obj))

        # Start a new worker thread specifically for the "Export All" functionality
        self.set_ui_busy(True, "Exporting All Formats...")
        self.export_all_worker_thread = QThread()
        # Create the specific worker object for batch export
        self.export_all_worker_object = ExportAllWorker(self, config.EXPORT_FORMAT_EXTENSIONS,
                                                        full_export_path_obj, base_filename,
                                                        self.table_model.data_df())
        self.export_all_worker_object.moveToThread(self.export_all_worker_thread)
        
        # Connect signals and slots for the batch export worker
        self.export_all_worker_thread.started.connect(self.export_all_worker_object.run)
        self.export_all_worker_object.all_finished.connect(self._handle_export_all_finished)
        self.export_all_worker_object.all_error.connect(self._handle_export_all_error)
        self.export_all_worker_object.file_progress.connect(self._handle_export_all_progress)
        self.export_all_worker_thread.finished.connect(self.export_all_worker_thread.deleteLater)
        # We don't delete worker_object here, it will be cleaned up in _handle_export_all_finished/_error
        
        self.export_all_worker_thread.start() # Start the batch export thread

    # --- Slots for Export All worker ---
    @Slot(str, int, int)
    def _handle_export_all_progress(self, format_name, current_idx, total_formats):
        """Updates progress bar and status for Export All task."""
        percentage = int((current_idx / total_formats) * 100)
        self.progress_bar.setValue(percentage)
        msg = f"Exporting All: {format_name} ({current_idx}/{total_formats})"
        self.progress_bar.setFormat(msg + " %p%")
        self.status_label.setText(msg)

    @Slot(str)
    def _handle_export_all_finished(self, summary_message):
        """Handles the completion of the Export All task."""
        QMessageBox.information(self, config.UI_CFG['export_all_info_title'], summary_message) # Show summary message
        self.update_status("Export All finished successfully.", 5000)
        self.set_ui_busy(False) # Reset UI
        
        # Make sure the thread is finished before cleaning it up
        if hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None:
            self.export_all_worker_thread.quit()
            self.export_all_worker_thread.wait(1000)
        self._cleanup_export_all_worker() # Clean up worker thread

    @Slot(str)
    def _handle_export_all_error(self, summary_message):
        """Handles errors encountered during the Export All task."""
        QMessageBox.warning(self, f"{config.UI_CFG['export_all_info_title']} (with errors)", summary_message + "\nPlease check the log.") # Show warning message
        self.update_status("Export All finished with errors. Check logs.", 0)
        self.set_ui_busy(False) # Reset UI
        
        # Make sure the thread is finished before cleaning it up
        if hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None:
            self.export_all_worker_thread.quit()
            self.export_all_worker_thread.wait(1000)
        self._cleanup_export_all_worker() # Clean up worker thread

    def _cleanup_export_all_worker(self):
        """Cleans up the Export All worker thread and object."""
        if hasattr(self, 'export_all_worker_thread') and self.export_all_worker_thread is not None:
            if self.export_all_worker_thread.isRunning():
                self.export_all_worker_thread.requestInterruption()
                self.export_all_worker_thread.wait(2000)  # Wait longer
                if self.export_all_worker_thread.isRunning():
                    self.export_all_worker_thread.terminate()
                self.export_all_worker_thread.wait(1000)
            self.export_all_worker_thread = None # Dereference thread
        if hasattr(self, 'export_all_worker_object') and self.export_all_worker_object:
            self.export_all_worker_object = None # Dereference object

    def _cleanup_worker_thread(self):
        """Cleans up the regular worker thread and object."""
        if hasattr(self, 'worker_thread') and self.worker_thread is not None:
            if self.worker_thread.isRunning():
                self.worker_thread.requestInterruption()
                self.worker_thread.wait(2000)  # Wait longer
                if self.worker_thread.isRunning():
                    self.worker_thread.terminate()
                    self.worker_thread.wait(1000)
            self.worker_thread = None # Dereference thread
        if hasattr(self, 'worker_object') and self.worker_object:
            self.worker_object = None # Dereference object


    # --- Dialog handlers for settings ---
    def get_dxf_export_settings(self):
        """Opens the DXF settings dialog and saves the changes."""
        # Pass the specific 'dxf' part of the profile to the dialog
        dxf_dialog = DXFSettingsDialog(self, self.dxf_settings)
        if dxf_dialog.exec() == QDialog.DialogCode.Accepted:
            # The dialog now modifies the dictionary in-place, so we just save the whole profile
            self._save_settings()
            self.update_status(config.UI_CFG['status_dxf_settings_saved'])
        else:
            self.update_status(config.UI_CFG['status_dxf_settings_cancelled'])

    def get_kml_export_settings(self):
        """Opens the KML settings dialog and saves the changes, adding KML/KMZ format selection."""
        kml_dialog = KMLSettingsDialog(self, self.kml_settings)
        # When opening the settings dialog, set the saved colors in the color selection elements if they exist
        color_fields = [
            ('color', 'color'),
            ('label_color', 'label_color'),
            ('line_color', 'line_color'),
            ('poly_outline_color', 'poly_outline_color'),
            ('fill_color', 'fill_color'),
        ]
        # When opening the settings dialog, set the saved colors in the color selection elements as they are (without rounding or processing)
        for widget_key, setting_key in color_fields:
            widget = getattr(kml_dialog, 'widgets', {}).get(widget_key)
            if widget is not None and setting_key in self.kml_settings:
                widget.setText(str(self.kml_settings[setting_key]))
        # The 'kml_format' dropdown is already created within the KMLSettingsDialog
        # under the key 'kml_format' in its widgets dictionary.
        # We just need to ensure its initial value is set correctly.
        if 'kml_format' in kml_dialog.widgets:
            kml_format_combo = kml_dialog.widgets['kml_format']
            current_fmt = self.kml_settings.get('kml_format', 'KML')
            kml_format_combo.setCurrentText(current_fmt if current_fmt in ["KML", "KMZ"] else "KML")

        # Button to preview in Google Earth before saving
        preview_btn = QPushButton(config.UI_CFG['kml_preview_button'])
        preview_btn.setToolTip(config.UI_CFG['kml_preview_tooltip'])
        def preview_in_google_earth():
            import tempfile, subprocess, sys
            # Get the latest settings from the dialog window elements
            try:
                # The dialog has a method to get all current values
                temp_settings = kml_dialog.validate_and_get_values()
                if temp_settings is None: # Validation failed
                    return
            except ValueError as ve:
                QMessageBox.warning(self, config.UI_CFG['kml_preview_validation_error_title'], config.UI_CFG['kml_preview_validation_error_text'].format(error=ve))
                return
            # Generate temporary file
            ext = '.kmz' if temp_settings.get('kml_format', 'KML') == 'KMZ' else '.kml'
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                tmp_path = tmp_file.name
            # Export current data to the temporary file
            try:
                from taco_geo_processor.core.workers import Worker
                worker = Worker(task_type="export", file_paths=[tmp_path], fmt="KML", export_settings=temp_settings, data_to_export=self.table_model.data_df())
                worker.run()
                # Open the file in Google Earth
                if sys.platform.startswith('win'):
                    os.startfile(tmp_path)
                elif sys.platform.startswith('darwin'):
                    subprocess.call(['open', tmp_path])
                else:
                    subprocess.call(['xdg-open', tmp_path])
            except Exception as e:
                QMessageBox.warning(self, config.UI_CFG['kml_preview_error_title'], config.UI_CFG['kml_preview_error_text'].format(error=e))

        preview_btn.clicked.connect(preview_in_google_earth)
        # Add the button to the dialog's button box for standard placement
        kml_dialog.button_box.addButton(preview_btn, QDialogButtonBox.ButtonRole.ActionRole)

        if kml_dialog.exec() == QDialog.DialogCode.Accepted:
            # The dialog now modifies the dictionary in-place, so we just save the whole profile
            self._save_settings()
            self.update_status(config.UI_CFG['status_kml_settings_saved'])
        else:
            self.update_status(config.UI_CFG['status_kml_settings_cancelled'])


    def show_find_dialog(self):
        """Opens the advanced search dialog and starts the search process."""
        find_dialog = FindDialog(self)
        if find_dialog.exec():
            settings = find_dialog.get_search_settings()
            self.find_in_table_advanced(settings)
        else:
            # Clear the filter if the dialog is closed
            self.proxy_model.setFilterRegularExpression(QRegularExpression())
            self.proxy_model.setFilterByColumns([])
            self.update_status(config.UI_CFG['find_status_cleared'])

    def find_in_table_advanced(self, settings):
        """Applies the advanced filter for searching in the table."""
        search_text = settings['text']
        
        if not search_text:
            self.proxy_model.setFilterRegularExpression(QRegularExpression())
            self.proxy_model.setFilterByColumns([])
            self.update_status(config.UI_CFG['find_status_cleared'])
            return
            
        # Build the regular expression pattern based on the match type
        regex_pattern = self._build_regex_pattern(search_text, settings)
        
        # Set regular expression options
        options = QRegularExpression.PatternOption.NoPatternOption
        if not settings['match_case']:
            options |= QRegularExpression.PatternOption.CaseInsensitiveOption
            
        q_regex = QRegularExpression(regex_pattern, options)
        self.proxy_model.setFilterRegularExpression(q_regex)
        
        # Set the columns to search in
        if settings['search_all_columns']:
            self.proxy_model.setFilterByColumns([])  # Search in all columns
        else:
            self.proxy_model.setFilterByColumns(settings['selected_columns'])
            
        # Display results
        matched_rows = self.proxy_model.rowCount()
        if matched_rows > 0:
            first_match_index = self.proxy_model.index(0, 0)
            if first_match_index.isValid():
                self.table_view.scrollTo(first_match_index, QAbstractItemView.ScrollHint.PositionAtTop)
                self.table_view.selectRow(0)
            
            status_msg = config.UI_CFG['find_status_found'].format(count=matched_rows, text=search_text)
            if settings['export_results']:
                self._export_search_results(settings)
            self.update_status(status_msg)
        else:
            self.update_status(config.UI_CFG['find_status_not_found'].format(text=search_text))

    def _build_regex_pattern(self, text, settings):
        """Builds the regular expression pattern based on the search settings."""
        match_type = settings['match_type']
        whole_word = settings['whole_word']
        
        # Use the user's text as a raw regex pattern if specified
        if match_type == "Regular expression match":
            return text
            
        # For all other match types, escape the text to treat it as a literal string
        escaped_text = re.escape(text)
        
        if match_type == "Exact match":
            # Anchor the pattern to match the entire cell content
            pattern = f"^{escaped_text}$"
        elif match_type == "Starts with":
            # Anchor the pattern to the start of the cell content
            pattern = f"^{escaped_text}"
        elif match_type == "Ends with":
            # Anchor the pattern to the end of the cell content
            pattern = f"{escaped_text}$"
        else:  # Partial match (contains) is the default
            pattern = escaped_text
            
        # Add word boundaries if required, but it doesn't make sense for "Exact match"
        if whole_word and match_type != "Exact match":
            pattern = r'\b' + pattern + r'\b'
            
        return pattern

    def _export_search_results(self, settings):
        """Export the search results to a file."""
        try:
            # Get filtered data
            filtered_data = []
            for row in range(self.proxy_model.rowCount()):
                row_data = {}
                for col in range(self.proxy_model.columnCount()):
                    index = self.proxy_model.index(row, col)
                    header = self.proxy_model.headerData(col, Qt.Orientation.Horizontal)
                    value = self.proxy_model.data(index)
                    row_data[header] = value
                filtered_data.append(row_data)
                
            if not filtered_data:
                self.update_status("No data to export.")
                return
                
            # Convert to DataFrame
            df = pd.DataFrame(filtered_data)
            
            # Open save file dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                config.UI_CFG['export_results_dialog_title'],
                f"Search_Results_{settings['text']}",
                "Excel Files (*.xlsx);;CSV Files (*.csv);;PDF Files (*.pdf)"
            )
            
            if not file_path:
                return
                
            # Export file
            final_file_path = file_path
            if file_path.endswith('.xlsx'):
                df.to_excel(file_path, index=False, engine='openpyxl')
            elif file_path.endswith('.csv'):
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
            elif file_path.endswith('.pdf'):
                # PDF export requires an additional library
                final_file_path = self._export_to_pdf(df, file_path)
            else:
                # Default: Excel
                if not file_path.endswith('.xlsx'):
                    file_path += '.xlsx'
                df.to_excel(file_path, index=False, engine='openpyxl')
                final_file_path = file_path

            if final_file_path:
                file_name = Path(final_file_path).name
                export_format = Path(final_file_path).suffix[1:].upper()
                success_message = config.UI_CFG['export_results_success_text'].format(count=len(df), filename=file_name, format=export_format)
                QMessageBox.information(self, config.UI_CFG['export_results_success_title'], success_message)
                self.update_status(f"Exported {len(df)} rows to {final_file_path}")
            
        except Exception as e:
            logging.error(f"Error exporting search results: {e}")
            self.show_error(config.UI_CFG['export_results_error_title'], config.UI_CFG['export_results_error_text'].format(error=e))

    def _export_to_pdf(self, df, file_path):
        """Export DataFrame to a PDF file. Returns the path of the created file."""
        # Import reportlab library (required)
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        
        try:
            doc = SimpleDocTemplate(file_path, pagesize=A4)
            elements = []
            
            # Add title
            styles = getSampleStyleSheet()
            title = f"Search Results: {len(df)} rows"
            elements.append(Paragraph(title, styles['Title']))
            
            # Prepare data for the table
            table_data = [df.columns.tolist()]  # Column headers
            for _, row in df.iterrows():
                table_data.append([str(val) for val in row.values])
            
            # Create table
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            elements.append(table)
            doc.build(elements)
            return file_path
            
        except Exception as e:
            logging.error(f"Error exporting PDF: {e}")
            # In case of failure, export as CSV
            csv_path = file_path.replace('.pdf', '.csv')
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            self.show_error(config.UI_CFG['export_pdf_error_title'], config.UI_CFG['export_pdf_error_text'].format(error=e))
            return csv_path

    def show_all_data(self):
        """Show all data (clear the search filter)."""
        self.proxy_model.setFilterRegularExpression(QRegularExpression())
        self.proxy_model.setFilterByColumns([])
        self.proxy_model.invalidateFilter()
        
        total_rows = self.table_model.rowCount()
        if total_rows > 0:
            self.update_status(config.UI_CFG['show_all_status'].format(count=total_rows))
        else:
            self.update_status(config.UI_CFG['show_all_no_data_status'])

    def find_in_table(self, text, match_case):
        """Simple search function for compatibility with old code."""
        settings = {
            'text': text,
            'match_type': 'Partial match (contains)',
            'match_case': match_case,
            'whole_word': False,
            'search_all_columns': True,
            'export_results': False,
            'selected_columns': []
        }
        self.find_in_table_advanced(settings)

    def _open_whatsapp(self):
        """Opens the WhatsApp application with the developer's number."""
        whatsapp_url = QUrl("https://wa.me/201029480271")
        if not QDesktopServices.openUrl(whatsapp_url):
            QMessageBox.warning(self, "Error", config.UI_CFG['contact_whatsapp_error'])

    def _open_facebook(self):
        """Opens the developer's Facebook page."""
        facebook_url = QUrl("https://www.facebook.com/")
        if not QDesktopServices.openUrl(facebook_url):
            QMessageBox.warning(self, "Error", config.UI_CFG['contact_facebook_error'])

    def show_info(self):
        """Displays the "About" dialog with application and developer information."""
        info_dialog = QDialog(self)
        info_dialog.setWindowTitle("حول البرنامج")
        info_dialog.resize(500, 600)
        info_dialog.setMinimumSize(400, 500)
        
        # تصميم خلفية متدرجة وجذابة
        info_dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f3460);
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        
        layout = QVBoxLayout(info_dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # تم حذف الإطارات العلوية (الشعار، العنوان، الإصدار، الوصف) لتنظيف الواجهة
        # قراءة الإصدار الحالي
        current_version = "1.0.0"
        try:
            version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VERSION')
            with open(version_file, 'r') as f:
                current_version = f.read().strip()
        except:
            pass

        # فاصل جذاب
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 #3498db, stop:0.5 #2ecc71, stop:1 #9b59b6);
            border-radius: 2px;
            margin: 20px 0;
        """)
        separator.setFixedHeight(3)
        layout.addWidget(separator)

        # قسم معلومات المطور
        dev_section = QLabel(
            "<h3 style='color: #3498db; margin: 20px 0; text-align: center; font-weight: 900;'>👨‍💻 Developer Information</h3>"
        )
        dev_section.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dev_section)

        # تم حذف إطار معلومات المطور

        # فاصل جذاب للتحديثات
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 #2ecc71, stop:0.5 #27ae60, stop:1 #16a085);
            border-radius: 2px;
            margin: 20px 0;
        """)
        separator2.setFixedHeight(2)
        layout.addWidget(separator2)

        # قسم التحديثات
        update_section = QLabel("<h3 style='color: #2ecc71; margin: 15px 0; text-align: center; font-weight: 700;'>🔄 Software Updates</h3>")
        update_section.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(update_section)

        # تم حذف إطار معلومات التحديثات

        # زر التحقق من التحديثات المحسن
        check_update_button = QPushButton("🔄 Check for Updates")
        try:
            check_update_button.setIcon(QIcon.fromTheme("system-software-update"))
        except:
            try:
                from taco_geo_processor.utils.utils import get_icon
                check_update_button.setIcon(get_icon("update_icon.png", 32))
            except:
                pass
        check_update_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #2ecc71, stop:0.5 #27ae60, stop:1 #229954);
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 30px;
                font-weight: bold;
                font-size: 18px;
                min-width: 250px;
                min-height: 60px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #27ae60, stop:0.5 #229954, stop:1 #1e8449);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #229954, stop:1 #1e8449);
            }
        """)
        check_update_button.clicked.connect(self.check_for_updates)
        
        # إضافة الزر في إطار خاص
        button_frame = QFrame()
        button_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                margin: 20px 0;
            }
        """)
        button_layout = QHBoxLayout(button_frame)
        button_layout.addStretch()
        button_layout.addWidget(check_update_button)
        button_layout.addStretch()
        layout.addWidget(button_frame)

        # فاصل جذاب لطرق الاتصال
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.HLine)
        separator3.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 #9b59b6, stop:0.5 #8e44ad, stop:1 #7d3c98);
            border-radius: 2px;
            margin: 20px 0;
        """)
        separator3.setFixedHeight(2)
        layout.addWidget(separator3)

        contact_section = QLabel("<h3 style='color: #9b59b6; margin: 15px 0; text-align: center; font-weight: 700;'>📞 Contact Methods</h3>")
        layout.addWidget(contact_section)

        contact_frame = QFrame()
        contact_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 rgba(155, 89, 182, 0.15), stop:1 rgba(155, 89, 182, 0.05));
                border-radius: 20px;
                padding: 25px;
                margin: 15px;
                border: 2px solid rgba(155, 89, 182, 0.4);
            }
        """)
        contact_layout = QHBoxLayout(contact_frame)
        contact_layout.setSpacing(30)

        # زر واتساب محسن
        whatsapp_button = QPushButton()
        try:
            from taco_geo_processor.utils.utils import get_icon
            whatsapp_button.setIcon(get_icon("whatsapp-icon.png", 90))
        except:
            pass
        whatsapp_button.setIconSize(QSize(70, 70))
        whatsapp_button.setToolTip("Contact the developer via WhatsApp")
        whatsapp_button.setFixedSize(150, 150)
        whatsapp_button.setStyleSheet("""
            QPushButton {
                border: 5px solid #25D366;
                border-radius: 25px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #25D366, stop:0.5 #128C7E, stop:1 #0F796E);
                padding: 15px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #128C7E, stop:0.5 #0F796E, stop:1 #0D6B5F);
                border-color: #0F796E;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #0F796E, stop:1 #0D6B5F);
                border-color: #0D6B5F;
            }
        """)
        try:
            whatsapp_button.clicked.connect(self._open_whatsapp)
        except:
            pass
        contact_layout.addWidget(whatsapp_button)

        # زر فيسبوك محسن
        facebook_button = QPushButton()
        try:
            facebook_button.setIcon(get_icon("facebook_icon.png", 90))  # type: ignore
        except:
            pass
        facebook_button.setIconSize(QSize(70, 70))
        facebook_button.setToolTip("Follow the developer on Facebook")
        facebook_button.setFixedSize(150, 150)
        facebook_button.setStyleSheet("""
            QPushButton {
                border: 5px solid #1877F2;
                border-radius: 25px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #1877F2, stop:0.5 #0d6efd, stop:1 #0b5ed7);
                padding: 15px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #0d6efd, stop:0.5 #0b5ed7, stop:1 #0a4b9e);
                border-color: #0b5ed7;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #0b5ed7, stop:1 #0a4b9e);
                border-color: #0a4b9e;
            }
        """)
        try:
            facebook_button.clicked.connect(self._open_facebook)
        except:
            pass
        contact_layout.addWidget(facebook_button)

        contact_layout.addStretch()
        layout.addWidget(contact_frame)

        # زر الإغلاق المحسن
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(info_dialog.accept)
        button_box.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #3498db, stop:0.5 #2980b9, stop:1 #21618c);
                color: #fff;
                border: none;
                padding: 15px 35px;
                border-radius: 30px;
                font-weight: bold;
                font-size: 16px;
                min-width: 140px;
                min-height: 50px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #2980b9, stop:0.5 #21618c, stop:1 #1a5276);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #21618c, stop:1 #1a5276);
            }
        """)
        
        # إضافة الزر في إطار خاص
        close_button_frame = QFrame()
        close_button_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                margin: 20px 0;
            }
        """)
        close_button_layout = QHBoxLayout(close_button_frame)
        close_button_layout.addStretch()
        close_button_layout.addWidget(button_box)
        close_button_layout.addStretch()
        layout.addWidget(close_button_frame)

        info_dialog.setLayout(layout)
        info_dialog.exec()  # Show dialog modally

    def check_for_updates(self):
        """Checks for updates using GitHub API."""
        # Show a "checking for updates" message
        progress_dialog = QProgressDialog("جاري فحص التحديثات...", "إلغاء", 0, 0, self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setWindowTitle("فحص التحديثات")
        progress_dialog.show()
        QApplication.processEvents()

        try:
            # Import the GitHub updater
            from github_updater import GitHubUpdater
            
            # Initialize updater with your GitHub repository
            # GitHub username: HOHO878
            # You need to create a repository for your project
            updater = GitHubUpdater("HOHO878", "taco-geo-processor-")
            
            progress_dialog.setValue(50)
            QApplication.processEvents()
            
            # Check for updates
            result = updater.check_for_updates()
            
            progress_dialog.setValue(100)
            progress_dialog.close()
            
            if result['status'] == 'update_available':
                # Update available
                release_notes = result.get('release_notes', 'لا توجد ملاحظات إصدار')
                if len(release_notes) > 200:
                    release_notes = release_notes[:200] + "..."
                
                reply = QMessageBox.question(
                    self,
                    "تحديث متاح",
                    f"إصدار جديد متاح!\n\n"
                    f"الإصدار الحالي: {result['current_version']}\n"
                    f"الإصدار الجديد: {result['latest_version']}\n\n"
                    f"ملاحظات الإصدار:\n{release_notes}\n\n"
                    f"هل تريد زيارة صفحة التحميل؟",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    updater.open_download_page()
                    
            elif result['status'] == 'up_to_date':
                # No updates available
                QMessageBox.information(
                    self,
                    "لا توجد تحديثات",
                    f"أنت تستخدم أحدث إصدار متاح.\n\nالإصدار الحالي: {result['current_version']}"
                )
            else:
                # Error occurred
                QMessageBox.warning(
                    self,
                    "خطأ في فحص التحديثات",
                    f"حدث خطأ أثناء فحص التحديثات:\n{result.get('message', 'خطأ غير معروف')}\n\n"
                    "يمكنك التحقق من التحديثات يدوياً من:\n"
                    "• موقع المطور الرسمي\n"
                    "• صفحة المشروع على GitHub"
                )
                
        except ImportError:
            progress_dialog.close()
            # Fallback to simple version check
            current_version = "1.0.0"
            try:
                version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VERSION')
                with open(version_file, 'r') as f:
                    current_version = f.read().strip()
            except:
                pass
            
            QMessageBox.information(
                self,
                "فحص التحديثات",
                f"الإصدار الحالي: {current_version}\n\n"
                "للتحقق من التحديثات، يرجى زيارة:\n"
                "• موقع المطور الرسمي\n"
                "• صفحة المشروع على GitHub"
            )
        except Exception as e:
            progress_dialog.close()
            QMessageBox.warning(
                self,
                "خطأ في فحص التحديثات",
                f"حدث خطأ أثناء فحص التحديثات:\n{str(e)}\n\n"
                "يمكنك التحقق من التحديثات يدوياً من:\n"
                "• موقع المطور الرسمي\n"
                "• صفحة المشروع على GitHub"
            )

    def download_and_apply_update(self, download_url):
        """Downloads the update and runs the apply script."""
        # Open the download page in browser
        import webbrowser
        webbrowser.open("https://github.com/HOHO878/taco-geo-processor-/releases")
        
        QMessageBox.information(
            self,
            "تحميل التحديث",
            "تم فتح صفحة التحميل في المتصفح.\n\n"
            "يرجى تحميل أحدث إصدار وتثبيته يدوياً."
        )

    def clear_data(self, keep_columns=False):
        """Clears data from the table after requesting confirmation."""
        if keep_columns:
            message = config.UI_CFG['clear_rows_confirm_text']
        else:
            message = config.UI_CFG['clear_data_confirm_text']
            
        reply = QMessageBox.question(self, config.UI_CFG['clear_data_confirm_title'], message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            self.update_status(config.UI_CFG['status_data_cleared_cancelled']); return
            
        if not self.table_model.data_df().empty:
            self.history_manager.push(self.table_model.data_df())
            
        self.table_model.clear_data(keep_columns)
        self.update_status(config.UI_CFG['status_cleared'] if not keep_columns else config.UI_CFG['status_rows_cleared'])
        
        if not keep_columns:
            self.history_manager.clear()

    def delete_selected_rows(self):
        """Deletes the selected rows from the table after requesting confirmation."""
        selection_model = self.table_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            self.update_status(config.UI_CFG['no_rows_selected_status']); return
            
        selected_proxy_rows_indices = selection_model.selectedRows()
        if not selected_proxy_rows_indices:
            selected_proxy_rows = sorted(list(set(index.row() for index in selection_model.selectedIndexes())))
        else:
            selected_proxy_rows = sorted(list(set(index.row() for index in selected_proxy_rows_indices)))
            
        if not selected_proxy_rows: return
        
        source_rows_to_delete = sorted(list(set(
            self.proxy_model.mapToSource(self.proxy_model.index(proxy_row, 0)).row()
            for proxy_row in selected_proxy_rows
        )))
        
        if not source_rows_to_delete: return
        
        reply = QMessageBox.question(self, config.UI_CFG['delete_rows_confirm_title'], config.UI_CFG['delete_rows_confirm_text'].format(count=len(source_rows_to_delete)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            current_df = self.table_model.data_df().copy()
            updated_df = current_df.drop(index=source_rows_to_delete).reset_index(drop=True)
            self.update_table_data(updated_df)
            self.update_status(config.UI_CFG['delete_rows_status'].format(count=len(source_rows_to_delete)))
        else:
            self.update_status(config.UI_CFG['status_deletion_cancelled'])

    def update_status(self, message, duration_ms=5000):
        """
        Updates the status bar with a message and an optional timer to clear the message.
        duration_ms = 0 means the message will not be cleared automatically.
        """
        self.status_label.setText(message)
        if hasattr(self, '_status_clear_timer') and self._status_clear_timer.isActive():
            self._status_clear_timer.stop()
        if duration_ms > 0:
            if not hasattr(self, '_status_clear_timer'):
                 self._status_clear_timer = QTimer(self)
                 self._status_clear_timer.setSingleShot(True)
                 self._status_clear_timer.timeout.connect(lambda: self.status_label.setText(config.UI_CFG['status_ready']))
            self._status_clear_timer.start(duration_ms)
        elif message != config.UI_CFG['status_ready']:
             pass

    def show_error(self, title, message):
        """Displays an error message box to the user and logs the error."""
        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Icon.Critical)
        error_dialog.setWindowTitle(title)
        error_dialog.setText(f"{message[:300]}{'...' if len(message) > 300 else ''}")
        
        error_dialog.setDetailedText(message)
        error_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        error_dialog.exec()
        
        logging.error(f"{title}: {message}")

    def undo(self):
        """Undoes the last performed operation."""
        if self.history_manager.can_undo():
            previous_state = self.history_manager.undo()
            if previous_state is not None:
                self.table_model.set_data_df(previous_state)
                self.update_status(config.UI_CFG['undo_status'])
            self.update_undo_redo_actions()

    def redo(self):
        """Redoes the last undone operation."""
        if self.history_manager.can_redo():
            next_state = self.history_manager.redo()
            if next_state is not None:
                self.table_model.set_data_df(next_state)
                self.update_status(config.UI_CFG['redo_status'])
            self.update_undo_redo_actions()

    def update_undo_redo_actions(self):
        pass

    def get_current_data_for_export(self):
        """
        Retrieves the currently visible (filtered and sorted) data from the table
        and returns it as a list of dictionaries, suitable for export functions.
        """
        if self.proxy_model.rowCount() == 0:
            return []

        headers = [self.proxy_model.headerData(i, Qt.Orientation.Horizontal) for i in range(self.proxy_model.columnCount())]
        
        data_list = []
        for row in range(self.proxy_model.rowCount()):
            row_data = {}
            for col, header in enumerate(headers):
                index = self.proxy_model.index(row, col)
                # Use .data() which should handle different data types correctly
                value = self.proxy_model.data(index, Qt.ItemDataRole.DisplayRole)
                row_data[header] = value
            data_list.append(row_data)
            
        return data_list

    @Slot(object, str, str)
    def handle_worker_finished(self, result_data, summary_message, representative_path_or_name):
        """Handle the successful completion of a worker task."""
        if isinstance(result_data, pd.DataFrame):
            self.update_table_data(result_data)
            self.update_status(summary_message, 10000)
            QMessageBox.information(self, config.UI_CFG['import_success_title'], summary_message)
        else:
            self.update_status(summary_message, 8000)
            QMessageBox.information(self, config.UI_CFG['export_success_title'], summary_message)
        self.set_ui_busy(False)
        
        if hasattr(self, 'worker_thread') and self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(1000)
        self._cleanup_worker_thread()

    @Slot(str, str)
    def handle_worker_error(self, error_message, context):
        """Handle an error from the worker."""
        if context == "import":
            error_title = config.UI_CFG['worker_error_import_title']
            status_message = config.UI_CFG['worker_error_import_status']
        elif context == "export":
            error_title = config.UI_CFG['worker_error_export_title']
            status_message = config.UI_CFG['worker_error_export_status']
        else:
            error_title = f"Error during {context}"
            status_message = f"Operation failed: {context}"
        
        self.show_error(error_title, error_message)
        self.update_status(status_message, 0)
        self.set_ui_busy(False)
        
        if hasattr(self, 'worker_thread') and self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(1000)
        self._cleanup_worker_thread()


if __name__ == "__main__":
    # --- منطق معالجة التحديثات ---
    # التحقق مما إذا كانت وسيطات سطر الأوامر تطلب عملية تحديث
    update_args = ['--check-update', '--apply']
    if any(arg in sys.argv for arg in update_args):
        # تحديد مسار سكربت عميل التحديث
        updater_script = os.path.join(os.path.dirname(__file__), 'updater', 'update_client.py')
        
        # بناء الأمر لتشغيل عميل التحديث
        command = [sys.executable, updater_script] + sys.argv[1:]
        
        print(f"إعادة توجيه إلى عميل التحديث: {' '.join(command)}")
        
        # تشغيل السكربت في عملية منفصلة
        # هذا يسمح لعميل التحديث بالعمل بشكل مستقل
        try:
            # استخدام Popen للسماح للعملية بالاستمرار حتى لو تم إغلاق هذه النافذة
            subprocess.Popen(command)
        except FileNotFoundError:
            print(f"خطأ: لم يتم العثور على سكربت التحديث في المسار: {updater_script}")
            sys.exit(1)
        except Exception as e:
            print(f"حدث خطأ أثناء محاولة تشغيل عميل التحديث: {e}")
            sys.exit(1)
            
        # الخروج من التطبيق الرئيسي بعد بدء عملية التحديث
        sys.exit(0)

    # --- التشغيل العادي للتطبيق الرسومي ---
    # High DPI scaling is handled automatically in Qt6
    RESTART_CODE = 1000  # Local variable instead of config attribute
    
    app = QApplication(sys.argv)
    try:
        app.setWindowIcon(get_icon("app_icon.png", size=32))
    except:
        # If icon loading fails, continue without icon
        pass
    
    # --- Modern Stylesheet ---
    app.setStyle("Fusion")
    dark_stylesheet = """
        QWidget {
            background-color: #2c3e50;
            color: #ecf0f1;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-size: 10pt;
        }
        QMainWindow {
            background-color: #34495e;
        }
        QGroupBox {
            background-color: #34495e;
            border: 1px solid #4a627a;
            border-radius: 5px;
            margin-top: 1ex;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 3px;
            background-color: #4a627a;
            color: #ecf0f1;
            border-radius: 3px;
        }
        QPushButton {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #2980b9;
        }
        QPushButton:pressed {
            background-color: #1f618d;
        }
        QPushButton:disabled {
            background-color: #566573;
            color: #95a5a6;
        }
        QTableView {
            background-color: #2c3e50;
            border: 1px solid #4a627a;
            gridline-color: #4a627a;
            selection-background-color: #3498db;
            selection-color: white;
        }
        QHeaderView::section {
            background-color: #4a627a;
            color: #ecf0f1;
            padding: 4px;
            border: 1px solid #2c3e50;
            font-weight: bold;
        }
        QComboBox {
            border: 1px solid #4a627a;
            border-radius: 3px;
            padding: 1px 18px 1px 3px;
            min-width: 6em;
            background-color: #34495e;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 15px;
            border-left-width: 1px;
            border-left-color: #4a627a;
            border-left-style: solid;
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
        }
        QComboBox QAbstractItemView {
            border: 1px solid #4a627a;
            background-color: #34495e;
            selection-background-color: #3498db;
        }
        QLineEdit {
            background-color: #34495e;
            border: 1px solid #4a627a;
            border-radius: 3px;
            padding: 4px;
        }
        QCheckBox {
            spacing: 5px;
        }
        QCheckBox::indicator {
            width: 13px;
            height: 13px;
        }
        QDialog {
            background-color: #34495e;
        }
        QMessageBox {
            background-color: #34495e;
        }
        QProgressBar {
            border: 1px solid #4a627a;
            border-radius: 5px;
            text-align: center;
            background-color: #34495e;
            color: #ecf0f1;
        }
        QProgressBar::chunk {
            background-color: #3498db;
            width: 20px;
        }
        QLabel {
            background-color: transparent;
        }
    """
    app.setStyleSheet(dark_stylesheet)
    
    # Do not auto-create icon files/folder on every startup. This was creating the icons folder
    # every time the app ran. Only create missing icons if explicitly enabled in config.
    try:
        create_icons_flag = bool(getattr(config, 'CREATE_MISSING_ICONS_AT_STARTUP', False))
    except Exception:
        create_icons_flag = False

    required_icon_files = [
        "clear_icon.png", "sdr_icon.png", "gsi_icon.png", "dxf_icon.png", "kml_icon.png", "txt_icon.png",
        "csv_icon.png", "excel_icon.png", "all_formats_icon.png", "color_icon.png",
        "app_icon.png", "whatsapp-icon.png", "facebook_icon.png", "search_icon.png", "info_icon.png", "settings_icon.png",
        "circle_plus_style.png", "circle_cross_style.png", "square_plus_style.png", "square_cross_style.png", "dot_style.png",
        "square_circle_plus_style.png", "square_circle_cross_style.png"
    ]
    all_needed_icons = set(required_icon_files)
    if create_icons_flag:
        config.ICON_DIR.mkdir(parents=True, exist_ok=True)
        for icon_filename in all_needed_icons:
            icon_path = config.ICON_DIR / icon_filename
            if not icon_path.is_file():
                try:
                    pixmap = QPixmap(config.DEFAULT_ICON_SIZE, config.DEFAULT_ICON_SIZE)
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    try:
                        painter.setPen(QColor(180, 180, 180))
                        painter.drawRect(0, 0, config.DEFAULT_ICON_SIZE - 1, config.DEFAULT_ICON_SIZE - 1)
                        painter.drawLine(0, 0, config.DEFAULT_ICON_SIZE - 1, config.DEFAULT_ICON_SIZE - 1)
                    finally:
                        painter.end()
                    pixmap.save(str(icon_path))
                    logging.info(f"Created dummy icon: {icon_path}")
                except Exception as e_icon:
                    logging.error(f"Failed to create dummy icon {icon_filename}: {e_icon}")

    main_win = MainWindow()
    main_win.show()
    app.exec()
