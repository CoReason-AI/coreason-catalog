import json
import uuid

import pytest

from coreason_catalog.models import SourceResult
from coreason_catalog.services.provenance import ProvenanceService


class TestProvenanceServiceComplex:
    @pytest.fixture  # type: ignore[misc]
    def provenance_service(self) -> ProvenanceService:
        return ProvenanceService()

    def test_mixed_status_filtering(self, provenance_service: ProvenanceService) -> None:
        """
        Verify that only sources with SUCCESS status are included in the provenance.
        BLOCKED_BY_POLICY and ERROR should be excluded.
        """
        query_id = uuid.uuid4()
        results = [
            SourceResult(source_urn="urn:success:1", status="SUCCESS", data={}, latency_ms=1.0),
            SourceResult(source_urn="urn:error:1", status="ERROR", data=None, latency_ms=0.5),
            SourceResult(source_urn="urn:blocked:1", status="BLOCKED_BY_POLICY", data=None, latency_ms=0.1),
            SourceResult(source_urn="urn:success:2", status="SUCCESS", data={}, latency_ms=1.2),
        ]

        prov_json = provenance_service.generate_provenance(query_id, results)
        data = json.loads(prov_json)

        activity = next(item for item in data["@graph"] if item["@type"] == "prov:Activity")
        used = activity.get("prov:used", [])

        assert "urn:success:1" in used
        assert "urn:success:2" in used
        assert "urn:error:1" not in used
        assert "urn:blocked:1" not in used
        assert len(used) == 2

    def test_deterministic_output(self, provenance_service: ProvenanceService) -> None:
        """
        Verify that the output is deterministic regardless of the input order of results.
        """
        query_id = uuid.uuid4()
        result1 = SourceResult(source_urn="urn:a", status="SUCCESS", data={}, latency_ms=1.0)
        result2 = SourceResult(source_urn="urn:b", status="SUCCESS", data={}, latency_ms=1.0)

        # Order 1
        json1 = provenance_service.generate_provenance(query_id, [result1, result2])

        # Order 2
        json2 = provenance_service.generate_provenance(query_id, [result2, result1])

        # We need to ignore timestamp difference for comparison
        data1 = json.loads(json1)
        data2 = json.loads(json2)

        # Patch timestamps to be identical
        activity1 = next(item for item in data1["@graph"] if item["@type"] == "prov:Activity")
        activity2 = next(item for item in data2["@graph"] if item["@type"] == "prov:Activity")

        activity1["prov:endedAtTime"]["@value"] = "FIXED_TIME"
        activity2["prov:endedAtTime"]["@value"] = "FIXED_TIME"

        assert json.dumps(data1, sort_keys=True) == json.dumps(data2, sort_keys=True)

        # Check that prov:used is sorted
        assert activity1["prov:used"] == ["urn:a", "urn:b"]

    def test_large_scale_generation(self, provenance_service: ProvenanceService) -> None:
        """
        Verify that the service can handle a large number of results.
        """
        query_id = uuid.uuid4()
        results = [
            SourceResult(source_urn=f"urn:source:{i}", status="SUCCESS", data={}, latency_ms=1.0) for i in range(1000)
        ]

        prov_json = provenance_service.generate_provenance(query_id, results)
        data = json.loads(prov_json)

        activity = next(item for item in data["@graph"] if item["@type"] == "prov:Activity")
        used = activity.get("prov:used", [])

        assert len(used) == 1000
        assert used[0] == "urn:source:0"
        assert used[-1] == "urn:source:999"

    def test_provenance_graph_structure(self, provenance_service: ProvenanceService) -> None:
        """
        Verify the structural integrity of the generated JSON-LD graph.
        """
        query_id = uuid.uuid4()
        results = [SourceResult(source_urn="urn:source:1", status="SUCCESS", data={}, latency_ms=1.0)]

        prov_json = provenance_service.generate_provenance(query_id, results)
        data = json.loads(prov_json)

        assert "@context" in data
        assert "@graph" in data
        assert isinstance(data["@graph"], list)

        graph_map = {item["@id"]: item for item in data["@graph"]}

        activity_id = f"urn:coreason:activity:{query_id}"
        entity_id = f"urn:coreason:entity:response:{query_id}"

        assert activity_id in graph_map
        assert entity_id in graph_map

        activity = graph_map[activity_id]
        entity = graph_map[entity_id]

        assert activity["@type"] == "prov:Activity"
        assert entity["@type"] == "prov:Entity"

        assert entity["prov:wasGeneratedBy"] == activity_id
        assert activity["prov:used"] == ["urn:source:1"]
