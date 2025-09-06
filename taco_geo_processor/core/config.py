import sys
import os
import logging
import json
import shutil
from pathlib import Path
from typing import Any, Dict

# --- Application Constants ---
RESTART_CODE: int = 0  # Application restart exit code
# These will be loaded from UI settings
APP_NAME = "Survey Data Converter Pro"
APP_VERSION = "1.0.0"

from taco_geo_processor.core.ui_config import get_default_ui_settings

# --- Helper Functions for Paths ---
def get_base_dir() -> Path:
    """Gets the base path for bundled resources, works for dev and for PyInstaller."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)  # type: ignore
    else:
        # In development, assumes this file is at src/taco_geo_processor/core/
        # and the project root is 4 levels up.
        return Path(__file__).resolve().parent.parent.parent.parent

def get_settings_dir() -> Path:
    """Returns the path to the application's settings directory."""
    if getattr(sys, 'frozen', False):
        app_data_root = os.getenv('APPDATA')
        if not app_data_root:
            app_data_root = Path.home()
            logging.warning("APPDATA environment variable not found. Using home directory as fallback.")
        app_data_path = Path(app_data_root) / "MyCompany" / "SurveyConverter"
    else:
        # For development, use a local folder relative to the project root
        app_data_path = get_base_dir() / "settings"
    
    app_data_path.mkdir(parents=True, exist_ok=True)
    return app_data_path

