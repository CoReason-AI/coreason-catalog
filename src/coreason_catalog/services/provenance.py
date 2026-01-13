import json
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from coreason_catalog.models import SourceResult


class ProvenanceService:
    """
    Service for generating W3C PROV-O JSON-LD provenance metadata.
    Ensures Chain of Custody tracking for all catalog responses.
    """

    def generate_provenance(self, query_id: UUID, results: List[SourceResult]) -> str:
        """
        Generate a W3C PROV-O JSON-LD compliant provenance signature.

        Args:
            query_id: The unique ID of the query execution.
            results: The list of results from the dispatched sources.

        Returns:
            A JSON string representing the provenance graph.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Define the Context
        context = {
            "prov": "http://www.w3.org/ns/prov#",
            "coreason": "https://coreason.ai/provenance#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        }

        # The Activity (The Query Execution)
        activity_id = f"urn:coreason:activity:{query_id}"
        activity = {
            "@id": activity_id,
            "@type": "prov:Activity",
            "prov:endedAtTime": {
                "@value": timestamp,
                "@type": "xsd:dateTime",
            },
        }

        # The Entity (The Aggregated Response)
        response_id = f"urn:coreason:entity:response:{query_id}"
        response_entity = {
            "@id": response_id,
            "@type": "prov:Entity",
            "prov:wasGeneratedBy": activity_id,
            "coreason:queryId": str(query_id),
        }

        # Identify used sources (Entities)
        used_sources = []
        for result in results:
            if result.status == "SUCCESS":
                used_sources.append(result.source_urn)

        if used_sources:
            activity["prov:used"] = used_sources

        # Construct the Graph
        graph = [activity, response_entity]

        # Assemble the JSON-LD document
        provenance_doc = {"@context": context, "@graph": graph}

        return json.dumps(provenance_doc, sort_keys=True)
