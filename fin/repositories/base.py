from abc import ABC, abstractmethod

from fin.models.alert import AlertFireModel, AlertModel
from fin.schemas.alert import AlertCreate, AlertUpdate


class AlertRepository(ABC):
    @abstractmethod
    def get_all(self) -> list[AlertModel]: ...

    @abstractmethod
    def get_enabled(self) -> list[AlertModel]: ...

    @abstractmethod
    def get_by_id(self, id: str) -> AlertModel | None: ...

    @abstractmethod
    def create(self, data: AlertCreate) -> AlertModel: ...

    @abstractmethod
    def update(self, id: str, data: AlertUpdate) -> AlertModel: ...

    @abstractmethod
    def delete(self, id: str) -> None: ...

    @abstractmethod
    def disable(self, id: str) -> AlertModel: ...

    @abstractmethod
    def reset(self, id: str) -> AlertModel: ...


class AlertFireRepository(ABC):
    @abstractmethod
    def create(self, alert_id: str, price: float, change_pct: float) -> AlertFireModel: ...

    @abstractmethod
    def get_by_alert(self, alert_id: str) -> list[AlertFireModel]: ...

    @abstractmethod
    def get_recent(self, limit: int = 50) -> list[AlertFireModel]: ...
