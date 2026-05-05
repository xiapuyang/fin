from abc import ABC, abstractmethod

from fin.models.alert import AlertFireModel, AlertModel
from fin.schemas.alert import AlertCreate, AlertUpdate


class AlertRepository(ABC):
    @abstractmethod
    def get_all(self) -> list[AlertModel]: ...

    @abstractmethod
    def get_enabled(self) -> list[AlertModel]: ...

    @abstractmethod
    def get_by_id(self, id: int) -> AlertModel | None: ...

    @abstractmethod
    def create(self, data: AlertCreate) -> AlertModel: ...

    @abstractmethod
    def update(self, id: int, data: AlertUpdate) -> AlertModel: ...

    @abstractmethod
    def delete(self, id: int) -> None: ...

    @abstractmethod
    def disable(self, id: int) -> AlertModel: ...

    @abstractmethod
    def reset(self, id: int) -> AlertModel: ...


class AlertFireRepository(ABC):
    @abstractmethod
    def create(
        self, alert_id: int, price: float, change_pct: float
    ) -> AlertFireModel: ...

    @abstractmethod
    def get_by_alert(self, alert_id: int) -> list[AlertFireModel]: ...

    @abstractmethod
    def get_recent(self, limit: int = 50) -> list[AlertFireModel]: ...
