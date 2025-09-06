import pandas as pd
import logging
import os
import re
import datetime
import csv
from pathlib import Path
import io
import xml.etree.ElementTree as ET
import zipfile
import gc
import functools
from typing import Optional, Dict, List
import numpy as np
import ezdxf
import ezdxf.recover
from ezdxf.filemanagement import readfile
import simplekml
import utm
import chardet
import webcolors # Used for color name parsing

# --- Dependency Handling ---
# Try to import optional libraries and log warnings if they are not found.
try:
    import ezdxf
    import ezdxf.recover
except ImportError:
    ezdxf = None
    logging.warning("ezdxf library not found in data_processing module. DXF functionality will be disabled.")

try:
    import simplekml
    import utm
except ImportError:
    simplekml = None
    utm = None
    logging.warning("simplekml and/or utm not found in data_processing module. KML functionality may be limited.")

try:
    import chardet
except ImportError:
    chardet = None
    logging.warning("chardet library not available in data_processing module.")

try:
    import webcolors # Used for color name parsing
except ImportError:
    webcolors = None
    logging.warning("webcolors library not found in data_processing module.")

try:
    import openpyxl
except ImportError:
    openpyxl = None
    logging.warning("openpyxl library not found in data_processing module. Excel functionality (.xlsx) will be disabled.")

try:
    from pyproj import CRS, Transformer
    from pyproj.exceptions import CRSError
    # Prefer TransformerGroup to pick the most accurate operation and inspect grids
    try:
        from pyproj.transformer import TransformerGroup
    except Exception:
        TransformerGroup = None
    try:
        from pyproj.aoi import AreaOfInterest
    except Exception:
        AreaOfInterest = None
except ImportError:
    CRS = None
    Transformer = None
    CRSError = None
    TransformerGroup = None
    AreaOfInterest = None
    logging.warning("pyproj library not found. Coordinate transformation will be disabled.")

# --- Constants related to data processing ---
# Standard column names used throughout the application
COL_PT = 'PT'
COL_E = 'Easting'
COL_N = 'Northing'
COL_Z = 'Elevation'
COL_CODE = 'Code'
COL_DESC = 'Description'
STANDARD_COLS = [COL_PT, COL_E, COL_N, COL_Z, COL_CODE, COL_DESC]

# Aliases for standard columns to support various input formats
COLUMN_ALIASES = {
    COL_PT: ['PT', 'POINT', 'P', 'POINTNUMBER', 'PN', 'STN', 'NAME', 'ID', 'POINT_ID', 'POINT_NO', 'NUMBER', 'رقم النقطة', 'الرقم'],
    COL_E: ['E', 'EAST', 'EASTING', 'X', 'COORDX', 'XCOORD', 'X_COORD', 'LON', 'LONGITUDE', 'خط الطول', 'شرق', 'س'],
    COL_N: ['N', 'NORTH', 'NORTHING', 'Y', 'COORDY', 'YCOORD', 'Y_COORD', 'LAT', 'LATITUDE', 'خط العرض', 'شمال', 'ص'],
    COL_Z: ['Z', 'ELEV', 'EL', 'ELEVATION', 'H', 'HEIGHT', 'COORDZ', 'ZCOORD', 'ALT', 'ALTITUDE', 'Z_COORD', 'RL', 'منسوب', 'ع'],
    COL_CODE: ['CODE', 'CD', 'COD', 'CODES', 'FEATURE', 'LAYER', 'STYLE', 'TYPE', 'MARKER', 'LINEID', 'LINE_ID', 'GROUP', 'كود', 'الرمز'],
    COL_DESC: ['DESCRIPTION', 'DESC', 'D', 'TEXT', 'NOTE', 'LABEL', 'INFO', 'COMMENT', 'REMARK', 'وصف', 'البيان', 'ملاحظات']
}

# Color mapping dictionaries for DXF and KML export settings
ACI_COLOR_MAP = { # Mapping from ACI color index to RGB tuple
    0: (0, 0, 0), 1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0), 4: (0, 255, 255),
    5: (0, 0, 255), 6: (255, 0, 255), 7: (255, 255, 255), 8: (128, 128, 128), 9: (192, 192, 192),
    10: (0, 0, 128), 30: (255, 128, 0), 40: (128, 0, 0), 50: (128, 128, 0), 60: (0, 128, 0),
    70: (0, 128, 128), 80: (0, 0, 128), 90: (128, 0, 128), 250: (80, 80, 80), 251: (100, 100, 100),
    252: (150, 150, 150), 253: (180, 180, 180), 254: (220, 220, 220), 255: (240, 240, 240),
    256: (128, 128, 128)  # ByLayer placeholder for DXF
}
COLOR_NAME_TO_ACI = { # Mapping from common color names to ACI index
    'red': 1, 'yellow': 2, 'green': 3, 'cyan': 4, 'blue': 5, 'magenta': 6, 'white': 7, 'black': 0,
    'gray': 8, 'grey': 8, 'lightgray': 9, 'lightgrey': 9, 'darkgray': 8, 'darkgrey': 8,
    'orange': 30, 'brown': 40, 'purple': 90, 'pink': 251, 'byblock': 0, 'bylayer': 256, 'none': 256, 'default': 7
}

COLOR_NAME_TO_KML = { # Mapping from common color names to KML's AABBGGRR format
    'red': 'ff0000ff', 'yellow': 'ff00ffff', 'green': 'ff00ff00', 'cyan': 'ffffff00', 'blue': 'ffff0000',
    'magenta': 'ffff00ff', 'white': 'ffffffff', 'black': 'ff000000', 'gray': 'ff808080', 'grey': 'ff808080',
    'lightgray': 'ffd3d3d3', 'lightgrey': 'ffd3d3d3', 'darkgray': 'ffa9a9a9', 'darkgrey': 'ffa9a9a9',
    'orange': 'ff00a5ff', 'brown': 'ff2a2aa5', 'purple': 'ff800080', 'pink': 'ffcbc0ff', 'none': '00000000', 'default': 'ffffffff'
}
DEFAULT_KML_ICON = "http://maps.google.com/mapfiles/kml/pushpin/wht-pushpin.png" # Default KML icon URL
DXF_POINT_STYLE_MAP = { # Mapping of DXF point styles (names to PDMODE values)
    "dot": 0, "circle_cross": 34, "circle_plus": 33, "square_cross": 66, "square_plus": 65,
    "square_circle_cross": 98, "square_circle_plus": 97,
}
CHUNK_SIZE_CSV = 50000 # Chunk size for reading CSV files to manage memory

# --- Helper Functions ---
def _rgb_to_aci(rgb_tuple, default_aci=7):
    """
    Converts an RGB tuple to the nearest ACI (AutoCAD Color Index) value.
    Uses a simple distance calculation algorithm to find the closest ACI color.
    """
    if not isinstance(rgb_tuple, (tuple, list)) or len(rgb_tuple) != 3:
        logging.error(f"Invalid RGB tuple format: {rgb_tuple}. Expected (R, G, B).")
        return default_aci
    # Check for exact matches first
    for aci, rgb_val in ACI_COLOR_MAP.items():
        if aci not in [0, 256] and rgb_val == rgb_tuple: return aci # Exact match found
    
    # If no exact match, find the closest ACI color
    closest_aci = default_aci
    min_dist = float('inf')
    for aci, aci_rgb in ACI_COLOR_MAP.items():
        if aci not in [0, 256]: # Exclude special codes
            # Calculate Euclidean distance squared between colors
            dist = sum((c1 - c2)**2 for c1, c2 in zip(rgb_tuple, aci_rgb))
            if dist < min_dist:
                min_dist = dist
                closest_aci = aci
    return closest_aci

def parse_aci_color(input_str, default=7):
    """
    Parses an ACI color input (number or name) and returns it as a numeric ACI value.
    Attempts to use the webcolors library to convert from color names or hex to RGB, then to ACI.
    """
    if not isinstance(input_str, str): input_str = str(input_str) # Ensure input is string
    input_str = input_str.strip().lower() # Normalize input
    if not input_str: return default # Return default if input is empty
    
    # Try parsing as integer ACI value
    try:
        aci = int(input_str)
        if 0 <= aci <= 256: return aci # Valid ACI range
    except ValueError: pass # Not an integer
    
    # Check common color name mappings
    if input_str in COLOR_NAME_TO_ACI: return COLOR_NAME_TO_ACI[input_str]
    
    # Try using webcolors if available
    if webcolors:
        try:
            rgb_tuple = None
            # Check if input is a hex color string
            if re.fullmatch(r"#?([0-9a-f]{6})", input_str): 
                rgb_tuple = webcolors.hex_to_rgb(input_str)
            else: # Otherwise, try parsing as color name
                rgb_tuple = webcolors.name_to_rgb(input_str)
            
            if rgb_tuple: # If RGB was successfully parsed
                aci = _rgb_to_aci(rgb_tuple, default_aci=default) # Convert RGB to closest ACI
                logging.debug(f"Converted '{input_str}' (RGB: {rgb_tuple}) to approximate ACI: {aci}")
                return aci
        except ValueError: pass # webcolors couldn't parse the input
        
    logging.warning(f"Invalid ACI color input: '{input_str}'. Using default ACI {default}.")
    return default # Return default if parsing failed

def parse_kml_color(input_str, default='ffffffff'):
    """
    Normalizes any color input (hex/name/ACI) into KML AABBGGRR by delegating to _get_kml_color_string.
    """
    try:
        return _get_kml_color_string(input_str, default_color=default)
    except Exception:
        logging.warning(f"Invalid KML color input: '{input_str}'. Using default {default}.")
        return default

def _get_kml_color_string(color_input, default_color='ffffffff'):
    """
    Robustly converts a color input (hex, name, ACI) into a valid KML AABBGGRR string.
    Handles #RRGGBB, #AARRGGBB, color names, and ACI indices.
    """
    if not isinstance(color_input, str):
        color_input = str(color_input)
    color_input = color_input.strip().lower()

    if not color_input:
        return default_color

    # Case 1: Already a valid KML-like string (8 hex chars)
    if re.fullmatch(r'[0-9a-f]{8}', color_input):
        return color_input

    # Case 2: Standard hex color #RRGGBB
    if color_input.startswith('#') and len(color_input) == 7:
        r, g, b = color_input[1:3], color_input[3:5], color_input[5:7]
        return f"ff{b}{g}{r}"

    # Case 3: Hex color #AARRGGBB
    if color_input.startswith('#') and len(color_input) == 9:
        a, r, g, b = color_input[1:3], color_input[3:5], color_input[5:7], color_input[7:9]
        return f"{a}{b}{g}{r}"

    # Case 4: Color name
    if webcolors:
        try:
            # Try direct name to KML mapping first
            if color_input in COLOR_NAME_TO_KML:
                return COLOR_NAME_TO_KML[color_input]
            # Fallback to webcolors parsing
            rgb = webcolors.name_to_rgb(color_input)
            return f"ff{rgb.blue:02x}{rgb.green:02x}{rgb.red:02x}"
        except ValueError:
            pass  # Not a known color name

    # Case 5: ACI color index
    try:
        aci_val = int(color_input)
        if aci_val in ACI_COLOR_MAP:
            r, g, b = ACI_COLOR_MAP[aci_val]
            return f"ff{b:02x}{g:02x}{r:02x}"
    except (ValueError, TypeError):
        pass

    logging.warning(f"Could not parse KML color '{color_input}'. Using default '{default_color}'.")
    return default_color

# --- Data Loading and Processing Functions ---
def detect_encoding(file_path: Path, sample_size=8192):
    """
    Attempts to detect the file encoding using a combination of direct trials (UTF-8, Windows-1256, etc.)
    and using the chardet library if available.
    """
    # List of common encodings to try first
    common_encodings = ['utf-8-sig', 'utf-8', 'windows-1256', 'iso-8859-6', 'cp1256', 'latin-1']
    for enc in common_encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                f.read(sample_size) # Read a sample to check if it works
            logging.info(f"Successfully detected encoding '{enc}' by trial for {file_path.name}.")
            return enc # Return the encoding if successful
        except (UnicodeDecodeError, UnicodeError, LookupError):
            continue # Try next encoding if error occurs
            
    # If common encodings fail and chardet is available, use it
    if not chardet:
        logging.warning("chardet library not available. Defaulting to 'utf-8' after common checks failed.")
        return 'utf-8' # Default if chardet is missing
        
    try:
        with open(file_path, 'rb') as f: raw_data = f.read(sample_size * 2) # Read a larger sample for chardet
        if not raw_data: return 'utf-8' # Return utf-8 for empty files
        
        result = chardet.detect(raw_data) # Detect encoding and confidence
        encoding = result['encoding']
        confidence = result.get('confidence', 0.0)
        logging.info(f"Chardet detected encoding: {encoding} with confidence {confidence:.2f} for {file_path.name}")
        
        # Return detected encoding if confidence is high, or fallback
        if encoding and confidence > 0.75:
            # Handle potential misdetections (e.g., Cyrillic misidentified as Arabic)
            if encoding.lower() in ['koi8-r', 'maccyrillic'] and any(c in common_encodings for c in ['windows-1256', 'iso-8859-6']):
                logging.warning(f"Chardet proposed {encoding} but might be Arabic. Trying common Arabic or utf-8 again.")
            else:
                return encoding # Return detected encoding if confidence is good
        return 'utf-8' # Default fallback if detection is poor or fails
        
    except FileNotFoundError:
        logging.error(f"File not found during encoding detection: {file_path.name}")
        raise
    except Exception as e:
        logging.error(f"Error detecting encoding for {file_path.name}: {e}", exc_info=True)
        return 'utf-8' # Return utf-8 on any other errors

