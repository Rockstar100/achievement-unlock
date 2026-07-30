"""Dagster Definitions — loaded by `dagster dev` via pyproject module_name."""
from dagster import Definitions, load_asset_checks_from_modules, load_assets_from_modules

from . import assets, jobs, schedules
from .asset_checks import bronze_checks, gold_checks
from .resources.file_store import FileStoreResource
from .resources.slack import SlackResource

file_store = FileStoreResource.from_env()
slack_daily = SlackResource.daily_pulse_from_env()
slack_weekly = SlackResource.weekly_digest_from_env()

all_assets = load_assets_from_modules([assets])
all_checks = load_asset_checks_from_modules([bronze_checks, gold_checks])

_sensors = []
try:
    from .sensors import alerting

    _sensors = [
        alerting.pipeline_failure_sensor,
        alerting.data_freshness_sensor,
    ]
except ImportError:
    pass

defs = Definitions(
    assets=all_assets,
    asset_checks=all_checks,
    jobs=[
        jobs.daily_ingestion_job,
        jobs.transformation_job,
        jobs.full_pipeline_job,
        jobs.daily_pulse_job,
        jobs.weekly_digest_job,
    ],
    schedules=[
        schedules.daily_ingestion_schedule,
        schedules.transformation_schedule,
        schedules.daily_pulse_schedule,
        schedules.weekly_digest_schedule,
        schedules.full_pipeline_schedule,
    ],
    sensors=_sensors,
    resources={
        "file_store": file_store,
        "slack_daily": slack_daily,
        "slack_weekly": slack_weekly,
    },
)