# --- Settings Management Functions ---
def load_settings(filename: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    """Loads JSON settings from a file, handling defaults and copying from bundle if needed."""
    if not filename.parent.exists():
        try:
            filename.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(f"Failed to create settings directory {filename.parent}: {e}")
            return default.copy()

    if not filename.exists() and getattr(sys, 'frozen', False):
        source_file = get_base_dir() / 'settings' / filename.name
        if source_file.exists():
            try:
                shutil.copy2(source_file, filename)
                logging.info(f"Copied default settings from {source_file} to {filename}")
            except Exception as e:
                logging.error(f"Failed to copy default settings file: {e}")
        else:
            logging.warning(f"Default settings file not found in bundle: {source_file}")

    if filename.exists():
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            default_copy = default.copy()
            default_copy.update(loaded)
            logging.info(f"Loaded settings from {filename.name}")
            return default_copy
        except (json.JSONDecodeError, Exception) as e:
            logging.error(f"Error loading settings from {filename.name}: {e}. Using defaults.")
            return default.copy()
    else:
        logging.info(f"Settings file {filename.name} not found. Using defaults.")
        return default.copy()

def save_settings(settings_dict: Dict[str, Any], filename: Path) -> bool:
    """Saves settings to a JSON file."""
    if not filename.parent.exists():
        try:
            filename.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(f"Failed to create settings dir for {filename.name}: {e}")
            return False
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(settings_dict, f, indent=4, ensure_ascii=False)
        logging.info(f"Saved settings to {filename.name}")
        return True
    except (IOError, Exception) as e:
        logging.error(f"Error saving settings to {filename.name}: {e}", exc_info=True)
        return False

# --- Path Definitions ---
BASE_DIR = get_base_dir()
SETTINGS_DIR = get_settings_dir()
ICON_DIR = BASE_DIR / "icons"
LOG_FILE_NAME = 'survey_converter_pyside6.log'

# --- Environment and Profile ---
ENV = 'production'

# --- Settings File Paths ---
PROFILE_SETTINGS_FILE = SETTINGS_DIR / 'profiles' / f'{ENV}.json'
WINDOW_SETTINGS_FILE = SETTINGS_DIR / 'window_settings.json'
UI_SETTINGS_FILE = SETTINGS_DIR / 'ui_settings.json'


# --- Load UI Settings ---
# Load UI configurations into a global variable for easy access
UI_CFG = load_settings(UI_SETTINGS_FILE, default=get_default_ui_settings())

# --- Update dynamic constants from loaded settings ---
APP_NAME = UI_CFG.get("app_title", APP_NAME)
APP_VERSION = UI_CFG.get("app_version", APP_VERSION)


# --- Ensure Directories Exist (for dev mode) ---
# Note: Do NOT create ICON_DIR automatically here. Icon directory creation was
# causing the app to create the icons folder on each run in development.
# If icons need to be generated, handle that explicitly at install time or
# via a controlled startup flag in the main application.

# --- Format and UI Constants ---
EXPORT_FORMAT_EXTENSIONS = {
    'CSV': '.csv', 'Excel': '.xlsx', 'TXT': '.txt', 'GSI': '.gsi',
    'SDR33': '.sdr', 'DXF': '.dxf', 'KML': '.kml', 'KMZ': '.kmz'
}
DXF_COLOR_MODES = ['By Layer (Recommended)', 'By Entity']
DEFAULT_DXF_COLOR_MODE = 'By Layer (Recommended)'
DEFAULT_ICON_SIZE = 25
TXT_DELIMITERS = ['Tab (\t)', 'Comma (,)', 'Semicolon (;)', 'Space ( )', 'Pipe (|)', 'Auto-detect']
DISPLAY_DELIMITER_TO_KEY = {
    'Tab (\t)': 'Tab',
    'Comma (,)': 'Comma',
    'Semicolon (;)': 'Semicolon',
    'Space ( )': 'Space',
    'Pipe (|)': 'Pipe',
    'Auto-detect': 'Auto-detect',
}

# --- Logging Configuration ---
def setup_logging(env: str = 'production', suppress_logs: bool | None = None):
    """Configures logging for the application.

    If `suppress_logs` is True (or the environment variable
    `SURVEY_CONVERTER_NO_LOG` is set to 1/true or `UI_CFG['no_logging']` is True),
    the function will disable logging entirely (no console output, no log file).
    """
    # Determine log suppression: explicit arg > env var > UI config
    if suppress_logs is None:
        env_flag = os.getenv('SURVEY_CONVERTER_NO_LOG', '').lower()
        # Check UI config and profile settings for no_logging
        profile_no_logging = False
        try:
            profile_cfg = load_settings(PROFILE_SETTINGS_FILE, default={})
            profile_no_logging = bool(profile_cfg.get('no_logging', False))
        except Exception:
            profile_no_logging = False

        suppress_logs = env_flag in ('1', 'true', 'yes') or UI_CFG.get('no_logging', False) or profile_no_logging

    if suppress_logs:
        # Disable all logging to prevent console output and file creation
        root_logger = logging.getLogger()
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
        # Prevent any logging calls from emitting below CRITICAL
        logging.disable(logging.CRITICAL)
        return

    log_level = logging.DEBUG if env == 'development' else logging.INFO
    log_file = SETTINGS_DIR / LOG_FILE_NAME

    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Clear existing handlers to avoid duplication
    if logger.hasHandlers():
        logger.handlers.clear()

    # File handler - logs everything at the specified level
    try:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except (IOError, PermissionError) as e:
        # Fallback to console if file logging fails
        logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s (File logging failed)')
        logging.error(f"Could not set up file logger at {log_file}: {e}")
        return

    # Console handler - logs INFO and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logging.info(f"--- {APP_NAME} V{APP_VERSION} Started (Profile: {env.upper()}) ---")
    logging.info(f"Logging to console (INFO+) and file '{log_file}' (DEBUG+)")

# Initial setup of logging
# Call without explicit suppress_logs so setup_logging checks env/UI_CFG for suppression
setup_logging(ENV, suppress_logs=None)

# --- Default Settings Functions ---

def get_default_profile_settings() -> Dict[str, Any]:
    """Provides default settings for a profile."""
    return {
        "dxf": {
            "layer_name": "Survey_Export",
            "color_mode": "By Layer",
            "use_code_as_layer": True,
            "dxf_line_layer_prefix": "LINE_",
            "dxf_poly_layer_prefix": "POLY_",
            "export_points": True,
            "export_lines": True,
            "export_polygons": True,
            "export_as_blocks": False,
            "point_style": "square_cross",
            "point_size": 2.0,
            "line_connection_logic_key": "by_code",
            "custom_line_grouping_column": "Code",
            "sort_points_in_line_group": True,
            "export_options": [
                "Point Number",
                "Elevation"
            ],
            "text_layer_prefix": "Text_",
            "text_rotation": 0.0,
            "point_color": "#ff0000",
            "line_color": "#00ff00",
            "poly_color": "#0000ff",
            "Point_Number_height": 0.2,
            "Point_Number_offset": 0.3,
            "Point_Number_color": "#e54ce5",
            "Description_height": 0.2,
            "Description_offset": -0.5,
            "Description_color": "#00aaff",
            "Elevation_height": 0.15,
            "Elevation_offset": -0.8,
            "Elevation_color": "#0055ff",
            "Code_height": 0.15,
            "Code_offset": 0.8,
            "Code_color": "#ff0000"
        },
        "kml": {
            "name": "Survey Export",
            "kml_format": "KML",
            "zone_number": 36,
            "zone_letter": "N",
            "open_after_save": False,
            "geometry_type": [
                "Point",
                "Line",
                "Polygon"
            ],
            "icon_url": "http://maps.google.com/mapfiles/kml/paddle/red-square.png",
            "scale": 1.5,
            "color": "ff0000ff",
            "label_content": "Code",
            "label_scale": 1.2,
            "label_color": "ffffffff",
            "line_connection_logic_key": "by_code",
            "custom_line_grouping_column": "Code",
            "sort_points_in_line_group": True,
            "line_width": 3,
            "line_color": "ff0000ff"
        }
    }

# --- Load Profile Settings ---
PROFILE_CFG = load_settings(PROFILE_SETTINGS_FILE, default=get_default_profile_settings())


def check_proj_data() -> tuple[bool, str]:
    """Check whether PROJ/pyproj resource files (proj.db or grid files) are available.

    Returns (available: bool, message: str).
    This is a non-raising helper so callers can show non-blocking warnings to users.
    """
    try:
        # Import lazily to avoid making pyproj a hard import at module load if not needed
        import pyproj
        import os
        data_dir = None
        
        try:
            # Try different methods to get the data directory based on pyproj version
            # Use getattr to avoid static analysis issues
            get_data_dir_func = getattr(pyproj, 'get_data_dir', None)
            if get_data_dir_func and callable(get_data_dir_func):
                data_dir = get_data_dir_func()
            else:
                # Try accessing datadir module
                try:
                    datadir_module = getattr(pyproj, 'datadir', None)
                    if datadir_module:
                        get_data_dir_func = getattr(datadir_module, 'get_data_dir', None)
                        if get_data_dir_func and callable(get_data_dir_func):
                            data_dir = get_data_dir_func()
                except (AttributeError, ImportError):
                    pass
            
            # If still no data_dir, try environment variable fallback
            if not data_dir:
                data_dir = os.environ.get('PROJ_LIB')
                
        except Exception:
            # If pyproj can't return a data dir, fall through to not-available
            data_dir = None

        if not data_dir:
            return False, "pyproj data directory not set"
        
        # Ensure data_dir is a string
        if not isinstance(data_dir, (str, os.PathLike)):
            return False, f"Invalid data directory type: {type(data_dir)}"

        p = Path(data_dir)
        # Check for proj.db which indicates installed resources
        if (p / 'proj.db').exists():
            return True, f"proj.db found in {p}"

        # Search for common grid/resource file types
        for root, dirs, files in os.walk(p):
            for fn in files:
                if fn.lower().endswith(('.tif', '.gsb', '.gtx', '.dat')):
                    return True, f"PROJ resource files found under {p}"

        return False, f"No PROJ resource files found under {p}"
    except Exception as e:
        logging.debug(f"check_proj_data error: {e}", exc_info=True)
        return False, f"Error checking pyproj data: {e}"
