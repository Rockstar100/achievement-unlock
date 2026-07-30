"""Dagster schedules for file-based pipeline."""
from dagster import DefaultScheduleStatus, ScheduleDefinition

from .jobs import (
    daily_ingestion_job,
    daily_pulse_job,
    full_pipeline_job,
    transformation_job,
    weekly_digest_job,
)

daily_ingestion_schedule = ScheduleDefinition(
    job=daily_ingestion_job,
    cron_schedule="0 7 * * *",
    execution_timezone="Asia/Kolkata",
    description="Daily bronze ingestion to CSV/JSON at 7:00 AM IST",
)

transformation_schedule = ScheduleDefinition(
    job=transformation_job,
    cron_schedule="0 8 * * *",
    execution_timezone="Asia/Kolkata",
    description="Build gold layer from bronze CSV at 8:00 AM IST",
)

daily_pulse_schedule = ScheduleDefinition(
    job=daily_pulse_job,
    cron_schedule="30 7 * * *",
    execution_timezone="Asia/Kolkata",
    description="Send daily Slack pulse at 7:30 AM IST",
)

weekly_digest_schedule = ScheduleDefinition(
    job=weekly_digest_job,
    cron_schedule="0 9 * * 1",
    execution_timezone="Asia/Kolkata",
    description="Send weekly digest every Monday at 9:00 AM IST",
)

# Optional: run everything in one shot
full_pipeline_schedule = ScheduleDefinition(
    job=full_pipeline_job,
    cron_schedule="0 6 * * *",
    execution_timezone="Asia/Kolkata",
    description="Full pipeline (bronze + gold) at 6:00 AM IST",
    default_status=DefaultScheduleStatus.STOPPED,
)
