"""Passive pipeline: event → background jobs (roadmap Ch 10).

Events fan out to jobs. CP-6 uses an in-memory queue; a real broker (RabbitMQ/Celery/NATS) plugs in behind
the same `JobQueue` interface at deployment time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# Which background jobs each event triggers (Ch 10 fan-out).
EVENT_JOBS: dict[str, list[str]] = {
    "DecisionAccepted": [
        "generate_summary",
        "create_embeddings",
        "update_decision_graph",
        "discover_relationships",
    ],
    "DocumentUploaded": ["chunk_document", "create_embeddings"],
}


@dataclass
class Job:
    name: str
    payload: dict = field(default_factory=dict)


class JobQueue(Protocol):
    def enqueue(self, job: Job) -> None: ...


@dataclass
class InMemoryJobQueue:
    jobs: list[Job] = field(default_factory=list)

    def enqueue(self, job: Job) -> None:
        self.jobs.append(job)


def emit(event: str, payload: dict, queue: JobQueue) -> list[str]:
    """Enqueue every job the event fans out to; return the job names enqueued."""
    names = EVENT_JOBS.get(event, [])
    for name in names:
        queue.enqueue(Job(name=name, payload=payload))
    return names
