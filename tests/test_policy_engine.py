import json
from unittest.mock import MagicMock, patch

import pytest

from coreason_catalog.services.policy_engine import PolicyEngine


@pytest.fixture  # type: ignore[misc]
def policy_engine() -> PolicyEngine:
    # Use a mock path to avoid looking for the real binary
    return PolicyEngine(opa_path="/mock/opa")


@patch("coreason_catalog.services.policy_engine.shutil.which")
@patch("coreason_catalog.services.policy_engine.Path")
def test_find_opa(mock_path: MagicMock, mock_which: MagicMock) -> None:
    # Case 1: Found in PATH
    mock_which.return_value = "/usr/bin/opa"
    engine = PolicyEngine()
    assert engine.opa_path == "/usr/bin/opa"

    # Case 2: Found in bin/
    mock_which.return_value = None
    # Mock Path("bin/opa").exists() -> True
    # We need to handle the chain of calls: Path("bin/opa").exists() and .is_file()

    # Reset mocks
    mock_path_instance = MagicMock()
    mock_path.return_value = mock_path_instance

    # Configure so that when initialized with "bin/opa", it exists
    def path_side_effect(arg: str) -> MagicMock:
        m = MagicMock()
        if arg == "bin/opa":
            m.exists.return_value = True
            m.is_file.return_value = True
            m.resolve.return_value = "/abs/bin/opa"
        else:
            m.exists.return_value = False
        return m

    mock_path.side_effect = path_side_effect

    engine = PolicyEngine()
    assert engine.opa_path == "/abs/bin/opa"

    # Case 3: Found in /usr/local/bin
    def path_side_effect_usr(arg: str) -> MagicMock:
        m = MagicMock()
        if arg == "/usr/local/bin/opa":
            m.exists.return_value = True
            m.__str__.return_value = "/usr/local/bin/opa"  # type: ignore[attr-defined]
        else:
            m.exists.return_value = False
        return m

    mock_path.side_effect = path_side_effect_usr
    engine = PolicyEngine()
    assert engine.opa_path == "/usr/local/bin/opa"

    # Case 4: Not found
    mock_path.side_effect = lambda x: MagicMock(exists=lambda: False)
    engine = PolicyEngine()
    assert engine.opa_path is None


@patch("subprocess.run")
def test_evaluate_simple_allow(mock_run: MagicMock, policy_engine: PolicyEngine) -> None:
    policy = 'allow { input.user == "admin" }'

    # Mock success response
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps({"result": [{"expressions": [{"value": True}]}]})

    # Matching input
    assert policy_engine.evaluate_policy(policy, {"user": "admin"}) is True

    # Mock failure response (rule not matched -> value is usually missing or False depending on OPA query)
    # If we query data.match.allow and it's undefined, OPA result is empty result: {} or {"result": []}
    mock_run.return_value.stdout = json.dumps({"result": []})

    # Non-matching input
    assert policy_engine.evaluate_policy(policy, {"user": "guest"}) is False


@patch("subprocess.run")
def test_evaluate_complex_policy(mock_run: MagicMock, policy_engine: PolicyEngine) -> None:
    policy = """
    allow {
        input.subject.location == input.object.geo
    }
    """

    # Match
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps({"result": [{"expressions": [{"value": True}]}]})

    input_data = {"subject": {"location": "US"}, "object": {"geo": "US"}}
    assert policy_engine.evaluate_policy(policy, input_data) is True

    # Verify the call arguments contained the correct query
    args, _ = mock_run.call_args
    cmd = args[0]
    assert "data.match.allow" in cmd

    # Mismatch
    mock_run.return_value.stdout = json.dumps({"result": []})
    input_data_loc = {"subject": {"location": "EU"}, "object": {"geo": "US"}}
    assert policy_engine.evaluate_policy(policy, input_data_loc) is False


@patch("subprocess.run")
def test_custom_package_name(mock_run: MagicMock, policy_engine: PolicyEngine) -> None:
    policy = """
    package custom.rules

    allow {
        input.x == 1
    }
    """

    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps({"result": [{"expressions": [{"value": True}]}]})

    assert policy_engine.evaluate_policy(policy, {"x": 1}) is True

    # Verify the query used the custom package
    args, _ = mock_run.call_args
    cmd = args[0]
    assert "data.custom.rules.allow" in cmd


@patch("subprocess.run")
def test_invalid_rego_syntax(mock_run: MagicMock, policy_engine: PolicyEngine) -> None:
    policy = "allow { input.x == "  # Syntax error

    # Simulate OPA error output
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "rego_parse_error: illegal token"
    mock_run.return_value.stdout = ""

    with pytest.raises(RuntimeError) as excinfo:
        policy_engine.evaluate_policy(policy, {"x": 1})

    assert "OPA execution failed" in str(excinfo.value)


@patch("subprocess.run")
def test_opa_execution_failure(mock_run: MagicMock, policy_engine: PolicyEngine) -> None:
    # Simulate a binary failure
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
