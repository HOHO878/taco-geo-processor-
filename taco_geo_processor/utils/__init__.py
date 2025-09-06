"""
Utilities package for the TACO Geo Processor application.
This package contains various utility functions and helpers.
"""

from .arabic_text_helper import (
    initialize_arabic_support,
    fix_arabic,
    is_arabic_text,
    format_arabic_number,
    get_arabic_direction,
    clean_arabic_text
)

__all__ = [
    'initialize_arabic_support',
    'fix_arabic',
    'is_arabic_text',
    'format_arabic_number',
    'get_arabic_direction',
    'clean_arabic_text'
]
