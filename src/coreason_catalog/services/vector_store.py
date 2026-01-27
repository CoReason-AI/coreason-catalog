from pathlib import Path
from typing import List, Optional

import lancedb
import pyarrow as pa

from coreason_catalog.models import DataSensitivity, SourceManifest


class VectorStore:
    """
    Wrapper around LanceDB for storing and searching source manifests.
    """

    def __init__(self, uri: str = "data/lancedb"):
        """
        Initialize the LanceDB connection.

        Args:
            uri: Path to the LanceDB directory.
        """
        # Ensure directory exists if it's a local path
        if not uri.startswith("s3://") and not uri.startswith("gs://"):
            Path(uri).mkdir(parents=True, exist_ok=True)

        self.db = lancedb.connect(uri)
        self.table_name = "sources"
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the table schema if it doesn't exist."""
        schema = pa.schema(
            [
                pa.field("urn", pa.string()),
                pa.field("name", pa.string()),
                pa.field("description", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), 384)),  # Assuming 384 dim from EmbeddingService
                pa.field("endpoint_url", pa.string()),
                pa.field("geo_location", pa.string()),
                pa.field("sensitivity", pa.string()),
                pa.field("owner_group", pa.string()),
                pa.field("access_policy", pa.string()),
            ]
        )

        if self.table_name not in self.db.list_tables(limit=1000).tables:
            self.db.create_table(self.table_name, schema=schema)

    def add_source(self, manifest: SourceManifest, embedding: List[float]) -> None:
        """
        Add or update a source manifest in the vector store.

        Args:
            manifest: The source manifest to store.
            embedding: The vector embedding of the description.

        Raises:
            ValueError: If embedding dimension is incorrect.
        """
        if len(embedding) != 384:
            raise ValueError(f"Embedding dimension mismatch. Expected 384, got {len(embedding)}")

        try:
            table = self.db.open_table(self.table_name)

            data = [
                {
                    "urn": manifest.urn,
                    "name": manifest.name,
                    "description": manifest.description,
                    "vector": embedding,
                    "endpoint_url": manifest.endpoint_url,
                    "geo_location": manifest.geo_location,
                    "sensitivity": manifest.sensitivity.value,
                    "owner_group": manifest.owner_group,
                    "access_policy": manifest.access_policy,
                }
            ]

            # Check if exists, delete if so (simple upsert strategy)
            # LanceDB merge/upsert is more complex, delete-insert is safer for MVP
            table.delete(f"urn = '{manifest.urn}'")
            table.add(data)
        except Exception as e:
            # Handle potential concurrent write issues or other DB errors
            raise RuntimeError(f"Failed to add source: {e}") from e

    def search(
        self, query_vector: List[float], limit: int = 10, filter_sql: Optional[str] = None
    ) -> List[SourceManifest]:
        """
        Search for sources using vector similarity and SQL filtering.

        Args:
            query_vector: The query embedding.
            limit: Max results.
            filter_sql: Optional SQL where clause (e.g. "geo_location = 'US'").

        Returns:
            List of matching SourceManifest objects.

        Raises:
            ValueError: If query vector dimension is incorrect or filter SQL is invalid.
        """
        if len(query_vector) != 384:
            raise ValueError(f"Query vector dimension mismatch. Expected 384, got {len(query_vector)}")

        try:
            table = self.db.open_table(self.table_name)

            query = table.search(query_vector).limit(limit)

            if filter_sql:
                query = query.where(filter_sql)

            results = query.to_pandas()
        except Exception as e:
            # Catch errors related to invalid SQL or other query issues
            if filter_sql and ("syntax" in str(e).lower() or "parser" in str(e).lower()):
                raise ValueError(f"Invalid SQL filter: {e}") from e
            raise RuntimeError(f"Search failed: {e}") from e

        manifests = []
        for _, row in results.iterrows():
            manifests.append(
                SourceManifest(
                    urn=row["urn"],
                    name=row["name"],
                    description=row["description"],
                    endpoint_url=row["endpoint_url"],
                    geo_location=row["geo_location"],
                    sensitivity=DataSensitivity(row["sensitivity"]),
                    owner_group=row["owner_group"],
                    access_policy=row["access_policy"],
                )
            )

        return manifests