def sniff_delimiter(file_path: Path, encoding='utf-8'):
    """
    Attempts to infer the delimiter used in a CSV file by examining the first few lines.
    Uses csv.Sniffer for this purpose.
    """
    try:
        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
            sample_lines = []
            # Read a sample of lines for sniffing
            for _i in range(50):
                line = f.readline()
                if not line: break # Stop if end of file
                stripped_line = line.strip()
                if stripped_line and not stripped_line.startswith('#'): # Ignore empty lines and comments
                    sample_lines.append(line)
                if len(sample_lines) >= 20: break # Stop after collecting enough lines
                
            if not sample_lines: return ',' # Default to comma if no sample lines found
            
            sample_text = "".join(sample_lines) # Join sample lines into a single string
            sniffer = csv.Sniffer()
            # Define delimiters to look for, including space if it's dominant
            common_delimiters = [',', '\t', ';', '|']
            if sample_text.count(' ') > sample_text.count(',') * 5 and \
               sample_text.count(' ') > sample_text.count('\t') * 5 and \
               sample_text.count(' ') > sample_text.count(';') * 5:
                common_delimiters.append(' ') # Add space as a delimiter if it's frequent
                
            try:
                # Use sniffer to determine the delimiter
                dialect = sniffer.sniff(sample_text, delimiters="".join(common_delimiters))
                if dialect.delimiter == ' ':
                     logging.info(f"Sniffed space as delimiter for {file_path.name}, using r'\\s+' for robust parsing.")
                     return r'\s+' # Use regex for space as delimiter for better handling
                logging.info(f"Sniffed delimiter: '{dialect.delimiter}' for {file_path.name}")
                return dialect.delimiter
            except csv.Error: # Handle cases where sniffer fails
                if ' ' in sample_text and all(d not in sample_text for d in [',', '\t', ';']):
                    logging.warning(f"csv.Sniffer failed. Assuming space delimiter (r'\\s+') for {file_path.name}.")
                    return r'\s+'
                logging.warning(f"csv.Sniffer could not determine delimiter for {file_path.name}. Defaulting to comma.")
                return ','
    except FileNotFoundError:
        logging.error(f"File not found during delimiter sniffing: {file_path.name}")
        raise
    except Exception as e:
        logging.warning(f"Could not sniff delimiter for {file_path.name}: {e}. Defaulting to comma.")
        return ','

def sniff_header_and_skiprows(file_path: Path, encoding, delimiter, num_preview_lines=30, comment_chars='#'):
    """
    Attempts to determine the number of rows to skip before the header and the line containing the header.
    Uses heuristic analysis of the nature of the lines (textual vs. numeric).
    """
    initial_skiprows = 0 # Default: skip 0 lines
    header_line_in_file = None # Line index in file where header was found
    header_names = None # List of header names
    
    try:
        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
            lines_for_sniffing_with_original_indices = []
            # Read lines up to a certain limit to find header
            for i, line_content in enumerate(f):
                if i >= num_preview_lines + 30: break # Limit lines read for performance
                
                stripped_line = line_content.strip()
                if not stripped_line: # If line is empty
                    if not lines_for_sniffing_with_original_indices: # If we haven't found any data yet
                        initial_skiprows = i + 1 # Assume this is a blank line to skip
                    continue # Skip empty lines
                    
                # Check if line starts with a comment character
                is_comment = any(stripped_line.startswith(char) for char in comment_chars) if comment_chars else False
                if is_comment:
                    if not lines_for_sniffing_with_original_indices: # If it's a comment before any data
                         initial_skiprows = i + 1 # Assume this is a comment line to skip
                    continue # Skip comment lines
                    
                lines_for_sniffing_with_original_indices.append((i, stripped_line)) # Store line index and content
                if len(lines_for_sniffing_with_original_indices) >= num_preview_lines:
                    break # Stop if we have enough preview lines
                    
            if not lines_for_sniffing_with_original_indices:
                logging.info(f"No data lines found for header sniffing in {file_path.name}. Skipping {initial_skiprows} lines.")
                return initial_skiprows, None, None # Return skip count and no header info
                
            # Analyze the collected lines to find the header
            for sample_idx, (original_file_line_idx, line_str) in enumerate(lines_for_sniffing_with_original_indices):
                potential_headers = [h.strip() for h in re.split(delimiter, line_str)] # Split line by delimiter
                if not all(ph for ph in potential_headers if ph): continue # Skip if line is mostly empty after split
                
                # Heuristic: A header line often contains mostly non-numeric fields.
                num_strings = sum(1 for h in potential_headers if not h.replace('.', '', 1).replace('-', '', 1).isdigit()) # Count non-numeric fields
                is_mostly_strings = (num_strings / len(potential_headers)) > 0.6 # Threshold for "mostly strings"
                
                # Heuristic: Check if the line BELOW the potential header looks like data (mostly numeric)
                has_data_like_row_below = False
                if sample_idx + 1 < len(lines_for_sniffing_with_original_indices):
                    _, next_line_str = lines_for_sniffing_with_original_indices[sample_idx + 1]
                    next_line_fields = [f.strip() for f in re.split(delimiter, next_line_str)]
                    if len(next_line_fields) == len(potential_headers): # If field counts match
                        num_numeric_next = sum(1 for f in next_line_fields if f.replace('.', '', 1).replace('-', '', 1).isdigit()) # Count numeric fields below
                        if num_numeric_next / len(next_line_fields) > 0.5: # Threshold for "mostly numeric"
                            has_data_like_row_below = True
                            
                # Heuristic: Check if field names match known column aliases
                match_score = sum(1 for ph_l in [ph.lower() for ph in potential_headers] if any(ph_l in [a.lower() for a in aliases_list] for aliases_list in COLUMN_ALIASES.values()))
                matches_aliases_well = (match_score / len(potential_headers)) > 0.5 if potential_headers else False
                
                # Determine if this line is likely the header
                if (is_mostly_strings and has_data_like_row_below) or matches_aliases_well:
                    header_line_in_file = original_file_line_idx # Record the file line number of the header
                    header_names = potential_headers # Store the identified header names
                    logging.info(f"Sniffed header at file line {header_line_in_file + 1}. Pandas will skip {header_line_in_file} lines and use header=0.")
                    return header_line_in_file, 0, header_names # Return skip count and header info
                    
    except FileNotFoundError:
        logging.error(f"File not found during header sniffing: {file_path.name}")
        raise
    except Exception as e_sniff:
        logging.warning(f"Error during header sniffing for {file_path.name}: {e_sniff}", exc_info=True)
        
    logging.info(f"No confident header sniffed for {file_path.name}. Pandas will skip {initial_skiprows} initial lines, header=None (or infer).")
    return initial_skiprows, None, None # Return skip count and no header info if sniffing failed

def normalize_columns(df: pd.DataFrame, column_order_str=None):
    """
    Renames and maps the columns in a DataFrame to the standard columns (PT, Easting, Northing, etc.)
    based on the extracted names and the desired order (if provided).
    """
    if df is None or df.empty: return pd.DataFrame()

    df_original = df.copy()

    # Check if columns are default integers (likely from header=None)
    is_headerless = all(isinstance(c, int) for c in df_original.columns)

    # Clean original column names (strip whitespace, ensure strings)
    df_original.columns = [str(col).strip() for col in df_original.columns]
    df_normalized = pd.DataFrame()

    # Create a mapping from original column name (lowercase) to its standard name
    original_cols_lower_to_original_case = {col.lower(): col for col in df_original.columns}
    current_col_to_std_map = {}

    # Populate the map by checking aliases if the file is not headerless
    if not is_headerless:
        for original_col in df_original.columns:
            for std_col_key, aliases in COLUMN_ALIASES.items():
                if original_col.lower() in [alias.lower() for alias in aliases]:
                    current_col_to_std_map[original_col] = std_col_key
                    break

    # --- Column reordering and selection ---
    if column_order_str and column_order_str not in ["Auto-detect Columns", "All Columns (Original Order)"]:
        desired_order_raw = [col.strip() for col in column_order_str.split(',')]
        used_original_cols = set()

        if is_headerless:
            # For headerless files, map by index based on the desired order
            for i, desired_col_name in enumerate(desired_order_raw):
                if i < len(df_original.columns):
                    original_col_idx = df_original.columns[i]
                    df_normalized[desired_col_name] = df_original[original_col_idx]
                    used_original_cols.add(str(original_col_idx))
                else:
                    # If desired order has more columns than the file, add empty ones
                    df_normalized[desired_col_name] = 0.0 if desired_col_name in [COL_E, COL_N, COL_Z] else ""
        else:
            # Logic for files with headers
            for desired_col_name_from_order in desired_order_raw:
                found_original_col = None
                if desired_col_name_from_order in STANDARD_COLS:
                    for orig_c, std_c_map_val in current_col_to_std_map.items():
                        if std_c_map_val == desired_col_name_from_order and orig_c not in used_original_cols:
                            found_original_col = orig_c
                            break
                if not found_original_col:
                    desired_lower = desired_col_name_from_order.lower()
                    if desired_lower in original_cols_lower_to_original_case:
                        potential_orig_col = original_cols_lower_to_original_case[desired_lower]
                        if potential_orig_col not in used_original_cols:
                            found_original_col = potential_orig_col
                
                if found_original_col and found_original_col in df_original.columns:
                    df_normalized[desired_col_name_from_order] = df_original[found_original_col]
                    used_original_cols.add(found_original_col)
                else:
                    df_normalized[desired_col_name_from_order] = 0.0 if desired_col_name_from_order in [COL_E, COL_N, COL_Z] else ""

        # Add any remaining original columns that weren't used
        for original_col in df_original.columns:
            if str(original_col) not in used_original_cols:
                if original_col not in df_normalized.columns:
                     df_normalized[original_col] = df_original[original_col]
                
    elif column_order_str == "All Columns (Original Order)":
        df_normalized = df_original.copy() # Just copy the original DataFrame
        
    else:  # Auto-detect column order
        processed_original_cols = set()
        # First, add standard columns in their standard order if found
        for std_col_target in STANDARD_COLS:
            original_col_found_for_std = None
            # Find the best match from original columns for this standard column
            for orig_c, mapped_std_c in current_col_to_std_map.items():
                if mapped_std_c == std_col_target and orig_c not in processed_original_cols:
                    original_col_found_for_std = orig_c
                    break
            if original_col_found_for_std:
                df_normalized[std_col_target] = df_original[original_col_found_for_std] # Assign to standard column name
                processed_original_cols.add(original_col_found_for_std)
                
        # Then, add any remaining original columns that were not mapped to standard columns
        for col_original in df_original.columns:
            if col_original not in processed_original_cols:
                if col_original not in df_normalized.columns: # Avoid overwriting if already mapped differently
                     df_normalized[col_original] = df_original[col_original]
                     
        # Ensure all standard columns are present, even if not found in original data (fill with empty values)
        for std_col in STANDARD_COLS:
            if std_col not in df_normalized.columns:
                if std_col in [COL_E, COL_N, COL_Z]:
                    df_normalized[std_col] = 0.0
                else:
                    df_normalized[std_col] = ""
                
    # --- Data Type Cleaning ---
    # Convert coordinate columns to numeric, handling errors gracefully
    for col in [COL_E, COL_N, COL_Z]:
        if col in df_normalized.columns:
            df_normalized[col] = pd.to_numeric(df_normalized[col], errors='coerce').fillna(0.0)
    # Convert ID, Code, Description columns to string, handling NA
    for col in [COL_PT, COL_CODE, COL_DESC]:
         if col in df_normalized.columns:
             df_normalized[col] = df_normalized[col].astype(str).replace({'nan': '', 'NaN': '', 'NAN': '', 'None': '', 'NULL': ''}, regex=False).fillna('')
             
    return df_normalized

def create_custom_transformer():
    custom_proj = "+proj=pipeline +step +inv +proj=utm +zone=36 +ellps=WGS84 +step +proj=cart +ellps=WGS84 +step +proj=helmert +x=127.535 +y=-113.495 +z=12.7 +rx=-1.603747 +ry=0.153612 +rz=5.364408 +s=-5.33745 +convention=position_vector +step +inv +proj=cart +ellps=clrk80 +step +proj=tmerc +lat_0=30 +lon_0=31 +k=1 +x_0=615000 +y_0=810000 +ellps=clrk80"
    return Transformer.from_pipeline(custom_proj)

