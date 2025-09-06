from PySide6.QtCore import QObject, Signal, Slot
import pandas as pd
import logging
from taco_geo_processor.processing import data_processing as dp
from pathlib import Path
import openpyxl
from typing import Sequence, cast, Any
from taco_geo_processor.core import config
from taco_geo_processor.core.exceptions import TacoBaseException, FileProcessingError, DataValidationError, ConfigurationError
import os

class Worker(QObject):
    """
    Works in a separate thread to perform large import and export operations.
    Emits signals for progress, completion, or errors.
    """
    finished = Signal(object, str, str) # Result data, summary message, representative path
    error = Signal(str, str) # Error message, context
    progress = Signal(int, str) # Percentage, message

    def __init__(self, task_type, file_paths, fmt, column_order_str=None, export_settings=None, data_to_export=None, import_mode="replace", existing_data=None):
        super().__init__()
        self.task_type = task_type
        self.file_paths = file_paths
        self.fmt = fmt
        self.column_order_str = column_order_str
        self.export_settings = export_settings
        self.data_to_export = data_to_export
        self.import_mode = import_mode
        self.existing_data = existing_data

    def run(self):
        try:
            if self.task_type == 'import':
                self._run_import()
            elif self.task_type == 'export':
                self._run_export()
        except TacoBaseException as e:
            logging.error(f"Worker caught a known application error: {e}")
            self.error.emit(str(e), self.task_type)
        except Exception as e:
            logging.exception("Worker encountered an unexpected error.")
            self.error.emit(f"An unexpected error occurred: {e}", self.task_type)

    def _is_text_row(self, fields, threshold=0.6):
        """Checks if the row contains more text than numbers"""
        if isinstance(fields, pd.Series):
            if fields.dropna().empty:
                return False
        elif not fields:
            return False
        
        text_count = 0
        total_valid_fields = 0
        
        for field in fields:
            field_str = str(field).strip()
            # Ignore empty values from pandas
            if pd.isna(field) or field_str == '' or field_str.lower() in ['nan', 'none', '']:
                continue
            total_valid_fields += 1
            # Check if the field is not a number
            try:
                # Ignore values that contain special characters like + or - at the beginning only
                clean_str = field_str.replace('+', '', 1).replace('-', '', 1)
                if clean_str.replace('.', '', 1).replace('e', '', 1).replace('E', '', 1).isdigit():
                    # If we get here, it means the field is numeric
                    pass
                else:
                    # If we get here, it means the field is text
                    text_count += 1
            except (ValueError, TypeError):
                # If we get here, it means the field is text
                text_count += 1
        
        # If there are no valid fields, consider the row as text
        if total_valid_fields == 0:
            return True
        
        # Improved detection: if more than 50% of the fields are text, consider the row as column headers
        text_ratio = text_count / total_valid_fields
        is_text_row = text_ratio > threshold
        
        # Add logging for diagnostics
        if total_valid_fields > 0:
            logging.debug(f"Row analysis: {text_count}/{total_valid_fields} text fields ({text_ratio:.2f} ratio), threshold={threshold}, is_text={is_text_row}")
        
        return is_text_row

    def _run_import(self):
        """Execute the import, handling potential errors gracefully."""
        dfs = []
        total_files = len(self.file_paths)
        self.progress.emit(0, f"Starting import of {total_files} file(s)...")

        for file_idx, file_path in enumerate(self.file_paths, 1):
            progress_percent = int((file_idx - 1) / total_files * 100)
            path_obj = Path(file_path)
            file_name = path_obj.name
            self.progress.emit(progress_percent, f"Importing file {file_idx}/{total_files}: {file_name}")
            
            try:
                fmt = self.fmt.upper()
                df = None
                if fmt in ('CSV', 'TXT'):
                    encoding = dp.detect_encoding(path_obj)
                    delimiter = dp.sniff_delimiter(path_obj, encoding)
                    skiprows, _, _ = dp.sniff_header_and_skiprows(path_obj, encoding, delimiter)
                    
                    additional_skip = 0
                    if skiprows == 0:
                        with open(path_obj, 'r', encoding=encoding, errors='ignore') as f:
                            first_line = f.readline().strip()
                            if first_line and self._is_text_row([field.strip() for field in first_line.split(delimiter)]):
                                additional_skip = 1
                    
                    total_skiprows = skiprows + additional_skip
                    
                    names = [col.strip() for col in self.column_order_str.split(',')] if self.column_order_str and self.column_order_str != "Auto-detect Columns" else None
                    df = pd.read_csv(path_obj, encoding=encoding, delimiter=delimiter, skiprows=total_skiprows, header=None, names=names, dtype=str)

                elif fmt == 'EXCEL':
                    df = pd.read_excel(path_obj, header=None, dtype=str, engine='openpyxl')

                elif fmt == 'DXF':
                    df = dp.read_dxf_file(path_obj)
                elif fmt == 'KML':
                    df = dp.read_kml_file(path_obj, self.export_settings or {})
                elif fmt == 'GSI':
                    df = dp.read_gsi_file(path_obj)
                elif fmt == 'SDR33':
                    df = dp.read_sdr33_file(path_obj)
                else:
                    raise ConfigurationError(f"Unsupported import format: {self.fmt}")

                if df is None or df.empty:
                    logging.warning(f"No data was extracted from {file_name}.")
                    continue

                df = dp.normalize_columns(df, self.column_order_str)
                dfs.append(df)

            except (IOError, FileNotFoundError) as e:
                raise FileProcessingError(f"Cannot read file '{file_name}': {e}") from e
            except (pd.errors.ParserError, ValueError, IndexError) as e:
                raise DataValidationError(f"Invalid data format in '{file_name}': {e}") from e
            except Exception as e:
                raise FileProcessingError(f"An unexpected error occurred while processing '{file_name}': {e}") from e

        if not dfs:
            raise DataValidationError("No data could be imported from the selected file(s).")

        if len(dfs) > 1:
            self.progress.emit(95, f"Merging {len(dfs)} file(s)...")
        
        result_df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]

        if self.import_mode == "append" and self.existing_data is not None and not self.existing_data.empty:
            self.progress.emit(98, "Appending to existing data...")
            result_df = pd.concat([self.existing_data, result_df], ignore_index=True).fillna('')
            new_points = len(result_df) - len(self.existing_data)
            success_message = f"Successfully appended {new_points} points. Total points: {len(result_df)}."
        else:
            total_points = len(result_df)
            success_message = f"Import successful! {total_points} points were imported from {len(self.file_paths)} file(s)."

        self.progress.emit(100, "Import finished")
        self.finished.emit(result_df, success_message, str(self.file_paths[0]))

    def _run_export(self):
        """Execute the export, handling potential errors gracefully."""
        if self.data_to_export is None or self.data_to_export.empty:
            raise DataValidationError("No data available to export.")

        file_path = Path(self.file_paths[0])
        fmt = self.fmt.upper()
        total_points = len(self.data_to_export)
        self.progress.emit(10, f"Starting export to {fmt}...")
        self.progress.emit(20, f"Preparing {total_points} points...")

        try:
            # Apply requested column order for text-like formats
            df_to_write = self.data_to_export
            if fmt in ('CSV', 'TXT', 'EXCEL'):
                order_str = (self.column_order_str or '').strip()
                logging.info(f"Requested export order: '{order_str}'")
                if order_str and order_str not in ("Auto-detect Columns", "All Columns (Original Order)"):
                    requested_raw = [c.strip() for c in order_str.split(',') if c.strip()]
                    # Build case-insensitive mapping for existing columns
                    existing_cols = list(df_to_write.columns)
                    lower_to_actual = {c.lower(): c for c in existing_cols}
                    # Build alias mapping to standard names
                    alias_to_standard = {alias.lower(): std for std, aliases in dp.COLUMN_ALIASES.items() for alias in aliases}
                    resolved_order = []
                    for req in requested_raw:
                        # exact
                        if req in existing_cols:
                            resolved_order.append(req)
                            continue
                        # case-insensitive
                        low = req.lower()
                        if low in lower_to_actual:
                            resolved_order.append(lower_to_actual[low])
                            continue
                        # alias to standard
                        std = alias_to_standard.get(low)
                        if std and std in lower_to_actual.values():
                            resolved_order.append(std)
                            continue
                        # skip unknown
                        logging.debug(f"Export order: unknown column '{req}', skipping")
                    # Only use the resolved columns, preserving the requested order.
                    if resolved_order:
                        # Create a new DataFrame with only the selected columns in the specified order.
                        df_to_write = df_to_write[resolved_order]
                        logging.info(f"Export columns order applied: {resolved_order}")
                    else:
                        logging.info("Requested export order had no matching columns; using original order.")

            if fmt == 'CSV':
                delimiter = self.export_settings.get('txt_delimiter', ',') if self.export_settings else ','
                df_to_write.to_csv(file_path, index=False, header=False, sep=delimiter, encoding='utf-8-sig')
            elif fmt == 'EXCEL':
                df_to_write.to_excel(file_path, index=False, header=False, engine='openpyxl')
            elif fmt == 'TXT':
                delimiter = self.export_settings.get('txt_delimiter', '\t') if self.export_settings else '\t'
                df_to_write.to_csv(file_path, index=False, header=False, sep=delimiter, encoding='utf-8-sig')
            elif fmt == 'DXF':
                dp.export_dxf_file(self.data_to_export, file_path, self.export_settings or {})
            elif fmt == 'KML':
                dp.export_kml_file(self.data_to_export, file_path, self.export_settings or {})
                if self.export_settings and self.export_settings.get('open_after_save', False):
                    os.startfile(file_path)
            elif fmt == 'GSI':
                dp.export_gsi_file(self.data_to_export, file_path)
            elif fmt == 'SDR33':
                order = 'ENZ' if self.export_settings and self.export_settings.get('swap_e_n_for_sdr', False) else 'NEZ'
                dp.export_sdr33_file(self.data_to_export, file_path, order)
            else:
                raise ConfigurationError(f"Unsupported export format: {fmt}")

            self.progress.emit(100, f"Successfully exported to {fmt}")
            file_size = file_path.stat().st_size / 1024  # KB
            size_str = f"{file_size:.1f} KB" if file_size < 1024 else f"{file_size/1024:.2f} MB"
            success_message = f"Exported {total_points} points to {file_path.name} ({size_str})."
            self.finished.emit(None, success_message, str(file_path))

        except (IOError, PermissionError) as e:
            raise FileProcessingError(f"Could not write to file '{file_path.name}'. It may be open or you may lack permissions: {e}") from e
        except Exception as e:
            raise FileProcessingError(f"An unexpected error occurred during {fmt} export: {e}") from e

