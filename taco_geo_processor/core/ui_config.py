# -*- coding: utf-8 -*-
"""
Module for managing UI-related configurations and settings.
"""
from typing import Dict, Any

def get_default_ui_settings() -> Dict[str, Any]:
    """
    Returns a dictionary containing the default UI settings, text, and messages.
    This makes the application easier to customize and translate.
    """
    return {
        "app_title": "Survey Data Converter Pro",
        "app_version": "2.0.0",
        
        # --- Main Window ---
        "window_title": "{app_title} V{app_version}",
        "min_window_width": 700,
        "min_window_height": 780,
        "status_ready": "Ready. Load data or paste from clipboard.",
        "status_processing": "Processing...",
        "status_cancelled": "Operation cancelled.",
        "status_cleared": "Data cleared.",
        "status_rows_cleared": "Rows cleared, columns kept.",
        "status_data_cleared_cancelled": "Data clear cancelled.",
        "status_deletion_cancelled": "Deletion cancelled.",
        "status_column_deletion_cancelled": "Column deletion cancelled.",
        "status_no_rows_to_select": "No rows to select.",
        "status_selected_columns": "Selected column(s): {columns}.",
        "status_importing": "Importing {format}...",
        "status_exporting": "Exporting {format}...",
        "status_kml_settings_saved": "KML settings saved.",
        "status_kml_settings_cancelled": "KML settings cancelled.",
        "status_dxf_settings_saved": "DXF settings saved.",
        "status_dxf_settings_cancelled": "DXF settings cancelled.",

        # --- Actions (Undo, Redo, etc.) ---
        "action_dev_info": "Developer Info",
        "action_find": "Find",
        "action_copy": "Copy",
        "action_paste": "Paste",
        "action_undo": "Undo",
        "action_redo": "Redo",

        # --- Import Group ---
        "import_group_title": "Import Data",
        "import_mode_label": "Import Mode:",
        "import_mode_replace": "Replace Data",
        "import_mode_append": "Append to Data",
        "import_mode_tooltip": "Replace Data: Deletes existing data and imports new data\nAppend to Data: Adds new data to existing data",
        "import_confirm_append_title": "Confirm Append Data",
        "import_confirm_append_text": "New data will be appended to the existing {count} points. Do you want to continue?",
        "import_dialog_title": "Import {format} Files",

        # --- Export Group ---
        "export_group_title": "Export Data",
        "export_all_button_text": "Export All",
        "export_all_tooltip": "Export data to all formats in a new folder with date and time",
        "export_no_data_title": "No Data",
        "export_no_data_text": "There is no data to export.",
        "export_all_formats_title": "Select Main Export Folder",
        "export_all_info_title": "Export All",
        "export_all_info_text": "Data will be exported to the folder:\n{path}",
        "export_error_folder_exists_title": "Export Error",
        "export_error_folder_exists_text": "The folder '{folder_name}' already exists in '{path}'.",
        "export_error_folder_create_title": "Folder Creation Error",
        "export_error_folder_create_text": "Could not create the export folder:\n{path}\n{error}",
        "export_dialog_title": "Save Data as {format}",
        "export_results_dialog_title": "Save Search Results",
        "export_results_success_title": "Search Results Export Successful",
        "export_results_success_text": "Successfully exported {count} rows to:\n\n{filename}\n\nFormat: {format}",
        "export_results_error_title": "Export Error",
        "export_results_error_text": "Could not export search results:\n{error}",
        "export_pdf_error_title": "PDF Export Failed",
        "export_pdf_error_text": "Could not export the file as PDF:\n{error}\n\nThe results have been saved as a CSV file instead.",

        # --- Table & Data Operations ---
        "table_updated_status": "Table updated: {rows} rows, {columns} columns.",
        "table_cleared_status": "Table cleared or no data loaded.",
        "copy_status": "Copied {rows} row(s), {columns} column(s) to clipboard.",
        "paste_status": "Pasted {rows} rows, {columns} columns from clipboard at ({start_row},{start_col}).",
        "delete_rows_status": "Deleted {count} row(s).",
        "delete_rows_confirm_title": "Confirm Deletion",
        "delete_rows_confirm_text": "Are you sure you want to delete the {count} selected row(s)?",
        "delete_columns_status": "Deleted column(s): {columns}.",
        "delete_columns_not_found_status": "Column(s) '{columns}' not found in data for deletion.",
        "delete_columns_confirm_title": "Confirm Deletion",
        "delete_columns_confirm_text": "Are you sure you want to delete the selected column(s):\n{columns}?",
        "clear_data_confirm_title": "Confirm Clear",
        "clear_data_confirm_text": "Are you sure you want to clear all data?",
        "clear_rows_confirm_text": "Are you sure you want to clear all rows while keeping the columns?",
        "no_columns_selected_status": "No columns selected to delete.",
        "no_rows_selected_status": "No rows selected to delete.",
        "no_cells_selected_copy_status": "No cells selected to copy.",
        "no_cells_selected_cut_status": "No cells selected to cut.",
        "clipboard_empty_status": "Clipboard is empty.",
        "clipboard_parse_error_title": "Paste Error",
        "clipboard_parse_error_text": "Could not parse clipboard data:\n{error}",
        "undo_status": "Previous operation undone.",
        "redo_status": "Operation redone.",

        # --- Find/Search ---
        "find_dialog_title": "Find",
        "find_status_cleared": "Search filter cleared.",
        "find_status_found": "Found {count} matching rows for '{text}'",
        "find_status_not_found": "No results found for '{text}'",
        "show_all_status": "Displayed all data: {count} rows",
        "show_all_no_data_status": "No data to display",

        # --- Dialogs & Messages ---
        "error_saving_settings_title": "Error Saving Settings",
        "error_saving_settings_text": "Could not save settings to {filename}",
        "operation_in_progress_title": "Operation in Progress",
        "operation_in_progress_text": "Cannot start a new operation until the current one is finished.",
        "close_confirm_title": "Operation in Progress",
        "close_confirm_text": "An operation is currently running. Do you want to close anyway?",
        "worker_error_import_title": "Import Failed",
        "worker_error_export_title": "Export Failed",
        "worker_error_import_status": "Import failed - no data was imported",
        "worker_error_export_status": "Export failed - the file was not saved",
        "import_success_title": "Import Successful",
        "export_success_title": "Export Successful",

        # --- About/Info Dialog ---
        "about_dialog_title": "About {app_name}",
        "about_developer_name": "Mahmoud Kamal",
        "about_developer_specialization": "Surveying and Mapping Specialist",
        "about_developer_experience": "Survey Data Conversion",
        "about_developer_programming": "Development of Surveying Applications",
        "about_copyright": "© 2024 Mahmoud Kamal. All rights reserved.",
        "contact_whatsapp_error": "Could not open WhatsApp. Make sure you have an internet connection and the WhatsApp application.",
        "contact_facebook_error": "Could not open Facebook. Make sure you have an internet connection.",
        "kml_preview_button": "Preview in Google Earth",
        "kml_preview_tooltip": "Generate a temporary file and open it in Google Earth for preview before saving.",
        "kml_preview_validation_error_title": "Validation Error",
        "kml_preview_validation_error_text": "Cannot generate preview due to invalid settings:\n{error}",
        "kml_preview_error_title": "Preview Error",
        "kml_preview_error_text": "Could not open the file in Google Earth:\n{error}",

        # --- Tooltips ---
        "tooltip_sdr_import": "Sokkia/Topcon SDR33 Format",
        "tooltip_gsi_import": "Leica GSI Format (GSI-16)",
        "tooltip_dxf_import": "AutoCAD DXF (Points, Lines, Blocks)",
        "tooltip_kml_import": "Google Earth KML (Placemarks)",
        "tooltip_txt_import": "Delimited Text File",
        "tooltip_csv_import": "Comma Separated Values",
        "tooltip_excel_import": "Microsoft Excel (.xlsx, .xls)",
        "tooltip_sdr_export": "Export as Sokkia/Topcon SDR33",
        "tooltip_gsi_export": "Export as Leica GSI (GSI-16)",
        "tooltip_dxf_export": "Export as AutoCAD DXF",
        "tooltip_kml_export": "Export as Google Earth KML",
        "tooltip_txt_export": "Export as Text File",
        "tooltip_csv_export": "Export as Comma Separated Values",
        "tooltip_excel_export": "Export as Microsoft Excel (.xlsx)",
        "tooltip_dxf_settings": "DXF Settings",
        "tooltip_kml_settings": "KML Settings",
        "tooltip_swap_en_export": "If checked, Easting and Northing columns will be swapped in the output file.",
        "tooltip_delimiter_select": "Select field delimiter",
        "tooltip_find_button": "Advanced search in the table",
        "tooltip_show_all_button": "Show all data (clear filter)",
        "tooltip_clear_all_button": "Clear all data from the table",
        "tooltip_info_button": "Show developer info and contact methods"
    }