def transform_coordinates(
    df: pd.DataFrame,
    source_crs: str,
    target_crs: str,
    write_to_new_columns: bool = False,
    new_easting_col: Optional[str] = None,
    new_northing_col: Optional[str] = None,
    flip_en: bool = False,
    use_custom: bool = False,
):
    """
    Transforms coordinates in a DataFrame from a source CRS to a target CRS.

    If write_to_new_columns=True, the transformed coordinates are written to the
    specified new columns without dropping rows that have invalid coordinates.
    """
    if df.empty:
        return df

    if not all([CRS, Transformer, CRSError]):
        raise ImportError("pyproj library is required for coordinate transformation.")

    try:
        src = CRS(source_crs)
        dst = CRS(target_crs)
        transformer = None

        # Enable custom transformation automatically for UTM Zone 36N to Egypt Red Belt
        source_str = str(source_crs).strip().upper()
        target_str = str(target_crs).strip().upper()
        
        # Check for UTM Zone 36N (multiple formats)
        is_utm36n = (source_str in {"EPSG:32636", "32636"} or 
                     "UTM" in source_str and "36" in source_str and "N" in source_str)
        
        # Check for Egypt Red Belt (multiple formats) 
        is_egypt_red = (target_str in {"EPSG:22992", "22992"} or
                       "EGYPT" in target_str and "RED" in target_str)
        
        if is_utm36n and is_egypt_red:
            use_custom = True
            logging.info(f"Auto-enabling custom Egypt transformation: {source_crs} -> {target_crs}")

        # Custom for Egypt using inverted EPSG:1148 parameters
        if use_custom and (is_utm36n and is_egypt_red):
            try:
                transformer = create_custom_transformer()
                logging.info("Using custom Helmert transformation for UTM 36N to Egypt Red Belt.")
                # Validate against standard on a small sample and fallback if deviation is large
                try:
                    e_series_val = pd.to_numeric(df.get(COL_E), errors='coerce') if COL_E in df.columns else pd.Series([], dtype=float)
                    n_series_val = pd.to_numeric(df.get(COL_N), errors='coerce') if COL_N in df.columns else pd.Series([], dtype=float)
                    valid_mask_val = e_series_val.notna() & n_series_val.notna()
                    if valid_mask_val.any():
                        idx_sample = e_series_val[valid_mask_val].index[:50]
                        if len(idx_sample) >= 3:
                            x_samp = e_series_val.loc[idx_sample].to_numpy()
                            y_samp = n_series_val.loc[idx_sample].to_numpy()
                            cx, cy = transformer.transform(x_samp, y_samp)
                            std_tr = Transformer.from_crs(src, dst, always_xy=True)
                            sx, sy = std_tr.transform(x_samp, y_samp)
                            diffs = np.sqrt((cx - sx) ** 2 + (cy - sy) ** 2)
                            median_diff = float(np.nanmedian(diffs)) if diffs.size > 0 else 0.0
                            if median_diff > 3.0:
                                logging.warning(f"Custom Egypt transform deviates from standard by median {median_diff:.3f} m on sample; using standard instead.")
                                transformer = std_tr
                except Exception as e_val:
                    logging.warning(f"Custom transform self-check failed: {e_val}. Using standard transformer.")
                    transformer = Transformer.from_crs(src, dst, always_xy=True)
            except Exception as e_custom:
                logging.warning(f"Custom transformer failed: {e_custom}. Falling back to standard.")
                transformer = Transformer.from_crs(src, dst, always_xy=True)

        # Build AOI from sample if possible to encourage the best grid-based path
        aoi = None
        if AreaOfInterest is not None:
            try:
                e_series_tmp = pd.to_numeric(df.get(COL_E), errors='coerce') if COL_E in df.columns else pd.Series([], dtype=float)
                n_series_tmp = pd.to_numeric(df.get(COL_N), errors='coerce') if COL_N in df.columns else pd.Series([], dtype=float)
                valid_mask_tmp = e_series_tmp.notna() & n_series_tmp.notna()
                if valid_mask_tmp.any():
                    # sample up to 200 points
                    idx = e_series_tmp[valid_mask_tmp].index[:200]
                    x = e_series_tmp.loc[idx].to_numpy()
                    y = n_series_tmp.loc[idx].to_numpy()
                    # If source is geographic (lon/lat), AOI directly from data; else transform to 4326 first
                    def _bbox(arr):
                        return float(np.nanmin(arr)), float(np.nanmax(arr))
                    if src.is_geographic:
                        minx, maxx = _bbox(x)
                        miny, maxy = _bbox(y)
                        aoi = AreaOfInterest(west_lon_degree=minx, south_lat_degree=miny, east_lon_degree=maxx, north_lat_degree=maxy)
                    else:
                        try:
                            to_wgs84 = Transformer.from_crs(src, CRS("EPSG:4326"), always_xy=True)
                            lon, lat = to_wgs84.transform(x, y)
                            minx, maxx = _bbox(lon)
                            miny, maxy = _bbox(lat)
                            aoi = AreaOfInterest(west_lon_degree=minx, south_lat_degree=miny, east_lon_degree=maxx, north_lat_degree=maxy)
                        except Exception:
                            aoi = None
            except Exception:
                aoi = None

        # If no custom transformer, use the standard approach
        if transformer is None:
            # Optionally use TransformerGroup to pick authority-preferred with available grids
            use_best = True
            try:
                # Respect UI option if present via environment flag set by app
                use_best = bool(int(os.environ.get("TACO_USE_BEST_TRANSFORM", "1")))
            except Exception:
                use_best = True
            if use_best and TransformerGroup is not None:
                try:
                    tg = TransformerGroup(src, dst, always_xy=True, area_of_interest=aoi)
                    # Log available transformations for debugging
                    logging.info(f"Available transformations for {source_crs} to {target_crs}:")
                    for i, trans in enumerate(getattr(tg, "transformers", []) or []):
                        logging.info(f"  {i+1}: {getattr(trans, 'name', 'N/A')} - Accuracy: {getattr(trans, 'accuracy', 'N/A')}")
                    # Warn about missing grids if any operation references grids that are not available
                    try:
                        for op in getattr(tg, "operations", []) or []:
                            grids = getattr(op, "grids", []) or []
                            missing = [g for g in grids if hasattr(g, "is_available") and not getattr(g, "is_available")]
                            if missing:
                                names = ", ".join(getattr(g, "name", "<grid>") for g in missing)
                                logging.warning(f"Some transformation grids are missing and may reduce accuracy: {names}")
                    except Exception:
                        pass
                    # Choose the best available transformer robustly across pyproj versions
                    transformer = None
                    tfs = getattr(tg, "transformers", None)
                    if isinstance(tfs, (list, tuple)) and len(tfs) > 0:
                        transformer = tfs[0]
                    else:
                        ba = getattr(tg, "best_available", None)
                        if ba is not None and not isinstance(ba, bool):
                            transformer = ba
                except Exception:
                    transformer = None

        if transformer is None:
            transformer = Transformer.from_crs(src, dst, always_xy=True, accuracy=0.1, allow_ballpark=False)
    except CRSError as e:
        logging.error(f"Invalid CRS provided: {e}")
        raise ValueError(f"Invalid CRS: {e}") from e

    # Ensure coordinate columns are numeric
    easting_series = pd.to_numeric(df[COL_E], errors='coerce')
    northing_series = pd.to_numeric(df[COL_N], errors='coerce')

    # Allow optional swap E/N before transform when data comes as N/E
    if flip_en:
        easting_series, northing_series = northing_series, easting_series

    if write_to_new_columns:
        # Decide default new column names
        if new_easting_col is None or new_northing_col is None:
            if str(target_crs).strip().upper() in {"EPSG:4326", "4326"}:
                new_easting_col = new_easting_col or "Longitude"
                new_northing_col = new_northing_col or "Latitude"
            else:
                suffix = str(target_crs).replace(":", "_")
                new_easting_col = new_easting_col or f"Easting_{suffix}"
                new_northing_col = new_northing_col or f"Northing_{suffix}"

        valid_mask = easting_series.notna() & northing_series.notna()
        # Initialize with NaN (numpy.nan to avoid NAType issues in downstream float conversions)
        result_e = pd.Series([np.nan] * len(df), index=df.index, dtype="float64")
        result_n = pd.Series([np.nan] * len(df), index=df.index, dtype="float64")
        if valid_mask.any():
            # Ensure order always_xy=True means (x=lon/easting, y=lat/northing)
            tr_x, tr_y = transformer.transform(easting_series[valid_mask].to_numpy(), northing_series[valid_mask].to_numpy())
            
            # V11 - Custom adjustment for Egypt Red Belt
            if is_utm36n and is_egypt_red:
                logging.info("Applying custom offset for Egypt Red Belt transformation: E+0.4344, N-0.4977")
                tr_x = tr_x + 0.4344
                tr_y = tr_y - 0.4977

            result_e.loc[valid_mask] = tr_x
            result_n.loc[valid_mask] = tr_y
        df[new_easting_col] = result_e
        df[new_northing_col] = result_n
        logging.info(
            f"Transformed {int(valid_mask.sum())}/{len(df)} points from {source_crs} to {target_crs} into new columns: "
            f"{new_easting_col}, {new_northing_col}."
        )
        return df
    else:
        # In-place transformation for valid coordinates, preserving all rows.
        working_df = df.copy()
        valid_mask = easting_series.notna() & northing_series.notna()

        if valid_mask.any():
            # Get the coordinates to be transformed from the (potentially swapped) series
            x_in = easting_series[valid_mask].to_numpy()
            y_in = northing_series[valid_mask].to_numpy()

            # Perform the transformation only on valid data
            tr_x, tr_y = transformer.transform(x_in, y_in)

            # V11 - Custom adjustment for Egypt Red Belt
            if is_utm36n and is_egypt_red:
                logging.info("Applying custom offset for Egypt Red Belt transformation: E+0.4344, N-0.4977")
                tr_x = tr_x + 0.4344
                tr_y = tr_y - 0.4977

            # Update the columns in-place only for the valid rows
            working_df.loc[valid_mask, COL_E] = tr_x
            working_df.loc[valid_mask, COL_N] = tr_y

            logging.info(
                f"Transformed {int(valid_mask.sum())}/{len(df)} points from {source_crs} to {target_crs} in-place."
            )
        else:
            logging.info("No valid coordinates found to transform.")

        return working_df


def detect_crs_auto(df: pd.DataFrame, hints: Optional[Dict] = None) -> str:
    """
    Attempts to detect the source CRS from data heuristics and optional hints.

    Heuristics:
    - If Easting/Northing look like lon/lat degrees (most values within [-180..180] and [-90..90]), assume EPSG:4326.
    - If values look like UTM meters (E in [100k..900k], N in [0..10,000k]) and hints specify a UTM zone,
      return the corresponding EPSG: 326{zone} for 'N' or 327{zone} for 'S'.

    Raises ValueError if CRS cannot be determined.
    """
    if df.empty:
        raise ValueError("Cannot detect CRS from an empty DataFrame.")

    if hints is None:
        hints = {}

    # If the DataFrame has explicit CRS/EPSG columns
    for crs_col in ["CRS", "crs", "EPSG", "epsg", "SourceCRS", "source_crs"]:
        if crs_col in df.columns and pd.api.types.is_string_dtype(df[crs_col]):
            first = str(df[crs_col].dropna().iloc[0]).strip()
            if first:
                return first if first.upper().startswith("EPSG:") else f"EPSG:{first}"

    # Use numeric heuristics
    easting = pd.to_numeric(df.get(COL_E, pd.Series([], dtype=float)), errors='coerce')
    northing = pd.to_numeric(df.get(COL_N, pd.Series([], dtype=float)), errors='coerce')
    valid = easting.notna() & northing.notna()
    if valid.any():
        e_sub = easting[valid]
        n_sub = northing[valid]
        # Degree-like check
        deg_like = (e_sub.between(-180, 180).mean() > 0.9) and (n_sub.between(-90, 90).mean() > 0.9)
        if deg_like:
            return "EPSG:4326"

        # UTM-like with provided zone
        e_utmlike = e_sub.between(100000, 900000).mean() > 0.9
        n_utmlike = n_sub.between(0, 10000000).mean() > 0.9
        zone_number = hints.get('zone_number') or hints.get('utm_zone') or hints.get('Zone')
        zone_letter = (hints.get('zone_letter') or hints.get('hemisphere') or '').upper()
        if e_utmlike and n_utmlike and zone_number:
            try:
                zone_number_int = int(zone_number)
                if 1 <= zone_number_int <= 60:
                    if zone_letter == 'S':
                        return f"EPSG:327{zone_number_int:02d}"
                    # Default to northern hemisphere
                    return f"EPSG:326{zone_number_int:02d}"
            except Exception:
                pass

    raise ValueError("Unable to auto-detect CRS. Please specify the source CRS explicitly.")


def detect_egypt_belt(df: pd.DataFrame, source_crs: str) -> str:
    """
    Detect the appropriate Egypt ETM belt for the given data by projecting a sample
    to WGS84 and selecting based on longitude:
      - Purple Belt: 25°E to <29°E  -> EPSG:22994
      - Red Belt:    29°E to <33°E  -> EPSG:22992
      - Blue Belt:   33°E to <37°E  -> EPSG:22993

    Returns EPSG code string. Defaults to Red Belt if outside ranges or detection fails.
    """
    if df.empty:
        return "EPSG:22992"  # Default to Red

    if not all([CRS, Transformer, CRSError]):
        raise ImportError("pyproj library is required for belt detection.")

    # Prepare sample of valid coordinates
    e_series = pd.to_numeric(df.get(COL_E), errors='coerce') if COL_E in df.columns else pd.Series([], dtype=float)
    n_series = pd.to_numeric(df.get(COL_N), errors='coerce') if COL_N in df.columns else pd.Series([], dtype=float)
    valid_mask = e_series.notna() & n_series.notna()
    if not valid_mask.any():
        return "EPSG:22992"

    sample_idx = e_series[valid_mask].index[:200]
    try:
        to_wgs = Transformer.from_crs(CRS(source_crs), CRS("EPSG:4326"), always_xy=True)
        lons, lats = to_wgs.transform(e_series.loc[sample_idx].values, n_series.loc[sample_idx].values)
        if len(lons) == 0:
            return "EPSG:22992"
        import numpy as np
        median_lon = float(np.median(lons))
        if 25.0 <= median_lon < 29.0:
            return "EPSG:22994"  # Purple
        if 29.0 <= median_lon < 33.0:
            return "EPSG:22992"  # Red
        if 33.0 <= median_lon < 37.0:
            return "EPSG:22993"  # Blue
        return "EPSG:22992"
    except Exception:
        return "EPSG:22992"