class ExportAllWorker(QObject):
    """
    Separate worker for exporting data to all specified formats at once.
    """
    # Define signals
    all_finished = Signal(str) # Signal emitted when all exports are done successfully
    all_error = Signal(str) # Signal emitted if any export fails
    file_progress = Signal(str, int, int) # Signal for progress: format name, current index, total formats

    def __init__(self, main_window_ref, formats_dict, base_path, base_filename, data_to_export):
        super().__init__()
        self.main_window_ref = main_window_ref
        self.formats_dict = formats_dict
        self.base_path = base_path
        self.base_filename = base_filename
        self.data_to_export = data_to_export

    def run(self):
        """Execute the export for all formats."""
        if self.data_to_export.empty:
            self.all_error.emit("No data to export.")
            return

        successful_exports, failed_exports = [], []
        formats_to_export = {k: v for k, v in self.formats_dict.items() if k != 'KMZ'}
        total_formats = len(formats_to_export)

        for idx, (format_name, extension) in enumerate(formats_to_export.items(), 1):
            try:
                self.file_progress.emit(format_name, idx, total_formats)
                file_path = self.base_path / f"{self.base_filename}{extension}"
                
                if format_name == 'CSV':
                    self.data_to_export.to_csv(file_path, index=False, header=False, encoding='utf-8-sig')
                elif format_name == 'Excel':
                    self.data_to_export.to_excel(file_path, index=False, header=False, engine='openpyxl')
                elif format_name == 'TXT':
                    self.data_to_export.to_csv(file_path, index=False, header=False, sep='\t', encoding='utf-8-sig')
                elif format_name == 'DXF':
                    dp.export_dxf_file(self.data_to_export, file_path, config.PROFILE_CFG.get('dxf', {}))
                elif format_name == 'KML':
                    kml_settings = config.PROFILE_CFG.get('kml', {}).copy()
                    kml_settings['kml_format'] = 'KML'
                    dp.export_kml_file(self.data_to_export, file_path, kml_settings)
                elif format_name == 'GSI':
                    dp.export_gsi_file(self.data_to_export, file_path)
                elif format_name == 'SDR33':
                    dp.export_sdr33_file(self.data_to_export, file_path, 'NEZ')
                
                successful_exports.append(format_name)
                logging.info(f"Export All: Successfully exported {format_name} to {file_path}")
            except Exception as e:
                failed_exports.append(format_name)
                logging.error(f"Export All: Failed to export {format_name}: {e}")

        if failed_exports:
            error_msg = f"{len(successful_exports)} formats exported successfully. Failed: {', '.join(failed_exports)}."
            self.all_error.emit(error_msg)
        else:
            success_msg = f"All {len(successful_exports)} formats exported successfully to: {self.base_path}"
            self.all_finished.emit(success_msg)
