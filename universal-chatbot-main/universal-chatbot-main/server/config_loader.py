"""
Configuration loader for RAG server.

DEPRECATED: This module is deprecated. Use app.core.settings instead.

    from app.core.settings import settings

This module now serves as a compatibility layer that redirects to the new
centralized settings. All functionality is preserved for backwards compatibility.
"""
import warnings

# Emit deprecation warning on import
warnings.warn(
    "config_loader is deprecated. Use 'from app.core.settings import settings' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from new location for backwards compatibility
from app.core.settings import settings

# Also export as Config for any code using the class directly
Config = settings.__class__

# For any code that imports specific attributes
__all__ = ['settings', 'Config']
