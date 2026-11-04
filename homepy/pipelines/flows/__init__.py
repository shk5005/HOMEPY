"""Prefect orchestration flows (daily, weekly, monthly, event-driven)."""
from homepy.pipelines.flows._common import FlowResult
from homepy.pipelines.flows.daily_flow import daily_pipeline
from homepy.pipelines.flows.event_flow import event_pipeline
from homepy.pipelines.flows.monthly_flow import monthly_pipeline
from homepy.pipelines.flows.weekly_flow import weekly_pipeline

__all__ = ["FlowResult", "daily_pipeline", "weekly_pipeline", "monthly_pipeline", "event_pipeline"]
