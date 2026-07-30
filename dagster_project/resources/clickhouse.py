"""
ClickHouse resource for Dagster.
"""
import os
from typing import Any, Dict, List, Optional

from clickhouse_driver import Client
from dagster import ConfigurableResource


class ClickHouseResource(ConfigurableResource):
    host: str = "localhost"
    port: int = 9000
    user: str = "default"
    password: str = ""
    database: str = "default"
    secure: bool = False

    @classmethod
    def from_env(cls) -> "ClickHouseResource":
        return cls(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
            user=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            database=os.getenv("CLICKHOUSE_DATABASE", "default"),
        )

    def get_client(self) -> Client:
        return Client(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            secure=self.secure,
        )

    def execute(self, query: str, parameters: Optional[Dict] = None) -> List[tuple]:
        client = self.get_client()
        return client.execute(query, parameters or {})

    def insert(self, table: str, data: List[Dict[str, Any]]) -> None:
        if not data:
            return
        client = self.get_client()
        columns = list(data[0].keys())
        values = [[row[col] for col in columns] for row in data]
        client.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES",
            values,
        )

    def query_dicts(self, query: str, parameters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        client = self.get_client()
        result = client.execute(query, parameters or {}, with_column_types=True)
        if not result:
            return []
        rows, col_types = result
        cols = [c[0] for c in col_types]
        return [dict(zip(cols, row)) for row in rows]
