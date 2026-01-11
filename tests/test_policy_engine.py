from unittest.mock import MagicMock, patch

import pytest

from coreason_catalog.services.policy_engine import PolicyEngine


@pytest.fixture  # type: ignore[misc]
def policy_engine() -> PolicyEngine:
    # We use the real binary if available (which it should be in sandbox),
    # but we can fallback or mock if needed.
    # For now, let's try to use the auto-discovery.
    return PolicyEngine()


def test_find_opa(policy_engine: PolicyEngine) -> None:
    assert policy_engine.opa_path is not None
    assert "opa" in policy_engine.opa_path


def test_evaluate_simple_allow(policy_engine: PolicyEngine) -> None:
    policy = 'allow { input.user == "admin" }'

    # Matching input
    assert policy_engine.evaluate_policy(policy, {"user": "admin"}) is True

    # Non-matching input
    assert policy_engine.evaluate_policy(policy, {"user": "guest"}) is False


def test_evaluate_complex_policy(policy_engine: PolicyEngine) -> None:
    policy = """
    allow {
        input.subject.location == input.object.geo
        input.subject.level >= input.object.level
    }
    """

    # Match
    input_data = {"subject": {"location": "US", "level": 3}, "object": {"geo": "US", "level": 2}}
    assert policy_engine.evaluate_policy(policy, input_data) is True

    # Mismatch location
    input_data_loc = {"subject": {"location": "EU", "level": 3}, "object": {"geo": "US", "level": 2}}
    assert policy_engine.evaluate_policy(policy, input_data_loc) is False

    # Mismatch level
    input_data_lvl = {"subject": {"location": "US", "level": 1}, "object": {"geo": "US", "level": 2}}
    assert policy_engine.evaluate_policy(policy, input_data_lvl) is False


def test_custom_package_name(policy_engine: PolicyEngine) -> None:
    policy = """
    package custom.rules

    allow {
        input.x == 1
    }
    """
    assert policy_engine.evaluate_policy(policy, {"x": 1}) is True
    assert policy_engine.evaluate_policy(policy, {"x": 2}) is False


def test_invalid_rego_syntax(policy_engine: PolicyEngine) -> None:
    policy = "allow { input.x == "  # Syntax error

    with pytest.raises(RuntimeError) as excinfo:
        policy_engine.evaluate_policy(policy, {"x": 1})

    assert "OPA execution failed" in str(excinfo.value)


@patch("subprocess.run")
def test_opa_execution_failure(mock_run: MagicMock, policy_engine: PolicyEngine) -> None:
    # Simulate a binary failure not related to syntax (e.g. segfault or other error)
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "Fatal error"
    mock_run.return_value.stdout = ""

    with pytest.raises(RuntimeError, match="OPA execution failed"):
        policy_engine.evaluate_policy("allow { true }", {})


@patch("coreason_catalog.services.policy_engine.shutil.which")
@patch("pathlib.Path.exists")
def test_opa_not_found(mock_exists: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = None
    mock_exists.return_value = False

    engine = PolicyEngine(opa_path=None)
    assert engine.opa_path is None

    with pytest.raises(RuntimeError, match="OPA binary is not configured"):
        engine.evaluate_policy("allow { true }", {})