def infer_egypt_belt_from_data(df: pd.DataFrame) -> str:
    """
    Attempts to infer the Egypt ETM belt (EPSG:22992/22993/22994) directly from Easting/Northing
    by trying each belt as SOURCE and projecting to WGS84, then scoring plausibility.

    Returns best-matching EPSG belt, defaulting to 22992 if uncertain.
    """
    if df.empty:
        return "EPSG:22992"
    if not all([CRS, Transformer, CRSError]):
        raise ImportError("pyproj library is required for belt inference.")

    e_series = pd.to_numeric(df.get(COL_E, pd.Series(dtype=float)), errors='coerce')
    n_series = pd.to_numeric(df.get(COL_N, pd.Series(dtype=float)), errors='coerce')
    valid_mask = e_series.notna() & n_series.notna()
    if not valid_mask.any():
        return "EPSG:22992"

    candidates = ["EPSG:22992", "EPSG:22993", "EPSG:22994"]
    best = (None, -1.0, 0.0)  # (epsg, score, egypt_fraction)
    # Rough Egypt bounding box
    egypt_lon_min, egypt_lon_max = 24.0, 37.5
    egypt_lat_min, egypt_lat_max = 21.0, 32.7

    for epsg in candidates:
        try:
            tr = Transformer.from_crs(CRS(epsg), CRS("EPSG:4326"), always_xy=True)
            x = e_series[valid_mask].to_numpy()
            y = n_series[valid_mask].to_numpy()
            lon, lat = tr.transform(x, y)
            import numpy as np
            lon = np.array(lon, dtype=float)
            lat = np.array(lat, dtype=float)
            finite = np.isfinite(lon) & np.isfinite(lat)
            if not finite.any():
                continue
            # global plausibility
            plausible = (lon > -180) & (lon < 180) & (lat > -90) & (lat < 90)
            plaus_frac = float(plausible.mean())
            # egypt bbox plausibility
            in_egypt = (lon >= egypt_lon_min) & (lon <= egypt_lon_max) & (lat >= egypt_lat_min) & (lat <= egypt_lat_max)
            egypt_frac = float(in_egypt.mean())
            # score: weight egypt box higher
            score = egypt_frac * 0.8 + plaus_frac * 0.2
            if score > best[1]:
                best = (epsg, score, egypt_frac)
        except Exception:
            continue

    return best[0] if best[0] else "EPSG:22992"


# V7 - REVISED: get_line_groups with robust Natural Sort logic
@functools.lru_cache(maxsize=128)
def read_excel_file(file_path: Path, sheet_name=0):
    """
    Reads survey points from an Excel file (.xlsx, .xls).
    It intelligently detects if a header row exists.
    """
    if openpyxl is None:
        raise ImportError("The 'openpyxl' library is required to read Excel files. Please install it.")

    try:
        # First, read the top few rows without a header to inspect them
        preview_df = pd.read_excel(str(file_path), sheet_name=sheet_name, header=None, engine='openpyxl', nrows=5)
        
        # Heuristic to detect a header: check if the first row is mostly strings
        # and the second row is not, or if the first row contains known aliases.
        header_row_index = None
        if not preview_df.empty:
            first_row = preview_df.iloc[0]
            # Check if the first row looks like a header (mostly non-numeric)
            is_mostly_strings = first_row.apply(lambda x: isinstance(x, str)).mean() > 0.6
            
            # Check if the second row looks like data (if it exists)
            has_data_below = False
            if len(preview_df) > 1:
                second_row = preview_df.iloc[1]
                # Check if the second row is mostly numeric or can be converted to numeric
                numeric_like_count = pd.to_numeric(second_row, errors='coerce').notna().mean()
                if numeric_like_count > 0.5:
                    has_data_below = True

            # Check for aliases in the first row
            matches_aliases = any(str(h).lower() in [a.lower() for aliases in COLUMN_ALIASES.values() for a in aliases] for h in first_row)

            if (is_mostly_strings and has_data_below) or matches_aliases:
                header_row_index = 0 # The first row is the header
                logging.info(f"Header detected in the first row of {file_path.name}.")
            else:
                logging.info(f"No header detected in {file_path.name}. Reading without a header.")

        # Read the full file with the determined header setting
        df = pd.read_excel(str(file_path), sheet_name=sheet_name, header=header_row_index, engine='openpyxl')

        logging.info(f"Successfully read {len(df)} rows from Excel file: {file_path.name}, Sheet: {sheet_name}")
        return df
    except FileNotFoundError:
        logging.error(f"Excel file not found: {file_path}")
        raise
    except Exception as e:
        logging.error(f"Error reading Excel file {file_path.name}: {e}", exc_info=True)
        raise ValueError(f"Could not read Excel file. Error: {e}") from e


# New master function to dispatch based on file type
def read_survey_file(file_path: Path, settings: dict = None):
    """
    Reads a survey data file by dispatching to the appropriate reader based on file extension.
    """
    if settings is None:
        settings = {}
        
    ext = file_path.suffix.lower()
    logging.info(f"Attempting to read file '{file_path.name}' with extension '{ext}'")

    df = pd.DataFrame()
    try:
        if ext in ['.csv', '.txt', '.dat']:
            encoding = detect_encoding(file_path)
            delimiter = sniff_delimiter(file_path, encoding)
            skiprows, header_row, header_names = sniff_header_and_skiprows(file_path, encoding, delimiter)
            
            # Use chunking for large CSV files
            chunks = []
            for chunk in pd.read_csv(
                file_path,
                encoding=encoding,
                delimiter=delimiter,
                skiprows=skiprows,
                header=header_row,
                names=header_names if header_row is None else None,
                on_bad_lines='warn',
                engine='python', # 'python' engine is more robust for sniffing
                chunksize=CHUNK_SIZE_CSV
            ):
                chunks.append(chunk)
            if chunks:
                df = pd.concat(chunks, ignore_index=True)

        elif ext in ['.xlsx', '.xls']:
            # For Excel, we might need to let the user choose a sheet.
            # For now, we default to the first sheet (index 0).
            sheet_name = settings.get('excel_sheet_name', 0)
            df = read_excel_file(file_path, sheet_name=sheet_name)
            
        elif ext == '.dxf':
            df = read_dxf_file(file_path)
        elif ext == '.dwg':
            raise ValueError("Direct import of DWG files is not supported. Please save the file as a DXF in your CAD software and try again.")
            
        elif ext in ['.kml', '.kmz']:
            df = read_kml_file(file_path, settings)
            
        elif ext == '.gsi':
            df = read_gsi_file(file_path)
            
        elif ext in ['.sdr', '.sdr33']:
            df = read_sdr33_file(file_path)
            
        else:
            # Fallback for unknown text-based formats: try to read as CSV
            logging.warning(f"Unknown file extension '{ext}'. Attempting to read as a generic delimited file.")
            encoding = detect_encoding(file_path)
            delimiter = sniff_delimiter(file_path, encoding)
            skiprows, header_row, header_names = sniff_header_and_skiprows(file_path, encoding, delimiter)
            df = pd.read_csv(
                file_path,
                encoding=encoding,
                delimiter=delimiter,
                skiprows=skiprows,
                header=header_row,
                names=header_names if header_row is None else None,
                on_bad_lines='warn',
                engine='python'
            )

        if df.empty:
            logging.warning(f"Reading file '{file_path.name}' resulted in an empty DataFrame.")
            return pd.DataFrame()

        # After reading, normalize the columns
        column_order = settings.get('column_order_str', 'Auto-detect Columns')
        normalized_df = normalize_columns(df, column_order_str=column_order)
        
        logging.info(f"Successfully read and normalized {len(normalized_df)} records from {file_path.name}")
        return normalized_df

    except Exception as e:
        logging.error(f"Failed to read or process file {file_path.name}: {e}", exc_info=True)
        # Propagate a more user-friendly error
        raise IOError(f"Could not process file '{file_path.name}'. Reason: {e}") from e

def get_line_groups(df: pd.DataFrame, logic_key: str, custom_group_col: str, sort_col: str = COL_PT, do_sort: bool = True):
    """
    Splits a DataFrame into groups based on the specified connection logic (sequential, by column, etc.).
    Uses a robust "natural sort" for sorting within groups.
    """
    if df.empty: return {}
    
    grouped_dfs = {}
    effective_sort_col = sort_col if sort_col in df.columns else None
    
    if not effective_sort_col and do_sort:
        logging.warning(f"Sort column '{sort_col}' not found. Disabling sorting for line grouping.")
        do_sort = False

    def natural_sort_key(text):
        """Helper key function for natural sorting (e.g., 'STN2' before 'STN10')."""
        text = str(text) if pd.notna(text) else ''
        # Splits the text into a list of strings and numbers.
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

    def sort_group_naturally(group_df):
        """Applies natural sort to a DataFrame group."""
        if not (do_sort and effective_sort_col):
            return group_df
        try:
            # Create a temporary column with the natural sort key
            # This is more robust for pandas than using the `key` argument directly
            group_df['_natural_sort_key'] = group_df[effective_sort_col].apply(natural_sort_key)
            
            # Sort by the new key and drop it
            sorted_group = group_df.sort_values(
                by='_natural_sort_key',
                kind='mergesort', # Stable sort
                na_position='last'
            ).drop(columns=['_natural_sort_key']).reset_index(drop=True)
            return sorted_group
        except Exception as e_sort:
            logging.warning(f"Could not perform natural sort on group by '{effective_sort_col}': {e_sort}. Falling back to original order.")
            return group_df # Return unsorted on error

    # --- Grouping Logic ---
    if logic_key == 'sequential':
        # For sequential logic, we connect points in their current order without any sorting or grouping.
        grouped_dfs['sequential_line_0'] = df.copy()
        return grouped_dfs
        
    group_by_column_name = None
    if logic_key == 'by_pt': group_by_column_name = COL_PT
    elif logic_key == 'code': group_by_column_name = COL_CODE
    elif logic_key == 'description': group_by_column_name = COL_DESC
    elif logic_key == 'custom' and custom_group_col: group_by_column_name = custom_group_col
    
    if not (group_by_column_name and group_by_column_name in df.columns):
        logging.warning(f"Line connection logic '{logic_key}' with column '{custom_group_col}' failed. Defaulting to sequential.")
        return get_line_groups(df, 'sequential', '', sort_col=sort_col, do_sort=do_sort)
        
    for group_id, group_df_raw in df.groupby(group_by_column_name, sort=False, dropna=False):
        if group_id is None or (isinstance(group_id, str) and group_id.strip() == ""):
            continue
            
        group_df_copy = group_df_raw.copy()
        if len(group_df_copy) >= 2:
            sorted_group = sort_group_naturally(group_df_copy)
            grouped_dfs[str(group_id)] = sorted_group
            
    return grouped_dfs

def _is_potential_point_id(text: str, max_length=32) -> bool:
    """
    Heuristically determines if a string is a potential point identifier.
    - Not too long.
    - Does not contain characters typical of descriptive sentences (e.g., multiple spaces).
    """
    if not text or not isinstance(text, str):
        return False
    
    text = text.strip()
    # An empty string is not a valid ID.
    if not text:
        return False
        
    # Point IDs are typically short.
    if len(text) > max_length:
        return False
    
    # Descriptions often have multiple words/spaces. Point IDs usually have one or none.
    if text.count(' ') > 2: # Allow up to two spaces for IDs like "STN 1 A"
        return False
        
    # If it passes the checks, it's a potential ID.
    return True

@functools.lru_cache(maxsize=128)
def read_dxf_file(file_path: Path):
    """
    Reads survey points from a DXF file. Supports POINT and INSERT (Blocks) entities with data
    extraction from ATTRIBS attributes if present, and attempts to link the nearest text label to the point.
    """
    points_data = []
    doc = None # Initialize document object to None
    try:
        # Try to recover the DXF file first, then fall back to direct read
        try:
            if ezdxf and hasattr(ezdxf, 'recover'):
                doc, auditor = ezdxf.recover.readfile(str(file_path))
                if auditor.has_errors:
                    logging.warning(f"DXF recover found errors in {file_path.name}. Proceeding with recovered data.")
                if not doc: # If recover failed, try direct read
                    logging.warning(f"DXF recover failed for {file_path.name}. Trying direct read.")
                    doc = readfile(str(file_path))
            else:
                doc = readfile(str(file_path))
        except Exception as e_recover:
            logging.warning(f"DXF recover failed for {file_path.name}: {e_recover}. Trying direct read.")
            doc = readfile(str(file_path))
            
        if not doc: raise ValueError("Failed to open or recover DXF document.") # Raise error if still no document
        
        msp = doc.modelspace() # Get the model space from the DXF document
        
        # --- Spatial Indexing Preparation ---
        # Create a list of all text entities with their locations for efficient searching
        text_spatial_index = []
        for text_ent in msp.query('TEXT MTEXT'):
            loc = None
            if text_ent.dxf.hasattr('insert'):
                loc = text_ent.dxf.insert
            
            if loc:
                text_content = ""
                if hasattr(text_ent, 'plain_text'): # MTEXT
                    text_content = text_ent.plain_text().strip()
                elif hasattr(text_ent.dxf, 'text'): # TEXT
                    text_content = text_ent.dxf.text.strip()
                
                if text_content:
                    text_spatial_index.append({'loc': loc, 'text': text_content})

        # Use aliases for attribute tag matching, including Arabic names
        pt_attr_names = [name.upper() for name in COLUMN_ALIASES.get(COL_PT, [])]
        
        # Iterate through each point-like entity in the model space
        for entity in msp.query('POINT INSERT'):
            entity_type = entity.dxftype()
            pt_data = {}
            
            # --- 1. Extract Base Point Info ---
            if entity_type == 'POINT':
                loc = entity.dxf.location
                pt_data = {
                    COL_E: loc.x, COL_N: loc.y, COL_Z: loc.z,
                    COL_PT: None, # To be determined
                    COL_CODE: entity.dxf.layer,
                    COL_DESC: ""
                }
            elif entity_type == 'INSERT':
                loc = entity.dxf.insert
                pt_id_from_attrib = None
                
                # Robustly search for ATTRIBS
                if entity.attribs:
                    for attrib in entity.attribs:
                        if attrib.dxf.tag.upper() in pt_attr_names:
                            pt_id_from_attrib = str(attrib.dxf.text).strip()
                            break
                
                pt_data = {
                    COL_E: loc.x, COL_N: loc.y, COL_Z: loc.z,
                    COL_PT: pt_id_from_attrib, # Can be None
                    COL_CODE: entity.dxf.layer,
                    COL_DESC: entity.dxf.name
                }

            # --- 2. Find Closest Text using the Spatial Index ---
            closest_text_pt = None
            closest_text_desc = None
            min_dist_sq = float('inf')

            if text_spatial_index:
                # Find the single closest text entity of any kind
                closest_text_info = min(text_spatial_index, key=lambda t: (t['loc'] - loc).magnitude_square)
                
                # Now, decide if this closest text is an ID or a description
                if _is_potential_point_id(closest_text_info['text']):
                    closest_text_pt = closest_text_info['text']
                else:
                    closest_text_desc = closest_text_info['text']

            # --- 3. Finalize Point Data using Priority ---
            # Priority: 1. Closest Text ID, 2. Block Attribute, 3. Handle
            final_pt_id = closest_text_pt or pt_data.get(COL_PT) or str(entity.dxf.handle)
            pt_data[COL_PT] = final_pt_id
            
            # Only use the closest text as description if we didn't use it for the ID
            if closest_text_desc:
                pt_data[COL_DESC] = closest_text_desc
            
            points_data.append(pt_data)
                
        logging.info(f"Read {len(points_data)} points from DXF: {file_path.name}")
        return pd.DataFrame(points_data) # Return data as DataFrame
        
    except Exception as e_dxf_struct:
        logging.error(f"DXF Structure Error reading {file_path.name}: {e_dxf_struct}", exc_info=True)
        raise ValueError(f"Invalid DXF file structure: {e_dxf_struct}") from e_dxf_struct
    finally:
        if doc: del doc; gc.collect() # Clean up DXF document object to free memory

def export_dxf_file(df: pd.DataFrame, file_path: Path, settings: dict):
    """
    Exports data from a DataFrame to a DXF file. Supports exporting points, lines, and polygons,
    with options to customize layers, colors, point styles, and text labels.
    """
    # Ensure df is a DataFrame
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    # Ensure coordinate columns are numeric
    for col in [COL_E, COL_N, COL_Z]:
        if col in df.columns:
            # Force conversion to numeric, coercing errors to NaN, then fill with 0.0 and cast to float.
            # This is a robust way to handle mixed types, empty strings, etc.
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)
            
    if ezdxf is None:
        raise ImportError("ezdxf library is not available")
    
    # Create new DXF document - handle different ezdxf versions
    doc = None
    
    # Try different methods to create DXF document
    creation_methods = [
        lambda: getattr(ezdxf, 'new', lambda x: None)('R2010'),
        lambda: getattr(ezdxf, 'Document', lambda x: None)('R2010'),
        lambda: getattr(ezdxf, 'readfile', lambda x: None)('template.dxf')
    ]
    
    for method in creation_methods:
        try:
            doc = method()
            if doc is not None:
                break
        except (AttributeError, ImportError, FileNotFoundError):
            continue
    
    if doc is None:
        raise ImportError("Unable to create DXF document with available ezdxf version")
        
    msp = doc.modelspace() # Create new DXF document R2010
    
    # Get settings with defaults
    base_layer_name = settings.get('layer_name', 'Survey_Export').strip() or 'Survey_Export' # Ensure layer name is not empty
    def get_color_attr(val, fallback_aci=7):
        """Helper: returns (aci, true_color) tuple from a color value (hex or int)."""
        import re
        if isinstance(val, str) and val.strip().startswith('#') and re.fullmatch(r'#([0-9a-fA-F]{6})', val.strip()):
            hex_val = val.strip()
            rgb = tuple(int(hex_val[i:i+2], 16) for i in (1, 3, 5))
            # DXF true color is packed as 0x00RRGGBB
            true_color = (rgb[0] << 16) + (rgb[1] << 8) + rgb[2]
            return (fallback_aci, true_color) # Return fallback ACI with true_color
        try:
            aci = int(val)
            return (aci, None)
        except Exception:
            return (fallback_aci, None)

    default_line_color_aci, default_line_true_color = get_color_attr(settings.get('line_color', "#00ff00"))
    point_default_color_aci, point_default_true_color = get_color_attr(settings.get('point_color', "#ff0000"))
    poly_default_color_aci, poly_default_true_color = get_color_attr(settings.get('poly_color', "#0000ff"))
    
    color_mode_is_bylayer = (settings.get('color_mode', 'By Layer (Recommended)') == 'By Layer (Recommended)')

    # Create base layer if it doesn't exist
    if base_layer_name not in doc.layers:
        layer = doc.layers.add(base_layer_name, color=point_default_color_aci)
        if point_default_true_color is not None and color_mode_is_bylayer:
            layer.true_color = point_default_true_color
        
    pdmode_val = DXF_POINT_STYLE_MAP.get(str(settings.get('point_style', 'circle_cross')).lower(), 34) # Get PDMODE value
    doc.header['$PDMODE'] = pdmode_val
    doc.header['$PDSIZE'] = float(settings.get('point_size', 0.1)) # Set point size
    
    color_mode_is_bylayer = (settings.get('color_mode', 'By Layer (Recommended)') == 'By Layer (Recommended)')
    use_code_for_layer = settings.get('use_code_as_layer', True)
    
    # --- Export Points ---
    if settings.get('export_points', True):
        # Vectorized layer name creation
        df['point_dxf_layer_name'] = base_layer_name
        if use_code_for_layer:
            df['point_dxf_layer_name'] = df[COL_CODE].str.strip().apply(lambda c: re.sub(r'[^\w_.)( -]', '_', c) if c else base_layer_name)
        
        # Create all necessary layers in one go
        unique_layers = df['point_dxf_layer_name'].unique()
        for layer_name in unique_layers:
            if layer_name not in doc.layers:
                layer = doc.layers.add(layer_name, color=point_default_color_aci)
                if point_default_true_color is not None and color_mode_is_bylayer:
                    layer.true_color = point_default_true_color

        point_entity_color_aci = 256 if color_mode_is_bylayer else point_default_color_aci
        
        # Prepare block if needed
        if settings.get('export_as_blocks', True):
            block_name_suffix = settings.get('point_style', 'circle_cross').upper()
            block_name = f"POINT_BLOCK_{block_name_suffix}"
            block_name = re.sub(r'[^\w_.)( -]', '_', block_name)
            
            if doc.blocks.get(block_name) is None:
                block = doc.blocks.new(name=block_name)
                ps = float(settings.get('point_size', 0.5)) / 2
                block_geom_color = 0
                if pdmode_val == 0: block.add_point((0,0,0))
                else:
                    if pdmode_val & 32: block.add_circle((0,0), ps, dxfattribs={'color': block_geom_color})
                    if pdmode_val & 64: block.add_lwpolyline([(-ps,-ps),(ps,-ps),(ps,ps),(-ps,ps),(-ps,-ps)], dxfattribs={'color': block_geom_color})
                    if pdmode_val & 1:
                         block.add_line((-ps,0),(ps,0), dxfattribs={'color': block_geom_color}); block.add_line((0,-ps),(0,ps), dxfattribs={'color': block_geom_color})
                    if pdmode_val & 2: block.add_line((-ps,-ps),(ps,ps), dxfattribs={'color': block_geom_color}); block.add_line((-ps,ps),(ps,-ps), dxfattribs={'color': block_geom_color})
                    if pdmode_val & 4: block.add_line((0,-ps*1.5),(0,ps*1.5), dxfattribs={'color': block_geom_color})

        # Iterate and add points/blocks
        for index, row in df.iterrows():
            try:
                x, y, z = float(row[COL_E]), float(row[COL_N]), float(row[COL_Z])
                point_attribs = {'layer': row['point_dxf_layer_name'], 'color': point_entity_color_aci}
                if point_default_true_color is not None and not color_mode_is_bylayer:
                    point_attribs['true_color'] = point_default_true_color
                
                if settings.get('export_as_blocks', True):
                    msp.add_blockref(block_name, (x,y,z), dxfattribs=point_attribs)
                else:
                    msp.add_point((x,y,z), dxfattribs=point_attribs)
            except Exception as e_pt: logging.error(f"Error processing DXF point data (row {index}, PT: {row.get(COL_PT, 'N/A')}): {e_pt}", exc_info=True)

        # --- Export Text Labels ---
        text_layer_prefix = settings.get('text_layer_prefix', 'Text_').strip()
        selected_options = settings.get('export_options', [])
        
        for label_type_setting in selected_options:
            text_content_col, key_base, default_text_color_aci = None, None, 7
            
            if label_type_setting == 'Point Number': text_content_col, key_base, default_text_color_aci = COL_PT, "Point_Number", "4"
            elif label_type_setting == 'Description': text_content_col, key_base, default_text_color_aci = COL_DESC, "Description", "5"
            elif label_type_setting == 'Elevation': text_content_col, key_base, default_text_color_aci = COL_Z, "Elevation", "9"
            elif label_type_setting == 'Code': text_content_col, key_base, default_text_color_aci = COL_CODE, "Code", "254"

            if text_content_col and key_base:
                text_height = float(settings.get(f'{key_base}_height', 0.2))
                text_offset_y = float(settings.get(f'{key_base}_offset', 0.1))
                text_dxf_layer_name = f"{text_layer_prefix}{label_type_setting.replace(' ', '_')}"
                text_dxf_layer_name = re.sub(r'[^\w_.)( -]', '_', text_dxf_layer_name)
                
                text_color_aci, text_true_color = get_color_attr(settings.get(f'{key_base}_color', default_text_color_aci))
                
                if text_dxf_layer_name not in doc.layers:
                    text_layer = doc.layers.add(text_dxf_layer_name, color=text_color_aci)
                    if text_true_color is not None and color_mode_is_bylayer:
                        text_layer.true_color = text_true_color
                
                final_text_color_val = 256 if color_mode_is_bylayer else text_color_aci
                
                for index, row in df.iterrows():
                    try:
                        text_content = str(row[text_content_col])
                        if label_type_setting == 'Elevation':
                            text_content = f"{float(row[text_content_col]):.3f}"
                        
                        if text_content:
                            x, y, z = float(row[COL_E]), float(row[COL_N]), float(row[COL_Z])
                            text_attribs = {
                                'layer': text_dxf_layer_name, 'height': text_height,
                                'color': final_text_color_val,
                                'insert': (x, y + text_offset_y, z),
                                'rotation': float(settings.get('text_rotation', 0.0)), 'style': 'Standard'
                            }
                            if text_true_color is not None and not color_mode_is_bylayer:
                                text_attribs['true_color'] = text_true_color
                            msp.add_text(text_content, dxfattribs=text_attribs)
                    except Exception as e_text: logging.error(f"Error processing DXF text label (row {index}, PT: {row.get(COL_PT, 'N/A')}): {e_text}", exc_info=True)
            
    # --- Export Lines ---
    if settings.get('export_lines', False):
        line_groups = get_line_groups(df, settings.get('line_connection_logic_key', 'sequential'),
                                            settings.get('custom_line_grouping_column', ''),
                                            do_sort=settings.get('sort_points_in_line_group', True))
        line_layer_prefix = settings.get('dxf_line_layer_prefix', 'LINE_').strip()
        
        for group_id, group_df in line_groups.items():
            if len(group_df) < 2: continue
            points_for_line = [(float(row[COL_E]), float(row[COL_N]), float(row[COL_Z])) for _, row in group_df.iterrows()]
            line_dxf_layer = re.sub(r'[^\w_.)( -]', '_', f"{line_layer_prefix}{group_id}")
            if not line_dxf_layer: line_dxf_layer = base_layer_name
            if line_dxf_layer not in doc.layers:
                layer = doc.layers.add(line_dxf_layer, color=default_line_color_aci)
                if default_line_true_color is not None and color_mode_is_bylayer:
                    layer.true_color = default_line_true_color
            
            # V7 - REVISED: Export lines as continuous POLYLINE entities.
            line_attribs = {'layer': line_dxf_layer, 'color': 256 if color_mode_is_bylayer else default_line_color_aci}
            if default_line_true_color is not None and not color_mode_is_bylayer:
                line_attribs['true_color'] = default_line_true_color
            # إنشاء خطوط منفردة بين كل نقطتين
            for i in range(len(points_for_line) - 1):
                start_point = points_for_line[i]
                end_point = points_for_line[i + 1]
                msp.add_line(start_point, end_point, dxfattribs=line_attribs)

    # --- Export Polylines ---
    if settings.get('export_polylines', False):
        polyline_groups = get_line_groups(df, settings.get('line_connection_logic_key', 'sequential'),
                                            settings.get('custom_line_grouping_column', ''),
                                            do_sort=settings.get('sort_points_in_line_group', True))
        polyline_layer_prefix = settings.get('dxf_polyline_layer_prefix', 'POLYLINE_').strip()
        
        for group_id, group_df in polyline_groups.items():
            if len(group_df) < 2: continue
            points_for_polyline = [(float(row[COL_E]), float(row[COL_N]), float(row[COL_Z])) for _, row in group_df.iterrows()]
            polyline_dxf_layer = re.sub(r'[^\w_.)( -]', '_', f"{polyline_layer_prefix}{group_id}")
            if not polyline_dxf_layer: polyline_dxf_layer = base_layer_name
            if polyline_dxf_layer not in doc.layers:
                layer = doc.layers.add(polyline_dxf_layer, color=default_line_color_aci)
                if default_line_true_color is not None and color_mode_is_bylayer:
                    layer.true_color = default_line_true_color
            
            polyline_attribs = {'layer': polyline_dxf_layer, 'color': 256 if color_mode_is_bylayer else default_line_color_aci}
            if default_line_true_color is not None and not color_mode_is_bylayer:
                polyline_attribs['true_color'] = default_line_true_color
            # Use add_lwpolyline to ensure a LWPOLYLINE entity is created.
            # This is a 2D entity, so Z-coordinates will be ignored for this geometry type.
            points_2d = [(p[0], p[1]) for p in points_for_polyline]
            msp.add_lwpolyline(points_2d, dxfattribs=polyline_attribs)

    # --- Export Polygons ---
    if settings.get('export_polygons', False):
        poly_groups = get_line_groups(df, settings.get('line_connection_logic_key', 'sequential'),
                                             settings.get('custom_line_grouping_column', ''),
                                             do_sort=settings.get('sort_points_in_line_group', True))
        poly_layer_prefix = settings.get('dxf_poly_layer_prefix', 'POLY_').strip()
        default_poly_color_aci = parse_aci_color(settings.get('poly_color', "5"))
        
        for group_id, group_df in poly_groups.items():
            if len(group_df) < 3: continue
            points_for_poly = [(float(row[COL_E]), float(row[COL_N]), float(row[COL_Z])) for _, row in group_df.iterrows()]
            
            poly_dxf_layer = re.sub(r'[^\w_.)( -]', '_', f"{poly_layer_prefix}{group_id}")
            if not poly_dxf_layer: poly_dxf_layer = base_layer_name
            if poly_dxf_layer not in doc.layers:
                layer = doc.layers.add(poly_dxf_layer, color=default_poly_color_aci)
                if poly_default_true_color is not None and color_mode_is_bylayer:
                    layer.true_color = poly_default_true_color
            
            # V9 - REVISED: Export polygons as continuous 3D POLYLINE entities to preserve elevation data.
            poly_attribs = {'layer': poly_dxf_layer, 'color': 256 if color_mode_is_bylayer else default_poly_color_aci}
            if poly_default_true_color is not None and not color_mode_is_bylayer:
                poly_attribs['true_color'] = poly_default_true_color
            
            # Use add_polyline3d to create a 3D polyline that includes Z-coordinates.
            msp.add_polyline3d(points_for_poly, close=True, dxfattribs=poly_attribs)
            
    try:
        # Check the export format from settings
        export_format = settings.get('export_format', 'DXF').upper()
        
        # Ensure the file path has the correct extension
        final_path = file_path
        if export_format == 'DWG' and file_path.suffix.lower() != '.dwg':
            final_path = file_path.with_suffix('.dwg')
        elif export_format == 'DXF' and file_path.suffix.lower() != '.dxf':
            final_path = file_path.with_suffix('.dxf')

        doc.saveas(str(final_path))
        logging.info(f"{export_format} file successfully saved to: {final_path}")
    except Exception as e_dxf_save:
        logging.error(f"Error saving DXF/DWG file {file_path}: {e_dxf_save}", exc_info=True)
        raise ValueError(f"DXF/DWG save error: {e_dxf_save}") from e_dxf_save

