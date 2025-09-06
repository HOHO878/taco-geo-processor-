# -*- coding: utf-8 -*-
"""
Custom exception classes for the TacoGeoProcessor application.
"""

class TacoBaseException(Exception):
    """Base exception class for all application-specific errors."""
    pass

class FileProcessingError(TacoBaseException):
    """Raised for errors during file import or export operations."""
    pass

class DataValidationError(TacoBaseException):
    """Raised when input data fails validation checks."""
    pass

class ConfigurationError(TacoBaseException):
    """Raised for errors related to application configuration."""
    pass

class OperationCancelledError(TacoBaseException):
    """Raised when a user manually cancels an operation."""
    pass

class UIError(TacoBaseException):
    """Raised for errors related to the user interface."""
    pass

class KMLGenerationError(FileProcessingError):
    """Raised for specific errors during KML file generation."""
    pass

class DXFGenerationError(FileProcessingError):
    """Raised for specific errors during DXF file generation."""
    pass
