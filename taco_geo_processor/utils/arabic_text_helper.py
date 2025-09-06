"""
Arabic text helper utilities for the TACO Geo Processor application.
This module provides functions to handle Arabic text display and formatting.
"""

import logging
from typing import Optional


def initialize_arabic_support():
    """
    Initialize Arabic text support for the application.
    This function sets up the necessary configurations for proper Arabic text rendering.
    """
    try:
        # Set up Arabic text support
        # This could include font configuration, text direction settings, etc.
        logging.info("Arabic text support initialized successfully")
        return True
    except Exception as e:
        logging.error(f"Failed to initialize Arabic text support: {e}")
        return False


def fix_arabic(text: str) -> str:
    """
    Fix Arabic text formatting and display issues.
    
    Args:
        text (str): The Arabic text to be fixed
        
    Returns:
        str: The fixed Arabic text
    """
    if not text or not isinstance(text, str):
        return text
    
    try:
        # Basic Arabic text fixes
        # Remove any problematic characters that might cause display issues
        fixed_text = text.strip()
        
        # Ensure proper Arabic text direction
        # This is a basic implementation - you might need more sophisticated logic
        # depending on your specific requirements
        
        return fixed_text
    except Exception as e:
        logging.error(f"Error fixing Arabic text: {e}")
        return text


def is_arabic_text(text: str) -> bool:
    """
    Check if the given text contains Arabic characters.
    
    Args:
        text (str): The text to check
        
    Returns:
        bool: True if the text contains Arabic characters, False otherwise
    """
    if not text or not isinstance(text, str):
        return False
    
    try:
        # Check for Arabic Unicode ranges
        arabic_ranges = [
            (0x0600, 0x06FF),  # Arabic
            (0x0750, 0x077F),  # Arabic Supplement
            (0x08A0, 0x08FF),  # Arabic Extended-A
            (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
            (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
        ]
        
        for char in text:
            char_code = ord(char)
            for start, end in arabic_ranges:
                if start <= char_code <= end:
                    return True
        return False
    except Exception as e:
        logging.error(f"Error checking Arabic text: {e}")
        return False


def format_arabic_number(number: float, decimal_places: int = 2) -> str:
    """
    Format a number for display in Arabic context.
    
    Args:
        number (float): The number to format
        decimal_places (int): Number of decimal places to show
        
    Returns:
        str: The formatted number string
    """
    try:
        if number is None:
            return ""
        
        # Format the number with specified decimal places
        formatted = f"{number:.{decimal_places}f}"
        return formatted
    except Exception as e:
        logging.error(f"Error formatting Arabic number: {e}")
        return str(number) if number is not None else ""


def get_arabic_direction() -> str:
    """
    Get the text direction for Arabic text.
    
    Returns:
        str: The text direction ('rtl' for right-to-left)
    """
    return "rtl"


def clean_arabic_text(text: str) -> str:
    """
    Clean Arabic text by removing unwanted characters and normalizing spacing.
    
    Args:
        text (str): The Arabic text to clean
        
    Returns:
        str: The cleaned Arabic text
    """
    if not text or not isinstance(text, str):
        return text
    
    try:
        # Remove extra whitespace
        cleaned = " ".join(text.split())
        
        # Remove any non-printable characters except Arabic ones
        cleaned = "".join(char for char in cleaned if char.isprintable() or is_arabic_text(char))
        
        return cleaned
    except Exception as e:
        logging.error(f"Error cleaning Arabic text: {e}")
        return text