def read_kml_file(file_path: Path, settings: dict):
    """
    Reads survey points from a KML or KMZ file.
    Uses the utm and simplekml libraries to convert coordinates to UTM and process KML data.
    Extracts the Placemark name, description, and coordinates.
    """
    kml_data = []
    # Get UTM zone from settings, with defaults
    zone_number = int(settings.get('zone_number', 36))
    zone_letter = str(settings.get('zone_letter', 'N')).upper()
    
    try:
        xml_content = None
        # Handle KMZ (zipped KML) files
        if file_path.suffix.lower() == '.kmz':
            with zipfile.ZipFile(str(file_path), 'r') as kmz:
                kml_filename = next((name for name in kmz.namelist() if name.lower().endswith('.kml')), None) # Find KML file inside
                if not kml_filename: raise ValueError("No .kml file found inside KMZ archive.")
                xml_content = kmz.read(kml_filename) # Read KML content from zip
        else:
            with open(file_path, 'rb') as f: xml_content = f.read() # Read KML file directly
            
        if not xml_content: raise ValueError("KML content is empty.")
        
        # Detect encoding and decode XML content
        detected_enc = detect_encoding(file_path)
        xml_content_str = xml_content.decode(detected_enc, errors='replace')

        # Remove default XML namespace to simplify ET parsing
        xml_content_str = re.sub(r'xmlns="[^"]+"', '', xml_content_str, count=1)
        root = ET.fromstring(xml_content_str) # Parse XML
        
        # Iterate through Placemarks in the KML
        for placemark_idx, placemark in enumerate(root.findall('.//Placemark')):
            name_el = placemark.find('name') # Find name element
            name = name_el.text.strip() if name_el is not None and name_el.text else f"KML_Placemark_{placemark_idx+1}" # Get name or generate one
            
            desc_el = placemark.find('description') # Find description element
            description_html = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            # Clean HTML description to plain text
            description_text = re.sub(r'<[^>]+>', ' ', description_html).replace('\n', ' ').replace('\r', '').strip()
            description_text = ' '.join(description_text.split()) # Normalize whitespace
            
            # Find coordinates (support Point, LineString, Polygon)
            coords_el = placemark.find('.//Point/coordinates')
            if coords_el is None: coords_el = placemark.find('.//LineString/coordinates')
            if coords_el is None: coords_el = placemark.find('.//Polygon/outerBoundaryIs/LinearRing/coordinates')
            
            if coords_el is not None and coords_el.text:
                coord_sets_text = coords_el.text.strip()
                coord_sets = re.split(r'\s+', coord_sets_text) # Split coordinates (lon,lat,alt pairs)
                
                for i, coord_set_str in enumerate(coord_sets):
                    if not coord_set_str: continue # Skip empty sets
                    parts = coord_set_str.split(',') # Split into lon, lat, [alt]
                    
                    if len(parts) >= 2: # Need at least longitude and latitude
                        try:
                            lon, lat = float(parts[0]), float(parts[1]) # Parse lon, lat
                            alt = float(parts[2]) if len(parts) > 2 else 0.0 # Parse altitude if present
                            
                            # Convert Lat/Lon to UTM coordinates using the provided zone
                            if utm is None:
                                raise ImportError("utm library is not available. Cannot convert Lat/Lon to UTM.")
                            easting, northing, actual_zone_num, actual_zone_letter = utm.from_latlon(lat, lon,
                                force_zone_number=zone_number,
                                force_zone_letter=zone_letter)
                            kml_data.append({
                                COL_PT: f"{name}_Pt{i+1}" if len(coord_sets) > 1 else name, # Generate PT name if multiple points
                                COL_E: easting, COL_N: northing, COL_Z: alt,
                                COL_CODE: "", # No code in standard KML placemarks
                                COL_DESC: description_text # Use cleaned description
                            })
                        except (ValueError, IndexError) as ve:
                            logging.warning(f"Skipping invalid KML coordinate set '{coord_set_str}' in '{name}': {ve}") # Log invalid coordinates
                            
        return pd.DataFrame(kml_data) # Return data as DataFrame
        
    except (ET.ParseError, zipfile.BadZipFile) as e_file_format:
        logging.error(f"KML/KMZ file format error for {file_path.name}: {e_file_format}", exc_info=True)
        raise ValueError(f"Invalid KML/KMZ file format: {e_file_format}") from e_file_format
    except Exception as e:
        logging.error(f"Error reading KML/KMZ file {file_path.name}: {e}", exc_info=True)
        raise

