from typing import List

import pytest
from coreason_identity.models import UserContext

from coreason_catalog.models import DataSensitivity, SourceManifest
from coreason_catalog.services.policy_engine import PolicyEngine


class TestIdentityEdgeCases:
    @pytest.fixture  # type: ignore[misc]
    def policy_engine(self) -> PolicyEngine:
        return PolicyEngine(opa_path="mock")

    def create_manifest(self, acls: List[str]) -> SourceManifest:
        return SourceManifest(
            urn="urn:test",
            name="Test",
            description="Test Desc",
            endpoint_url="http://test",
            geo_location="US",
            sensitivity=DataSensitivity.INTERNAL,
            owner_group="Owner",
            access_policy="allow { true }",
            acls=acls,
        )

    def test_access_empty_acls_blocks_regular_user(self, policy_engine: PolicyEngine) -> None:
        """
        Strict Fail-Closed: If an asset has NO ACLs (empty list), it implies no groups are allowed.
        Intersection of anything with empty set is empty.
        """
        asset = self.create_manifest(acls=[])
        user_context = UserContext(
            user_id="u1",
            email="u1@example.com",
            groups=["admin", "root", "system"],  # Even powerful looking groups fail if not listed
        )
        assert policy_engine.check_access(asset, user_context) is False

    def test_access_service_account_bypasses_empty_acls(self, policy_engine: PolicyEngine) -> None:
        """
        Service Accounts should bypass the ACL check, even if ACLs are empty (effectively locked).
        """
        asset = self.create_manifest(acls=[])
        user_context = UserContext(
            user_id="sa1",
            email="sa@bot.com",
            groups=[],
            claims={"is_service_account": True},
        )
        assert policy_engine.check_access(asset, user_context) is True

    def test_access_case_sensitivity(self, policy_engine: PolicyEngine) -> None:
        """
        Verify that group matching is case-sensitive.
        "group:admin" != "Group:Admin"
        """
        asset = self.create_manifest(acls=["group:admin"])

        # Mismatch case
        user_context_mismatch = UserContext(user_id="u1", email="u1@ex.com", groups=["Group:Admin"])
        assert policy_engine.check_access(asset, user_context_mismatch) is False

        # Match case
        user_context_match = UserContext(user_id="u1", email="u1@ex.com", groups=["group:admin"])
        assert policy_engine.check_access(asset, user_context_match) is True

    def test_access_large_lists(self, policy_engine: PolicyEngine) -> None:
        """
        Performance/Correctness check for large lists of groups/ACLs.
        """
        # 1000 ACLs
        acls = [f"group:{i}" for i in range(1000)]
        asset = self.create_manifest(acls=acls)

        # User has the last group
        user_context = UserContext(user_id="u1", email="u1@ex.com", groups=["group:999"])
        assert policy_engine.check_access(asset, user_context) is True

        # User has a group not in list
        user_context_fail = UserContext(user_id="u1", email="u1@ex.com", groups=["group:1001"])
        assert policy_engine.check_access(asset, user_context_fail) is False

    def test_access_none_groups_handled_safely(self, policy_engine: PolicyEngine) -> None:
        """
        Ensure UserContext with empty groups (default) is handled safely.
        """
        asset = self.create_manifest(acls=["group:A"])
        # groups defaults to [] in UserContext usually, but let's be explicit
        user_context = UserContext(user_id="u1", email="u1@ex.com", groups=[])
        assert policy_engine.check_access(asset, user_context) is False
