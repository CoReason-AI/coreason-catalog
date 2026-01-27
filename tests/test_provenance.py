import json
import uuid
from typing import List

import pytest

from coreason_catalog.models import SourceResult
from coreason_catalog.services.provenance import ProvenanceService


class TestProvenanceService:
    @pytest.fixture  # type: ignore[misc]
    def provenance_service(self) -> ProvenanceService:
        return ProvenanceService()

    def test_generate_provenance_structure(self, provenance_service: ProvenanceService) -> None:
        """Test that the generated provenance JSON has the correct top-level structure."""
        query_id = uuid.uuid4()
        results: List[SourceResult] = []

        prov_json = provenance_service.generate_provenance(query_id, results)
        data = json.loads(prov_json)

        assert "@context" in data
        assert "@graph" in data
        assert data["@context"]["prov"] == "http://www.w3.org/ns/prov#"

    def test_provenance_content_with_results(self, provenance_service: ProvenanceService) -> None:
        """Test that provenance includes the activity, entity, and used sources."""
        query_id = uuid.uuid4()
        source_urn = "urn:coreason:mcp:test_source"
        results = [SourceResult(source_urn=source_urn, status="SUCCESS", data={"foo": "bar"}, latency_ms=10.0)]

        prov_json = provenance_service.generate_provenance(query_id, results)
        data = json.loads(prov_json)
        graph = data["@graph"]

        # Find Activity and Entity
        activity = next((item for item in graph if item["@type"] == "prov:Activity"), None)
        entity = next((item for item in graph if item["@type"] == "prov:Entity"), None)

        assert activity is not None
        assert entity is not None

        # Check IDs
        assert activity["@id"] == f"urn:coreason:activity:{query_id}"
        assert entity["@id"] == f"urn:coreason:entity:response:{query_id}"

        # Check Relations
        assert entity["prov:wasGeneratedBy"] == activity["@id"]

        # Check Used Sources
        assert "prov:used" in activity
        assert source_urn in activity["prov:used"]

    def test_provenance_ignores_failed_sources(self, provenance_service: ProvenanceService) -> None:
        """Test that failed sources are not listed as 'used' in the activity."""
        query_id = uuid.uuid4()
        results = [
            SourceResult(source_urn="urn:failed", status="ERROR", data=None, latency_ms=0.0),
            SourceResult(source_urn="urn:success", status="SUCCESS", data={}, latency_ms=1.0),
        ]

        prov_json = provenance_service.generate_provenance(query_id, results)
        data = json.loads(prov_json)
        activity = next(item for item in data["@graph"] if item["@type"] == "prov:Activity")

        used = activity.get("prov:used", [])
        assert "urn:success" in used
        assert "urn:failed" not in used

    def test_timestamp_presence(self, provenance_service: ProvenanceService) -> None:
        """Test that a timestamp is included."""
        query_id = uuid.uuid4()
        prov_json = provenance_service.generate_provenance(query_id, [])
        data = json.loads(prov_json)
        activity = next(item for item in data["@graph"] if item["@type"] == "prov:Activity")

        assert "prov:endedAtTime" in activity
        assert "@value" in activity["prov:endedAtTime"]
