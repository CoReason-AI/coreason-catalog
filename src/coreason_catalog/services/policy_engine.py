import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from coreason_catalog.utils.logger import logger


class PolicyEngine:
    """
    Wrapper around the Open Policy Agent (OPA) binary for evaluating Rego policies.
    """

    def __init__(self, opa_path: Optional[str] = None):
        """
        Initialize the PolicyEngine.

        Args:
            opa_path: Path to the OPA binary. If None, tries to find it in PATH or local bin/.
        """
        self.opa_path = opa_path or self._find_opa()
        if not self.opa_path:
            logger.warning("OPA binary not found. Policy evaluation will fail.")

    def _find_opa(self) -> Optional[str]:
        """Find the OPA binary."""
        # Check PATH
        path = shutil.which("opa")
        if path:
            return path

        # Check local bin/
        local_bin = Path("bin/opa")
        if local_bin.exists() and local_bin.is_file():
            return str(local_bin.resolve())

        # Check /usr/local/bin explicit (sometimes shutil.which might miss if path not set)
        usr_bin = Path("/usr/local/bin/opa")
        if usr_bin.exists():
            return str(usr_bin)

        return None

    def evaluate_policy(self, policy_code: str, input_data: Dict[str, Any]) -> bool:
        """
        Evaluate a Rego policy against input data.

        Assumes the policy defines a rule `allow`.
        If the policy does not contain a package declaration, `package match` is prepended.

        Args:
            policy_code: The Rego policy string.
            input_data: The input data dictionary.

        Returns:
            True if the policy evaluates to True, False otherwise.

        Raises:
            RuntimeError: If OPA execution fails.
        """
        if not self.opa_path:
            raise RuntimeError("OPA binary is not configured.")

        # normalize policy code
        final_policy = policy_code
        package_name = "match"
        if "package " not in policy_code:
            final_policy = f"package {package_name}\n\n{policy_code}"
        else:
            # simple heuristic to find package name if needed, but for now we assume
            # if they provide package, they know what they are doing.
            # BUT, we query `data.match.allow` by default.
            # If they use a different package, our query will fail.
            # For this MVP, we enforce the rule: "Do not include package header, or use package match".
            # Or we can regex extract it.
            # Let's try to extract package name.
            import re

            match = re.search(r"package\s+([a-zA-Z0-9_.]+)", policy_code)
            if match:
                package_name = match.group(1)
            else:
                # Should not happen if "package " is in string
                pass

        query = f"data.{package_name}.allow"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".rego", delete=False) as policy_file:
            policy_file.write(final_policy)
            policy_path = policy_file.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as input_file:
            json.dump(input_data, input_file)
            input_path = input_file.name

        try:
            cmd = [self.opa_path, "eval", "--format", "json", "-d", policy_path, "-i", input_path, query]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                error_msg = f"OPA execution failed. CMD: {cmd}, STDERR: {result.stderr}, STDOUT: {result.stdout}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            output = json.loads(result.stdout)

            # Check if result is defined and true
            # output structure: {"result": [{"expressions": [{"value": true, ...}]}]}
            # If rule is undefined (false), result might be empty or value missing

            if "result" in output and len(output["result"]) > 0:
                expressions = output["result"][0].get("expressions", [])
                if expressions:
                    value = expressions[0].get("value")
                    return bool(value)

            return False

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OPA output: {e}")
            raise RuntimeError(f"Failed to parse OPA output: {e}") from e
        except Exception as e:
            logger.error(f"Error evaluating policy: {e}")
            raise e
        finally:
            # Cleanup
            Path(policy_path).unlink(missing_ok=True)
            Path(input_path).unlink(missing_ok=True)
