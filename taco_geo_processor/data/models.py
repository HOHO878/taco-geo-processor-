import pandas as pd
from PySide6.QtCore import Qt, QModelIndex, QSortFilterProxyModel
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QStandardItem
from PySide6.QtCore import QAbstractTableModel
from typing import Optional
import logging
from taco_geo_processor.processing import data_processing as dp

class HistoryManager:
    """Manages the undo and redo history for the application"""
    def __init__(self, max_steps=50):
        super().__init__()
        self.max_steps = max_steps
        self.history = []  # List of previous data states
        self.future = []   # List of data states that have been undone
        
    def push(self, data_df):
        """Adds a new state to the history"""
        # Do not store empty states unless it's the first state
        if data_df.empty and not self.history:
            return
        
        # Add a copy of the current data to the history
        self.history.append(data_df.copy())
        # Trim the history if it exceeds the maximum limit
        if len(self.history) > self.max_steps:
            self.history.pop(0)
        # Clear the redo future when a new state is added
        self.future.clear()
        
    def undo(self):
        """Restores the previous state"""
        if not self.history:
            return None
        
        # Move the current state to the redo future
        current_state = self.history.pop()
        self.future.append(current_state)
        
        # Return the previous state if it exists
        return self.history[-1] if self.history else None
        
    def redo(self):
        """Restores the future state after an undo"""
        if not self.future:
            return None
        
        # Move the state from the future to the history
        next_state = self.future.pop()
        self.history.append(next_state)
        return next_state
        
    def clear(self):
        """Clears all history"""
        self.history.clear()
        self.future.clear()
        
    def can_undo(self):
        """Determines if undo is possible"""
        return len(self.history) > 1
        
    def can_redo(self):
        """Determines if redo is possible"""
        return len(self.future) > 0

