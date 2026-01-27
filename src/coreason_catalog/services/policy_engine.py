import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from coreason_identity.models import UserContext

from coreason_catalog.models import SourceManifest
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

    def evaluate_policy(self, policy_code: str, input_data: Dict[str, Any], timeout: float = 5.0) -> bool:
        """
        Evaluate a Rego policy against input data.

        Assumes the policy defines a rule `allow`.
        If the policy does not contain a package declaration, `package match` is prepended.

        Args:
            policy_code: The Rego policy string.
            input_data: The input data dictionary.
            timeout: Timeout in seconds for the OPA process.

        Returns:
            True if the policy evaluates to True, False otherwise.

        Raises:
            RuntimeError: If OPA execution fails, times out, or returns invalid data.
            ValueError: If input data cannot be serialized.
        """
        if not self.opa_path:
            raise RuntimeError("OPA binary is not configured.")

        if not policy_code or not policy_code.strip():
            logger.error("Empty policy code provided.")
            return False

        # normalize policy code
        final_policy = policy_code
        package_name = "match"
        if "package " not in policy_code:
            final_policy = f"package {package_name}\n\n{policy_code}"
        else:
            import re

            match = re.search(r"package\s+([a-zA-Z0-9_.]+)", policy_code)
            if match:
                package_name = match.group(1)
            else:
                pass

        query = f"data.{package_name}.allow"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".rego", delete=False) as policy_file:
            policy_file.write(final_policy)
            policy_path = policy_file.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as input_file:
            try:
                json.dump(input_data, input_file)
            except (TypeError, ValueError) as e:
                logger.error(f"Failed to serialize input data: {e}")
                # Clean up policy file since we won't proceed
                Path(policy_path).unlink(missing_ok=True)
                # Cleanup handled by finally but we raise here
                raise ValueError(f"Invalid input data: {e}") from e
            input_path = input_file.name

        try:
            cmd = [self.opa_path, "eval", "--format", "json", "-d", policy_path, "-i", input_path, query]

            # Run with timeout
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

            if result.returncode != 0:
                error_msg = f"OPA execution failed. CMD: {cmd}, STDERR: {result.stderr}, STDOUT: {result.stdout}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            output = json.loads(result.stdout)

            # Check if result is defined and true
            if "result" in output and len(output["result"]) > 0:
                expressions = output["result"][0].get("expressions", [])
                if expressions:
                    value = expressions[0].get("value")
                    if not isinstance(value, bool):
                        logger.warning(f"Policy returned non-boolean value: {value} (type: {type(value)})")
                        return False
                    return value

            return False

        except subprocess.TimeoutExpired as e:
            logger.error(f"OPA execution timed out after {timeout} seconds")
            raise RuntimeError(f"OPA execution timed out after {timeout} seconds") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OPA output: {e}")
            raise RuntimeError(f"Failed to parse OPA output: {e}") from e
        except Exception as e:
            logger.error(f"Error evaluating policy: {e}")
            raise e
        finally:
            # Cleanup
            Path(policy_path).unlink(missing_ok=True)
            if "input_path" in locals():
                Path(input_path).unlink(missing_ok=True)

    def check_access(self, asset: SourceManifest, user_context: UserContext) -> bool:
        """
        Check if the user has access to the asset using strict Delegated Identity enforcement.

        Args:
            asset: The source manifest/asset to check access for.
            user_context: The user context containing identity and groups.

        Returns:
            True if access is allowed, False otherwise.
        """
        # Service accounts bypass ACL checks
        # Note: UserContext model currently stores this in claims
        if user_context.claims.get("is_service_account") is True:
            return True

        # Strict check: User must share at least one group with the asset's ACLs.
        return bool(set(asset.acls) & set(user_context.groups))
