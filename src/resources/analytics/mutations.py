from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.analytics_service import AnalyticsService
from src.models.analytics import AnalyticsEventCreate, AnalyticsMetricCreate
from src.models.common import MutationResponseDTO
from datetime import datetime


class TrackEventMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        event_data = AnalyticsEventCreate(**params)
        event = await service.track_event(event_data)
        return MutationResponseDTO(data=event.model_dump(by_alias=True)).model_dump()


class TrackMetricMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        metric_data = AnalyticsMetricCreate(**params)
        metric = await service.track_metric(metric_data)
        return MutationResponseDTO(data=metric.model_dump(by_alias=True)).model_dump()