class EfficientTableModel(QAbstractTableModel):
    """
    An efficient table model that uses a Pandas DataFrame as a database.
    Supports direct editing of data in the table.
    """
    MIN_ROWS = 10
    MIN_COLS = 6
    # Use the standard point column names from data_processing
    DEFAULT_COL_NAMES = [dp.COL_PT, dp.COL_E, dp.COL_N, dp.COL_Z, dp.COL_CODE, dp.COL_DESC]

    def __init__(self, data_df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        if data_df is not None and not data_df.empty:
            self._data_df = data_df
        else:
            self._data_df = pd.DataFrame(columns=pd.Index(self.DEFAULT_COL_NAMES))  # type: ignore[arg-type]
        self._ensure_minimum_shape()

    def _ensure_minimum_shape(self):
        # Ensure at least MIN_ROWS and MIN_COLS
        if self._data_df.shape[1] < self.MIN_COLS:
            for i in range(self._data_df.shape[1], self.MIN_COLS):
                self._data_df[f"Column {i+1}"] = ""
        if self._data_df.shape[0] < self.MIN_ROWS:
            extra_rows = self.MIN_ROWS - self._data_df.shape[0]
            empty_rows = pd.DataFrame("", index=range(extra_rows), columns=self._data_df.columns)
            self._data_df = pd.concat([self._data_df, empty_rows], ignore_index=True)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid(): return 0
        return max(len(self._data_df), self.MIN_ROWS)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid(): return 0
        return max(len(self._data_df.columns), self.MIN_COLS)

    def data(self, index, role=Qt.DisplayRole):  # type: ignore[attr-defined]
        if not index.isValid(): 
            return None
        row, col = index.row(), index.column()

        if role == Qt.DisplayRole or role == Qt.EditRole:  # type: ignore[attr-defined]
            try:
                if row < len(self._data_df) and col < len(self._data_df.columns):
                    value = self._data_df.iat[row, col]
                    return "" if pd.isna(value) else str(value)
                else:
                    return ""
            except (IndexError, KeyError) as e:
                logging.debug(f"Error accessing data at ({row}, {col}): {e}")
                return ""

        if role == Qt.ToolTipRole:  # type: ignore[attr-defined]
            try:
                if row < len(self._data_df) and col < len(self._data_df.columns):
                    value = self._data_df.iat[row, col]
                    return str(value)
                else:
                    return ""
            except (IndexError, KeyError):
                return ""
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # type: ignore[attr-defined]
        if role == Qt.DisplayRole:  # type: ignore[attr-defined]
            if orientation == Qt.Orientation.Horizontal:
                if section < len(self._data_df.columns):
                    return str(self._data_df.columns[section])
                elif section < self.MIN_COLS:
                    return f"Column {section+1}"
            elif orientation == Qt.Orientation.Vertical:
                return str(section + 1)
        return None

    def flags(self, index):
        if not index.isValid(): return Qt.ItemFlag.NoItemFlags  # type: ignore[attr-defined]
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable  # type: ignore[attr-defined]

    def setData(self, index, value, role=Qt.EditRole):  # type: ignore[attr-defined]
        if not index.isValid() or role != Qt.EditRole:  # type: ignore[attr-defined]
            return False
        row, col = index.row(), index.column()
        if col >= len(self._data_df.columns):
            return False
        column_name = self._data_df.columns[col]
        try:
            current_val = self._data_df.iat[row,col]
            # Check if value actually changed to avoid unnecessary signals
            if str(current_val if not pd.isna(current_val) else "") == str(value):
                return False

            # Data type conversion based on column name
            if column_name in [dp.COL_E, dp.COL_N, dp.COL_Z]:
                self._data_df.iat[row, col] = float(value) if value else pd.NA
            elif column_name == dp.COL_PT:
                if value == "": self._data_df.iat[row, col] = pd.NA
                else:
                    try: self._data_df.iat[row, col] = int(value) # Try int for Point ID
                    except ValueError: self._data_df.iat[row, col] = str(value) # Fallback to string
            else:
                self._data_df.iat[row, col] = str(value) if value else ""

            # Emit signal for entire row to improve performance
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole])  # type: ignore[attr-defined]
            logging.debug(f"DataFrame updated at ({row},{column_name}) to '{self._data_df.iat[row,col]}'")
            return True
        except (ValueError, TypeError) as e:
            logging.warning(f"Could not convert/set cell ({row},{column_name}) with value '{value}': {e}")
            return False

    def data_df(self):
        """Returns the underlying Pandas DataFrame."""
        return self._data_df

    def set_data_df(self, new_df: pd.DataFrame):
        """
        Updates the entire model with new DataFrame data.
        Preserves any extra columns (e.g., Longitude/Latitude) while ensuring
        the standard columns exist. Cleans types only for known columns.
        """
        try:
            standard_cols = self.DEFAULT_COL_NAMES.copy()
            if new_df is not None and not new_df.empty:
                df = new_df.copy()
                # Ensure all standard columns exist
                for col in standard_cols:
                    if col not in df.columns:
                        df[col] = "" if col in [dp.COL_PT, dp.COL_CODE, dp.COL_DESC] else pd.NA
            else:
                df = pd.DataFrame(columns=pd.Index(standard_cols))  # type: ignore[arg-type]

            # Type cleaning only for known standard columns
            for col in [dp.COL_E, dp.COL_N, dp.COL_Z]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            for col in [dp.COL_PT, dp.COL_CODE, dp.COL_DESC]:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace({'nan': '', 'None': ''}, regex=False).fillna('')

            # Update the model (keep all columns including extra ones)
            self.beginResetModel()
            self._data_df = df
            self._ensure_minimum_shape()
            self.endResetModel()

            logging.info(f"Model updated with DataFrame: {len(df)} rows, {len(df.columns)} columns")

        except Exception as e:
            logging.error(f"Error in set_data_df: {e}")
            self.beginResetModel()
            self._data_df = pd.DataFrame(columns=pd.Index(self.DEFAULT_COL_NAMES))  # type: ignore[arg-type]
            self._ensure_minimum_shape()
            self.endResetModel()

    def clear_data(self, keep_columns=False):
        """Clears the data from the model with an option to keep the columns."""
        if keep_columns and not self._data_df.empty:
            # Keep columns, remove all rows
            self.beginResetModel()
            self._data_df = pd.DataFrame(columns=self._data_df.columns)
            self._ensure_minimum_shape()
            self.endResetModel()
        else:
            self.beginResetModel()
            self._data_df = pd.DataFrame(columns=pd.Index(self.DEFAULT_COL_NAMES))  # type: ignore[arg-type]
            self._ensure_minimum_shape()
            self.endResetModel()

    def horizontalHeaderLabels(self):
        """Returns the horizontal header labels."""
        return list(self._data_df.columns)

