"""In-memory event hub (pub/sub) for live connectivity (roadmap Ch 2/10).

WebSocket clients subscribe to a topic (typically a project id); producers (the analyze flow, the passive
pipeline, alerts) publish events that are pushed to every subscriber. This is the in-process implementation;
a real deployment can back the same interface with Redis pub/sub for multi-instance fan-out.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict


class EventHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[topic].add(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        self._subs.get(topic, set()).discard(q)
        if topic in self._subs and not self._subs[topic]:
            self._subs.pop(topic, None)

    async def publish(self, topic: str, event: dict) -> int:
        """Push `event` to every subscriber of `topic`; return how many received it."""
        delivered = 0
        for q in list(self._subs.get(topic, ())):
            await q.put(event)
            delivered += 1
        return delivered

    def subscriber_count(self, topic: str) -> int:
        return len(self._subs.get(topic, ()))


# Module-level singleton shared by the API and producers.
hub = EventHub()