def export_kml_file(df: pd.DataFrame, file_path: Path, settings: dict):
    """
    Exports data from a DataFrame to a KML file. Supports exporting points, lines, and polygons
    with customization of icons, colors, labels, and connection logic.
    """
    if simplekml is None:
        raise ImportError("simplekml library is not available. Cannot export KML.")
    kml = simplekml.Kml(name=settings.get('name', 'Survey Export KML')) # Initialize KML object with name
    doc = kml.newdocument(name=settings.get('name', 'Survey Export')) # Create a document within KML
    
    # --- Define Styles ---
    # Point Style
    point_style = simplekml.Style()
    requested_icon_url = settings.get('icon_url', DEFAULT_KML_ICON)
    icon_color = _get_kml_color_string(settings.get('color', 'ffffffff'), 'ffffffff')
    # Many KML icons are pre-colored (e.g., red pushpin). Colorization works reliably on white
    # or monochrome icons. If user chose a non-white stock icon and a custom color, swap to white.
    normalized_icon_url = str(requested_icon_url).lower()
    use_icon_url = requested_icon_url
    if icon_color != 'ffffffff' and not any(tag in normalized_icon_url for tag in ['wht', 'white']):
        use_icon_url = DEFAULT_KML_ICON
    point_style.iconstyle.icon.href = use_icon_url
    point_style.iconstyle.scale = float(settings.get('scale', 1.0))
    point_style.iconstyle.color = icon_color
    # Ensure normal color mode so the chosen color is applied (not random)
    try:
        point_style.iconstyle.colormode = getattr(simplekml.ColorMode, 'normal')
    except Exception:
        pass
    point_style.labelstyle.scale = float(settings.get('label_scale', 0.8))
    point_style.labelstyle.color = _get_kml_color_string(settings.get('label_color', 'ffffffff'), 'ffffffff')
    
    # Line Style
    line_style = simplekml.Style()
    line_style.linestyle.width = int(settings.get('line_width', 2))
    line_style.linestyle.color = _get_kml_color_string(settings.get('line_color', 'ff00aaff'), 'ff00aaff')
    
    # Polygon Style
    poly_style = simplekml.Style()
    poly_style.polystyle.fill = 1 if settings.get('poly_fill', True) else 0 # Set fill property
    poly_style.polystyle.color = parse_kml_color(settings.get('fill_color', '8000aaff'), default='8000aaff') # Set fill color
    poly_style.polystyle.outline = 1 # Always outline polygon
    poly_style.linestyle.width = int(settings.get('poly_outline_width', 1)) # Set outline width
    poly_style.linestyle.color = parse_kml_color(settings.get('poly_outline_color', 'ff00aaff'), default='ff00aaff') # Set outline color
    
    # Get UTM zone from settings
    zone_number = int(settings.get('zone_number', 36))
    zone_letter = str(settings.get('zone_letter', 'N')).upper()
    
    geometry_types_to_export = settings.get('geometry_type', ['Point']) # Get selected geometry types
    
    # --- Export Points ---
    if 'Point' in geometry_types_to_export:
        point_folder = getattr(doc, 'newfolder', lambda **kwargs: doc)(name="Points")
        
        # Vectorized coordinate conversion
        if utm is None:
            raise ImportError("utm library is not available. Cannot convert UTM to Lat/Lon.")
        
        # Filter out rows with invalid coordinates first
        df_points = df.dropna(subset=[COL_E, COL_N]).copy()
        df_points[COL_E] = pd.to_numeric(df_points[COL_E], errors='coerce')
        df_points[COL_N] = pd.to_numeric(df_points[COL_N], errors='coerce')
        df_points = df_points.dropna(subset=[COL_E, COL_N])

        lat, lon = utm.to_latlon(df_points[COL_E].values, df_points[COL_N].values, zone_number, zone_letter)
        df_points['lat'] = lat
        df_points['lon'] = lon

        # Vectorized label creation
        label_choice = settings.get('label_content', 'Point Number (PT)')
        if label_choice == 'Point Number (PT)':
            df_points['point_name_str'] = df_points[COL_PT].astype(str)
        elif label_choice == 'Code':
            df_points['point_name_str'] = df_points[COL_CODE].astype(str)
        elif label_choice == 'Description':
            df_points['point_name_str'] = df_points[COL_DESC].astype(str)
        elif label_choice == 'Elevation':
            df_points['point_name_str'] = df_points[COL_Z].apply(lambda z: f"{z:.3f}" if pd.notna(z) else "")
        elif label_choice == 'None':
            df_points['point_name_str'] = ""
        else: # Fallback to Point Number if choice is invalid
            df_points['point_name_str'] = df_points[COL_PT].astype(str)

        # Vectorized description creation
        def create_description(row):
            desc_parts = []
            for col_name in df.columns:
                if col_name in row and pd.notna(row[col_name]):
                    value = row[col_name]
                    value_str = f"{value:.3f}" if isinstance(value, float) else str(value)
                    if value_str.strip():
                        desc_parts.append(f"<b>{col_name}:</b> {value_str}")
            return "<br>".join(desc_parts)
        
        df_points['desc_html'] = df_points.apply(create_description, axis=1)

        for index, row in df_points.iterrows():
            try:
                p = getattr(point_folder, 'newpoint', lambda **kwargs: doc.newpoint(**kwargs))(
                    name=row['point_name_str'], 
                    coords=[(row['lon'], row['lat'], row[COL_Z] if pd.notna(row[COL_Z]) else 0.0)]
                )
                p.style = point_style
                p.description = row['desc_html']
                
                try:
                    p.style.iconstyle.colormode = getattr(simplekml.ColorMode, 'normal')
                except Exception:
                    pass
                
                altitude_mode = getattr(simplekml, 'AltitudeMode', None)
                if altitude_mode:
                    clamptoground = getattr(altitude_mode, 'clamptoground', None)
                    if clamptoground:
                        setattr(p, 'altitudemode', clamptoground)
            except Exception as e_pt: logging.error(f"Error exporting KML point (PT: {row.get(COL_PT, 'N/A')}): {e_pt}", exc_info=True)
            
    # --- Export Lines ---
    if 'Line' in geometry_types_to_export:
        # Create folder for lines - handle different simplekml versions
        line_folder = getattr(doc, 'newfolder', lambda **kwargs: doc)(name="Lines")
        # Group data for line drawing
        line_groups = get_line_groups(df, settings.get('line_connection_logic_key','sequential'),
                                            settings.get('custom_line_grouping_column',''),
                                            do_sort=settings.get('sort_points_in_line_group',True))
        line_layer_prefix = settings.get('dxf_line_layer_prefix', 'LINE_').strip()
        
        # Iterate through line groups and create KML LineStrings
        for group_id, group_df in line_groups.items():
            if len(group_df) < 2: continue # Need at least 2 points for a line
            
            coords_for_line = []
            for _, row_line in group_df.iterrows():
                try:
                    e_val = row_line[COL_E]
                    n_val = row_line[COL_N]
                    try:
                        e_val = float(e_val)
                        n_val = float(n_val)
                    except (ValueError, TypeError):
                        logging.warning(f"Skipping KML line point (group '{group_id}', PT: {row_line.get(COL_PT, 'N/A')}) due to invalid E/N: e={e_val}, n={n_val}")
                        continue
                    if (e_val != e_val or e_val is None) or (n_val != n_val or n_val is None):
                        continue
                    if utm is None:
                        raise ImportError("utm library is not available. Cannot convert UTM to Lat/Lon.")
                    lat_l, lon_l = utm.to_latlon(e_val, n_val, zone_number, zone_letter)
                    z_val = row_line[COL_Z] if isinstance(row_line[COL_Z], (int, float)) and row_line[COL_Z] == row_line[COL_Z] else 0.0
                    coords_for_line.append((lon_l, lat_l, z_val))
                except Exception as e_line_pt:
                    logging.warning(f"Error processing point for KML line (group '{group_id}', PT: {row_line.get(COL_PT, 'N/A')}): {e_line_pt}")
                
            if len(coords_for_line) >= 2: # If we have at least 2 valid points
                # Create LineString - handle different simplekml versions
                def create_linestring_fallback(**kwargs):
                    if simplekml is None:
                        raise ImportError("simplekml library is not available")
                    return simplekml.Kml().newlinestring(**kwargs)
                
                ls = getattr(line_folder, 'newlinestring', 
                            getattr(line_folder, 'addlinestring', create_linestring_fallback))(
                    name=str(group_id), 
                    coords=coords_for_line
                )
                ls.style = line_style # Apply line style
                # Set altitude mode - handle different simplekml versions
                altitude_mode = getattr(simplekml, 'AltitudeMode', None)
                if altitude_mode:
                    clamptoground = getattr(altitude_mode, 'clamptoground', None)
                    if clamptoground:
                        setattr(ls, 'altitudemode', clamptoground)
                
    # --- Export Polygons ---
    if 'Polygon' in geometry_types_to_export:
        # Create folder for polygons - handle different simplekml versions
        poly_folder = getattr(doc, 'newfolder', lambda **kwargs: doc)(name="Polygons")
        # Group data for polygon drawing
        poly_groups = get_line_groups(df, settings.get('line_connection_logic_key','sequential'),
                                            settings.get('custom_line_grouping_column',''),
                                            do_sort=settings.get('sort_points_in_line_group',True))
        poly_layer_prefix = settings.get('dxf_poly_layer_prefix', 'POLY_').strip()
        
        # Iterate through polygon groups and create KML Polygons
        for group_id, group_df in poly_groups.items():
            if len(group_df) < 3: continue # Need at least 3 points for a polygon
            
            coords_for_poly = []
            for _, row_poly in group_df.iterrows():
                try:
                    e_val = row_poly[COL_E]
                    n_val = row_poly[COL_N]
                    try:
                        e_val = float(e_val)
                        n_val = float(n_val)
                    except (ValueError, TypeError):
                        logging.warning(f"Skipping KML polygon point (group '{group_id}', PT: {row_poly.get(COL_PT, 'N/A')}) due to invalid E/N: e={e_val}, n={n_val}")
                        continue
                    if (e_val != e_val or e_val is None) or (n_val != n_val or n_val is None):
                        continue
                    if utm is None:
                        raise ImportError("utm library is not available. Cannot convert UTM to Lat/Lon.")
                    lat_p, lon_p = utm.to_latlon(e_val, n_val, zone_number, zone_letter)
                    z_val = row_poly[COL_Z] if isinstance(row_poly[COL_Z], (int, float)) and row_poly[COL_Z] == row_poly[COL_Z] else 0.0
                    coords_for_poly.append((lon_p, lat_p, z_val))
                except Exception as e_poly_pt:
                    logging.warning(f"Error processing point for KML polygon (group '{group_id}', PT: {row_poly.get(COL_PT, 'N/A')}): {e_poly_pt}")
                
            if len(coords_for_poly) >= 3: # If we have at least 3 valid points
                # Close the polygon if the first and last points are not the same
                if coords_for_poly[0] != coords_for_poly[-1]:
                    coords_for_poly.append(coords_for_poly[0])
                    
                # Create Polygon - handle different simplekml versions
                def create_polygon_fallback(**kwargs):
                    if simplekml is None:
                        raise ImportError("simplekml library is not available")
                    return simplekml.Kml().newpolygon(**kwargs)
                
                poly = getattr(poly_folder, 'newpolygon', 
                              getattr(poly_folder, 'addpolygon', create_polygon_fallback))(
                    name=str(group_id), 
                    outerboundaryis=coords_for_poly
                )
                poly.style = poly_style # Apply polygon style
                # Set altitude mode - handle different simplekml versions
                altitude_mode = getattr(simplekml, 'AltitudeMode', None)
                if altitude_mode:
                    clamptoground = getattr(altitude_mode, 'clamptoground', None)
                    if clamptoground:
                        setattr(poly, 'altitudemode', clamptoground)
                
    # Save the KML/KMZ file
    try:
        # Check if we should save as KMZ (compressed)
        kml_format = settings.get('kml_format', 'KML')
        if kml_format == 'KMZ' and file_path.suffix.lower() == '.kmz':
            # Save as KMZ (compressed KML)
            kml.savekmz(str(file_path))
            logging.info(f"KMZ file successfully saved to {file_path}")
        else:
            # Save as regular KML
            kml.save(str(file_path))
            logging.info(f"KML file successfully saved to {file_path}")
    except Exception as e_save:
        logging.error(f"Error saving KML/KMZ file {file_path}: {e_save}", exc_info=True)
        raise ValueError(f"Failed to save KML/KMZ: {e_save}") from e_save

# ==============================================================================
# START OF GSI REVISED FUNCTIONS (V6 - Leica GSI-16 Standard Format)
# ==============================================================================

def read_gsi_file(file_path: Path):
    """
    V10 - REVISED: Reads a file in the standard Leica GSI-16 format.
    Fixes parsing of signed values and decimal places for the Code field.
    """
    points_data = []
    # Regex to capture GSI word ID, sign, and 16-char data block
    gsi_word_re = re.compile(r'\*?(\d{2})[.\w]*([+-])([\s\S]{16})')

    try:
        with open(file_path, 'r', encoding=detect_encoding(file_path)) as f:
            full_content = f.read()
            all_matches = gsi_word_re.finditer(full_content)
            
            current_point = {}
            for match in all_matches:
                word_id, sign, data_str = match.groups()
                
                if word_id == '11': # Start of a new point
                    if current_point:
                        points_data.append(current_point)
                    
                    # Point ID can be numeric or text (e.g., 'EXISTING')
                    pt_id_str = data_str.strip()
                    if pt_id_str.isdigit():
                        pt_id = str(int(pt_id_str))
                    else:
                        pt_id = pt_id_str if pt_id_str else f"GSI_Pt_{len(points_data)+1}"
                    current_point = {COL_PT: pt_id, COL_E: 0.0, COL_N: 0.0, COL_Z: 0.0, COL_CODE: ""}

                elif current_point: # If a point is being processed
                    try:
                        # V10 FIX: Correctly handle signs and non-numeric codes
                        data_to_parse = data_str.strip()
                        
                        # Check if the data is numeric
                        is_numeric = data_to_parse.replace('.', '', 1).replace('-', '', 1).isdigit()

                        if is_numeric:
                            # If the data string already has a sign, use it. Otherwise, use the GSI sign.
                            if data_to_parse.startswith('-') or data_to_parse.startswith('+'):
                                value = float(data_to_parse)
                            else:
                                value = float(sign + data_to_parse)

                            if word_id in ['81', '21']: # Northing
                                current_point[COL_N] = value / 1000.0
                            elif word_id in ['82', '22']: # Easting
                                current_point[COL_E] = value / 1000.0
                            elif word_id in ['83', '23']: # Elevation
                                current_point[COL_Z] = value / 1000.0
                            elif word_id == '71': # Code
                                # If the raw data string contains spaces, it's likely a direct-entry code.
                                # Otherwise, it's a numeric value in millimeters that needs conversion.
                                if ' ' in data_str:
                                    current_point[COL_CODE] = data_to_parse
                                else:
                                    if value != 0:
                                        code_val = value / 1000.0
                                        current_point[COL_CODE] = f"{code_val:.4f}".rstrip('0').rstrip('.')
                                    else:
                                        current_point[COL_CODE] = "0.0"
                        elif word_id == '71': # If not numeric and it's a code, store as text
                            current_point[COL_CODE] = data_to_parse
                        else: # Not numeric and not a code field
                            raise ValueError("Non-numeric data in a coordinate field")

                    except (ValueError, TypeError):
                        logging.warning(f"GSI: Could not parse data '{sign}{data_str}' for WordID {word_id} on point {current_point.get(COL_PT, 'N/A')}")

        if current_point:
            points_data.append(current_point)
        
        df = pd.DataFrame(points_data)
        
        if not df.empty:
            # Ensure standard columns exist
            for col in STANDARD_COLS:
                if col not in df.columns:
                    if col in [COL_E, COL_N, COL_Z]:
                        df[col] = 0.0
                    else:
                        df[col] = ""
            
            # Final type conversion and cleanup
            df[COL_E] = pd.to_numeric(df[COL_E], errors='coerce').fillna(0.0)
            df[COL_N] = pd.to_numeric(df[COL_N], errors='coerce').fillna(0.0)
            df[COL_Z] = pd.to_numeric(df[COL_Z], errors='coerce').fillna(0.0)
            df[COL_PT] = df[COL_PT].astype(str).fillna("")
            df[COL_CODE] = df[COL_CODE].astype(str).fillna("").replace('nan', '')
        
        return df
    except Exception as e:
        logging.error(f"Error reading GSI file {file_path.name}: {e}", exc_info=True)
        raise


def export_gsi_file(df: pd.DataFrame, file_path: Path):
    """
    V6 - REVISED: Exports data to a file in the standard Leica GSI-16 format.
    """
    def format_gsi_value(value, is_pt=False, is_code=False):
        """Helper to format values into the 16-character GSI string."""
        value_str = str(value).strip()
        
        if is_pt:
            # Point IDs are zero-padded to 16 characters if numeric
            return value_str.zfill(16) if value_str.isdigit() else value_str.ljust(16)
        
        # Coordinates and Code are formatted as signed, zero-padded integers (mm)
        try:
            # For code, if it's not a valid number, default to 0.
            if is_code and not value_str.replace('.', '', 1).replace('-', '', 1).isdigit():
                num_val = 0.0
            else:
                num_val = float(value_str)
            
            # Convert to millimeters
            mm_val = int(round(num_val * 1000.0))
            return f"{mm_val:+017d}"[-17:] # Format to 17 chars with sign, take last 17
        except (ValueError, TypeError):
            return "+0000000000000000"

    try:
        with open(file_path, 'w', encoding='ascii') as f:
            for index, row in df.iterrows():
                pt_id = format_gsi_value(row.get(COL_PT, ''), is_pt=True)
                northing = format_gsi_value(row.get(COL_N, 0.0))
                easting = format_gsi_value(row.get(COL_E, 0.0))
                elevation = format_gsi_value(row.get(COL_Z, 0.0))
                code = format_gsi_value(row.get(COL_CODE, '0'), is_code=True)

                line = (f"*11....+{pt_id} "
                        f"81..40{northing} "
                        f"82..40{easting} "
                        f"83..40{elevation} "
                        f"71....{code}")
                
                f.write(line + "\n")
                
    except IOError as e_io:
        logging.error(f"IOError exporting GSI file {file_path.name}: {e_io}", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"Error exporting GSI file {file_path.name}: {e}", exc_info=True)
        raise

## ==============================================================================
# SDR33 REVISED FUNCTIONS WITH IMPROVED FORMATTING
# ==============================================================================

