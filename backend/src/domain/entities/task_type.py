"""
Task type domain entity.
Independent lookup describing the nature of a compliance task.
"""

from dataclasses import dataclass

from src.domain.entities.base_entity import BaseEntity


@dataclass(kw_only=True)
class TaskType(BaseEntity):
    """
    Classification of a compliance task, e.g. "Return Filing",
    "Register Maintenance", "Statutory Payment".

    Declared `kw_only` so mandatory fields can stay mandatory despite
    BaseEntity supplying defaults for the audit fields.

    Attributes:
        code: Unique business key, e.g. "RETURN_FILING".
        name: Display name. Unique.
        description: What this kind of task involves.
        is_active: Soft retirement flag.
    """

    code: str
    name: str
    description: str = ""
    is_active: bool = True

    def deactivate(self) -> None:
        """Retire the task type without deleting history."""
        self.is_active = False

    def activate(self) -> None:
        """Restore a retired task type."""
        self.is_active = True
