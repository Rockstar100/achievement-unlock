"""Verify Dagster definitions load correctly."""
from dagster import DagsterInstance
from dagster._core.definitions.definitions_class import Definitions


def test_definitions_load():
    from dagster_project.definitions import defs

    assert isinstance(defs, Definitions)
    assert len(defs.get_repository_def().job_names) >= 4


def test_asset_keys():
    from dagster import AssetKey
    from dagster_project.definitions import defs

    repo = defs.get_repository_def()
    asset_keys = set(repo.asset_graph.get_all_asset_keys())
    assert AssetKey(["bronze", "ecom_trends", "amazon_bestsellers"]) in asset_keys
    assert AssetKey(["gold_trending_products"]) in asset_keys


def test_file_store_resource_registered():
    from dagster_project.definitions import defs

    assert "file_store" in defs.resources