@functools.lru_cache(maxsize=128)
def read_sdr33_file(file_path: Path):
    """
    REVISED: Reads an SDR file with automatic detection of coordinate order (E-N or N-E)
    and preserves the original number format without adding unnecessary zeros.
    """
    data_list = []
    line_num = 0
    processed_records = 0
    coordinate_order = None  # The order will be determined from the file
    
    # Define the fixed-width SDR33 format from the C# file:
    spec = {'id': (4, 20), 'c1': (20, 36), 'c2': (36, 52), 'z': (52, 68), 'code': (68, 84)}
    
    try:
        # Check file size
        file_size = file_path.stat().st_size
        logging.info(f"File {file_path.name} size: {file_size} bytes")
        
        if file_size == 0:
            logging.warning(f"File {file_path.name} is empty")
            return pd.DataFrame()
        
        encoding = detect_encoding(file_path)
        logging.debug(f"Using encoding='{encoding}' for SDR file {file_path.name}")

        # Read the first few lines to check the file format
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            first_lines = [f.readline().strip() for _ in range(10)]
            f.seek(0)  # Go back to the beginning of the file
            
            # Check the first 100 characters of the file
            f.seek(0)
            first_chars = f.read(100)
            logging.info(f"First 100 characters of {file_path.name}: {repr(first_chars)}")
            f.seek(0)
            
            # Check for SDR33 markers
            has_sdr_header = any(line.startswith('00NM') or line.startswith('10NM') for line in first_lines)
            has_sdr_data = any(line.startswith('08KI') or line.startswith('08TP') for line in first_lines)
            
            # Add detailed diagnostics
            logging.info(f"File {file_path.name} analysis:")
            logging.info(f"  - First 10 lines: {first_lines}")
            logging.info(f"  - Has SDR header: {has_sdr_header}")
            logging.info(f"  - Has SDR data: {has_sdr_data}")
            
            if not (has_sdr_header or has_sdr_data):
                logging.warning(f"File {file_path.name} does not appear to be in SDR33 format. Attempting to read anyway...")

        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            # First pass: Detect coordinate order from the header
            for line in f:
                if line.startswith('13NMCoordinate Format:'):
                    if 'N-E' in line:
                        coordinate_order = 'NEZ'
                    elif 'E-N' in line:
                        coordinate_order = 'ENZ'
                    break
            
            # Go back to the beginning of the file for processing
            f.seek(0)
            
            # Default setting if the header is not found
            if coordinate_order is None:
                coordinate_order = 'NEZ'  # Default: North, East, Elevation
                logging.info("No coordinate order header found in SDR file. Will attempt auto-detection from data.")
            
            logging.info(f"SDR33 coordinate order from header: {coordinate_order} ({'N-E' if coordinate_order == 'NEZ' else 'E-N'})")
            
            sdr_records_found = 0
            for line in f:
                line_num += 1
                line = line.rstrip('\n\r')
                if line.startswith('08KI') or line.startswith('08TP'):
                    sdr_records_found += 1
                    record_type = '08KI' if line.startswith('08KI') else '08TP'
                    
                    logging.debug(f"SDR line {line_num}: Processing {record_type} record with length {len(line)}")

                    try:
                        if record_type in ('08KI', '08TP'):
                            # Use the fixed-width spec for both formats
                            if len(line) < spec['z'][1]:
                                logging.warning(f"SDR line {line_num}: Record is too short (length: {len(line)}). Skipping: {line[:90]}...")
                                continue
                            pt_id = line[spec['id'][0]:spec['id'][1]].strip()
                            coord1_str = line[spec['c1'][0]:spec['c1'][1]].strip()
                            coord2_str = line[spec['c2'][0]:spec['c2'][1]].strip()
                            z_str = line[spec['z'][0]:spec['z'][1]].strip()
                            code = line[spec['code'][0]:spec['code'][1]].strip() if len(line) > spec['code'][0] else ""
                            logging.debug(f"SDR line {line_num}: Fixed-width parsing - PT: {pt_id}, C1: {coord1_str}, C2: {coord2_str}, Z: {z_str}, Code: {code}")
                        else:
                            # Other (rare) formats
                            continue
                        
                        # Add diagnostic details
                        logging.debug(f"SDR line {line_num}: PT='{pt_id}', C1='{coord1_str}', C2='{coord2_str}', Z='{z_str}', Code='{code}'")
                        logging.debug(f"SDR line {line_num}: Coordinate order '{coordinate_order}' - C1 will be {'Northing' if coordinate_order == 'NEZ' else 'Easting'}, C2 will be {'Easting' if coordinate_order == 'NEZ' else 'Northing'}")

                        # Handle null values
                        if not pt_id or pt_id == "":
                            pt_id = f"SDR_Pt_{len(data_list)+1}"
                        
                        # Convert coordinates to numbers
                        try:
                            coord1_val = float(coord1_str) if coord1_str and coord1_str.strip() else 0.0
                        except (ValueError, TypeError):
                            logging.warning(f"SDR line {line_num}: Invalid coord1 value '{coord1_str}'. Using 0.0")
                            coord1_val = 0.0
                            
                        try:
                            coord2_val = float(coord2_str) if coord2_str and coord2_str.strip() else 0.0
                        except (ValueError, TypeError):
                            logging.warning(f"SDR line {line_num}: Invalid coord2 value '{coord2_str}'. Using 0.0")
                            coord2_val = 0.0
                            
                        try:
                            z_val = float(z_str) if z_str and z_str.strip() else 0.0
                        except (ValueError, TypeError):
                            logging.warning(f"SDR line {line_num}: Invalid elevation value '{z_str}'. Using 0.0")
                            z_val = 0.0
                        
                        # Check that the record contains valid data
                        if coord1_val == 0.0 and coord2_val == 0.0 and z_val == 0.0:
                            logging.warning(f"SDR line {line_num}: All coordinates are zero. Skipping point {pt_id}")
                            continue
                        
                        # Check that the record contains non-empty data
                        if not coord1_str.strip() and not coord2_str.strip() and not z_str.strip():
                            logging.warning(f"SDR line {line_num}: All coordinate fields are empty. Skipping point {pt_id}")
                            continue
                        
                        # Check that the record contains at least some valid data
                        valid_coords = 0
                        if coord1_str.strip() and coord1_val != 0.0: valid_coords += 1
                        if coord2_str.strip() and coord2_val != 0.0: valid_coords += 1
                        if z_str.strip() and z_val != 0.0: valid_coords += 1
                        
                        if valid_coords == 0:
                            logging.warning(f"SDR line {line_num}: No valid coordinates found. Skipping point {pt_id}")
                            continue

                        # Create the data record while preserving the original format
                        if record_type == '08TP':
                            # 08TP format: coord1 = Easting, coord2 = Northing (fixed)
                            point_data = {
                                COL_PT: pt_id,
                                COL_E: coord1_val,  # Easting
                                COL_N: coord2_val,  # Northing
                                COL_Z: z_val,
                                COL_CODE: code if code else "",
                                COL_DESC: "",  # Add an empty description column
                            }
                        else:
                            # 08KI format: coord1 = Northing, coord2 = Easting (depending on coordinate order)
                            point_data = {
                                COL_PT: pt_id,
                                COL_N: coord1_val if coordinate_order == 'NEZ' else coord2_val,
                                COL_E: coord2_val if coordinate_order == 'NEZ' else coord1_val,
                                COL_Z: z_val,
                                COL_CODE: code if code else "",
                                COL_DESC: "",  # Add an empty description column
                            }
                        
                        # Add detailed diagnostic for coordinates
                        logging.debug(f"SDR line {line_num}: Final coordinates - PT: {pt_id}, N: {point_data[COL_N]}, E: {point_data[COL_E]}, Z: {point_data[COL_Z]}, Code: {point_data[COL_CODE]}")
                        logging.debug(f"SDR line {line_num}: Raw values - coord1: {coord1_val}, coord2: {coord2_val}, z: {z_val}, coordinate_order: {coordinate_order}")
                        data_list.append(point_data)
                        processed_records += 1
                        logging.debug(f"SDR line {line_num}: Successfully processed point {pt_id}")

                    except (ValueError, IndexError) as ve:
                        logging.warning(f"SDR line {line_num}: Skipping record due to error: {ve}")

        if not data_list:
            if sdr_records_found > 0:
                logging.warning(f"Found {sdr_records_found} SDR33 records in {file_path.name}, but none had valid coordinate data.")
            else:
                # Analyze the entire file content to search for other formats
                with open(file_path, 'r', encoding=encoding, errors='replace') as analyze_f:
                    all_lines = analyze_f.readlines()
                    logging.info(f"File {file_path.name} contains {len(all_lines)} lines total")
                    
                    # Search for different patterns
                    patterns_found = {
                        '08KI': sum(1 for line in all_lines if line.startswith('08KI')),
                        '08TP': sum(1 for line in all_lines if line.startswith('08TP')),
                        '00NM': sum(1 for line in all_lines if line.startswith('00NM')),
                        '10NM': sum(1 for line in all_lines if line.startswith('10NM')),
                        '13NM': sum(1 for line in all_lines if line.startswith('13NM')),
                        'empty': sum(1 for line in all_lines if not line.strip()),
                        'numeric_start': sum(1 for line in all_lines if line.strip() and line.strip()[0].isdigit()),
                        'comma_separated': sum(1 for line in all_lines if ',' in line and len(line.split(',')) > 3),
                        'tab_separated': sum(1 for line in all_lines if '\t' in line and len(line.split('\t')) > 3),
                    }
                    
                    logging.info(f"File analysis results:")
                    for pattern, count in patterns_found.items():
                        if count > 0:
                            logging.info(f"  - {pattern}: {count} lines")
                    
                    # Suggest a possible format
                    if patterns_found['08TP'] > 0:
                        logging.info(f"  - Suggestion: This is a valid SDR33 file with 08TP format (Total Station Points)")
                    elif patterns_found['08KI'] > 0:
                        logging.info(f"  - Suggestion: This is a valid SDR33 file with 08KI format")
                    elif patterns_found['comma_separated'] > 0:
                        logging.info(f"  - Suggestion: This might be a CSV file")
                    elif patterns_found['tab_separated'] > 0:
                        logging.info(f"  - Suggestion: This might be a tab-separated file")
                    elif patterns_found['numeric_start'] > 0:
                        logging.info(f"  - Suggestion: This might be a space-separated coordinate file")
                    elif patterns_found['empty'] == len(all_lines):
                        logging.info(f"  - Suggestion: File appears to be empty")
                    else:
                        logging.info(f"  - Suggestion: Unknown format, try CSV or TXT import")
                    
                    if patterns_found.get('08TP', 0) > 0:
                        logging.warning(f"File {file_path.name} contains {patterns_found['08TP']} 08TP records but no 08KI records. This appears to be a Total Station SDR33 format.")
                    else:
                        logging.warning(f"File {file_path.name} does not appear to be a valid SDR33 format file (no 08KI or 08TP records found).")
                
            return pd.DataFrame()

        # Convert to DataFrame while preserving the original format
        df = pd.DataFrame(data_list)
        logging.info(f"Successfully read {len(data_list)} points from SDR33 file: {file_path.name} (found {sdr_records_found} SDR records, processed {processed_records} valid records)")
        
        # Automatic detection of coordinate order if not specified in the header
        # Note: We don't need auto-detection with 08TP because its order is fixed
        if coordinate_order == 'NEZ' and data_list:  # If it's the default and data was found
            logging.info("Coordinate order auto-detection is not needed for 08TP format (fixed order: E-N)")
            logging.info("08TP format always uses: coord1=Easting, coord2=Northing")
            coordinate_order = 'ENZ'  # Confirm the order for 08TP
        
        logging.info(f"Final coordinate order: {coordinate_order} ({'N-E' if coordinate_order == 'NEZ' else 'E-N'})")
        
        # Final handling of null values
        if not df.empty:
            # Numeric columns
            for col in [COL_E, COL_N, COL_Z]:
                if col in df.columns:
                    df[col] = df[col].fillna(0.0)
            
            # Text columns
            for col in [COL_PT, COL_CODE, COL_DESC]:
                if col in df.columns:
                    df[col] = df[col].fillna("")
                    df[col] = df[col].astype(str).replace(['nan', 'NaN', 'NAN', 'None', 'NULL'], '')
        
        return df

    except Exception as e:
        logging.exception(f"SDR Import Error for {file_path.name}: {e}")
        raise

def export_sdr33_file(df: pd.DataFrame, file_path: Path, coordinate_order: str = 'NEZ'):
    """
    REVISED: Exports data to an SDR file while maintaining the fixed format
    and displaying numbers as they are without adding unnecessary zeros.
    """
    def format_sdr_field(series, width, align='left', is_numeric=False):
        """
        Vectorized function to format a pandas Series for SDR fields.
        """
        if is_numeric:
            # Convert to numeric, then format. Coerce errors to empty strings.
            series = pd.to_numeric(series, errors='coerce').apply(
                lambda x: '' if pd.isna(x) else (str(int(x)) if x == int(x) else str(x))
            )
        else:
            series = series.astype(str).fillna('')

        if align == 'right':
            return series.str.rjust(width).str[:width]
        return series.str.ljust(width).str[:width]

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            # Write the header
            f.write("00NMSDR33                               111111\n")
            f.write("10NM>RED EXPORT 33  121111\n")
            f.write("13NMAngle Unit: Degrees                                         \n")
            f.write("13DU1:Meters:                                                   \n")
            f.write(f"13NMCoordinate Format: {'E-N' if coordinate_order == 'ENZ' else 'N-E'}                                      \n")
            f.write("13NMPressure Unit: MmHg                                         \n")
            f.write("13NMTempurature Unit: Celsius                                   \n")
            f.write("13CCPlane Curvature Correction: Yes                             \n")

            # Prepare data columns
            df_export = df.copy()
            df_export['pt_id'] = format_sdr_field(df_export.get(COL_PT, ''), 16, align='right')
            
            coord1_col = COL_N if coordinate_order == 'NEZ' else COL_E
            coord2_col = COL_E if coordinate_order == 'NEZ' else COL_N
            
            df_export['coord1'] = format_sdr_field(df_export.get(coord1_col), 16, align='left', is_numeric=True)
            df_export['coord2'] = format_sdr_field(df_export.get(coord2_col), 16, align='left', is_numeric=True)
            df_export['elev'] = format_sdr_field(df_export.get(COL_Z), 16, align='left', is_numeric=True)
            df_export['code'] = format_sdr_field(df_export.get(COL_CODE, ''), 16)

            # Create the lines and write to file
            lines = "08KI" + df_export['pt_id'] + df_export['coord1'] + df_export['coord2'] + df_export['elev'] + df_export['code'] + "\n"
            f.writelines(lines.tolist())

    except Exception as e:
        logging.error(f"An error occurred while exporting the SDR file {file_path.name}: {e}", exc_info=True)
        raise
