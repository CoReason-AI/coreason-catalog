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
import types
from unittest.mock import MagicMock, patch


# Ensure we have the module, not the object
# We use a helper function to safely get the module for reloading
def get_logger_module() -> types.ModuleType:
    module_name = "coreason_catalog.utils.logger"
    if module_name in sys.modules:
        return sys.modules[module_name]
    else:
        return importlib.import_module(module_name)


def test_logger_directory_creation() -> None:
    """Test that the logs directory is created if it does not exist."""
    logger_module = get_logger_module()

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
    logger_module = get_logger_module()

    with patch("pathlib.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_cls.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True

        importlib.reload(logger_module)

        mock_path_instance.mkdir.assert_not_called()
