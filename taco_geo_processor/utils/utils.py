from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import QSize, Qt
import os

DEFAULT_ICON_SIZE = 32

import sys
import os

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

ICONS_DIR = os.path.join(BASE_DIR, 'icons')

def get_icon(filename, size=DEFAULT_ICON_SIZE, color=None):
    """
    Returns a QIcon from a file in the icons folder with a custom size and optional color.
    If a color is provided, the icon will be colorized.
    """
    path = os.path.join(ICONS_DIR, filename)
    if not os.path.exists(path):
        return QIcon()

    pixmap = QPixmap(path)
    if pixmap.isNull():
        return QIcon()

    if color:
        # Create a temporary pixmap to work on, fill it with the target color
        color_pixmap = QPixmap(pixmap.size())
        color_pixmap.fill(QColor(color))
        
        # Use the original pixmap as an alpha mask
        color_pixmap.setMask(pixmap.createMaskFromColor(Qt.GlobalColor.transparent))
        pixmap = color_pixmap

    if size:
        pixmap = pixmap.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    
    return QIcon(pixmap)

def safe_float(val, default=0.0):
    """Safely convert a value to float, returning a default if the conversion fails."""
    try:
        if val is None or val == '' or (hasattr(val, 'isna') and val.isna()):
            return default
        return float(val)
    except Exception:
        return default

TXT_DELIMITER_MAP = {
    'Tab': '\t',
    'Comma': ',',
    'Semicolon': ';',
    'Pipe': '|',
    'Space': ' '
}

def get_temp_dir():
    """Creates and returns the path to a temporary directory for the application."""
    import tempfile
    # Create a specific subdirectory for our app's temp files
    temp_dir = os.path.join(tempfile.gettempdir(), "SurveyConverterPro_Previews")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir
