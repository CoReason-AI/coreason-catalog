import shutil
from pathlib import Path

import pytest
from coreason_catalog.services.policy_engine import PolicyEngine

# Check if opa binary exists
OPA_EXISTS = shutil.which("opa") is not None or Path("bin/opa").exists() or Path("/usr/local/bin/opa").exists()


@pytest.mark.skipif(not OPA_EXISTS, reason="OPA binary not found")
class TestPolicyEngineIntegration:
    @pytest.fixture  # type: ignore[misc]
    def engine(self) -> PolicyEngine:
        # Auto-discover the binary
        return PolicyEngine()

    def test_complex_rego_logic(self, engine: PolicyEngine) -> None:
        """Test a policy using array comprehensions and built-in functions."""
        policy = """
        package complex.test
        import rego.v1

        allow if {
            # Check if user has "admin" role
            some i
            input.user.roles[i] == "admin"

            # Check if access time is within window (dummy check using numbers)
            input.request.time >= 900
            input.request.time <= 1700

            # Count verify
            count(input.user.roles) >= 2
        }
        """

        valid_input = {"user": {"roles": ["editor", "admin"]}, "request": {"time": 1000}}

        assert engine.evaluate_policy(policy, valid_input) is True

        invalid_input = {"user": {"roles": ["guest"]}, "request": {"time": 1000}}
        assert engine.evaluate_policy(policy, invalid_input) is False

    def test_large_input_payload(self, engine: PolicyEngine) -> None:
        """Test evaluating a policy with a large input payload."""
        # Create a large list of items
        items = [{"id": i, "value": i * 2} for i in range(10000)]

        policy = """
        package large.payload
        import rego.v1

        allow if {
            # Verify sum of values is correct (just to force processing)
            # Rego sum is not built-in for lists directly without comprehension,
            # let's just check existence of a specific item

            some i
            input.items[i].id == 9999
            input.items[i].value == 19998
        }
        """

        input_data = {"items": items}

        assert engine.evaluate_policy(policy, input_data) is True

    def test_multiple_rules(self, engine: PolicyEngine) -> None:
        """Test a policy with multiple rules (OR logic)."""
        policy = """
        package multi.rules
        import rego.v1

        default allow := false

        allow if {
            input.role == "admin"
        }

        allow if {
            input.role == "editor"
            input.action == "read"
        }
        """

        # Rule 1 match
        assert engine.evaluate_policy(policy, {"role": "admin", "action": "delete"}) is True

        # Rule 2 match
        assert engine.evaluate_policy(policy, {"role": "editor", "action": "read"}) is True

        # No match
        assert engine.evaluate_policy(policy, {"role": "editor", "action": "delete"}) is False

    def test_policy_with_helper_functions(self, engine: PolicyEngine) -> None:
        """Test a policy that defines and uses helper functions."""
        policy = """
        package helpers
        import rego.v1

        is_adult(age) if {
            age >= 18
        }

        allow if {
            is_adult(input.user.age)
        }
        """

        assert engine.evaluate_policy(policy, {"user": {"age": 20}}) is True
        assert engine.evaluate_policy(policy, {"user": {"age": 10}}) is False
