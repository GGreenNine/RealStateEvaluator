from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import POICategory, PointOfInterest


class BasePOIProvider(ABC):
    source_name: str

    @abstractmethod
    def fetch(self, category: POICategory) -> list[PointOfInterest]:
        raise NotImplementedError
