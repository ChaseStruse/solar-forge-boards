"""Domain enums and transition rules."""

from enum import StrEnum


class WorkItemStatus(StrEnum):
    """Lifecycle states for a work item."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[WorkItemStatus, frozenset[WorkItemStatus]] = {
    WorkItemStatus.TODO: frozenset(
        {
            WorkItemStatus.IN_PROGRESS,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.IN_PROGRESS: frozenset(
        {
            WorkItemStatus.TODO,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.DONE,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.BLOCKED: frozenset(
        {
            WorkItemStatus.TODO,
            WorkItemStatus.IN_PROGRESS,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.DONE: frozenset({WorkItemStatus.IN_PROGRESS}),
    WorkItemStatus.CANCELLED: frozenset({WorkItemStatus.TODO}),
}


def can_transition(current: WorkItemStatus, target: WorkItemStatus) -> bool:
    """Return whether a work item may move between two states."""
    return target in ALLOWED_TRANSITIONS[current]
