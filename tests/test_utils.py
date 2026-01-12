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
from unittest.mock import MagicMock, patch

from coreason_catalog.utils import logger as logger_module


def test_logger_directory_creation() -> None:
    """Test that the logs directory is created if it does not exist."""
    with patch("pathlib.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_cls.return_value = mock_path_instance
        mock_path_instance.exists.return_value = False

        # We must import the module again after invalidating it or use reload properly
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
