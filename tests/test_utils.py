# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_catalog

import importlib
import sys
from unittest.mock import MagicMock, patch

# To avoid importing the 'logger' object instead of the module, we need to bypass the package import
# or inspect sys.modules directly.
# The issue is that `from coreason_catalog.utils import logger` gives us the object because of __init__.py export.
# But `import coreason_catalog.utils.logger` should strictly be the module... UNLESS `coreason_catalog.utils` has
# 'logger' in its namespace (which it does, from the __init__.py) which shadows the submodule.
# Workaround: Import via sys.modules or use import_module with absolute path, checking what we get.
from coreason_catalog.utils import logger as potential_logger_module

# If it is the object, we need to get the actual module
if not isinstance(potential_logger_module, type(sys)):
    # It's not a module, it's the object.
    # We can try to get the module from sys.modules if it's loaded
    if "coreason_catalog.utils.logger" in sys.modules:
        logger_module = sys.modules["coreason_catalog.utils.logger"]
    else:
        # This shouldn't happen if we imported it, but...
        logger_module = importlib.import_module("coreason_catalog.utils.logger")
else:
    logger_module = potential_logger_module


def test_logger_directory_creation() -> None:
    """Test that the logs directory is created if it does not exist."""
    with patch("pathlib.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_cls.return_value = mock_path_instance
        mock_path_instance.exists.return_value = False

        # We must reload the specific module file
        importlib.reload(logger_module)

        # Verify
        mock_path_cls.assert_called_with("logs")
        mock_path_instance.mkdir.assert_called_with(parents=True, exist_ok=True)


def test_logger_directory_exists() -> None:
    """Test that mkdir is not called if logs directory exists."""
    with patch("pathlib.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_cls.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True

        importlib.reload(logger_module)

        mock_path_instance.mkdir.assert_not_called()