class CustomSortFilterProxyModel(QSortFilterProxyModel):
    """
    A custom proxy model for filtering and sorting data in a QTableView.
    Supports filtering based on specific columns.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_columns_indices = []  # List to store indices of columns to search in
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)  # Default to case-insensitive filtering
        self.setFilterKeyColumn(-1)  # Default to searching all columns
        logging.info("CustomSortFilterProxyModel initialized")

    def setFilterByColumns(self, column_names_to_search: list):
        """
        Sets the model to search in specific columns based on their names.
        """
        self._filter_columns_indices = [] # Clear previous column filters
        source_model = self.sourceModel()
        if not source_model or not hasattr(source_model, 'columnCount') or not hasattr(source_model, 'headerData'):
            self.invalidateFilter(); return
        
        if column_names_to_search:
            # Get all header names from the source model
            all_source_headers = [source_model.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) for i in range(source_model.columnCount())]
            for col_name in column_names_to_search:
                try:
                    # Find the index of the column name in the source model
                    idx = all_source_headers.index(col_name)
                    self._filter_columns_indices.append(idx)
                except ValueError:
                    logging.warning(f"Filter column '{col_name}' not found in source model headers.")
            
            if not self._filter_columns_indices:
                # If no valid columns were found, set filterKeyColumn to -2 to disable filtering
                self.setFilterKeyColumn(-2)
        else:
            # If no columns specified, search all columns (filterKeyColumn = -1)
            self.setFilterKeyColumn(-1)
            
        self.invalidateFilter() # Invalidate filter to re-apply it

    def filterAcceptsRow(self, source_row, source_parent_index):
        """
        Checks if a specific row (from the source model) is accepted by the filter.
        """
        regex = self.filterRegularExpression()
        if not regex.pattern(): # If no pattern is set, all rows are accepted
            return True
            
        model = self.sourceModel()
        if not model: return True # Should not happen if model is set correctly
        
        columns_to_iterate = []
        # Determine which columns to check based on filterKeyColumn setting
        if self.filterKeyColumn() == -1: # Search all columns
            columns_to_iterate = range(model.columnCount(source_parent_index))
        elif self.filterKeyColumn() >= 0: # Search a specific column
            columns_to_iterate = [self.filterKeyColumn()]
        elif self._filter_columns_indices: # Search a pre-defined list of columns
             columns_to_iterate = self._filter_columns_indices
             
        # Iterate through the determined columns
        for col_idx in columns_to_iterate:
            source_index = model.index(source_row, col_idx, source_parent_index) # Get index for the cell
            if source_index.isValid():
                cell_data_str = model.data(source_index, Qt.ItemDataRole.DisplayRole) # Get cell data as string
                if cell_data_str is not None and regex.match(str(cell_data_str)).hasMatch():
                    return True # If any cell matches the regex, accept the row
                    
        return False # If no cell in the specified columns matched

    def lessThan(self, source_left: QModelIndex, source_right: QModelIndex) -> bool:
        """
        Sorting has not been implemented yet. Always returns False.
        Can be extended to support sorting based on cell content.
        """
        return False
