"""In-process pub/sub for live monitor events.

Single-instance only — every FastAPI worker has its own subscriber set. Fine for
free-tier Render (one instance). If we ever scale horizontally, swap this for
Redis pub/sub or Postgres LISTEN/NOTIFY without touching callers.
"""
import asyncio
from typing import Any


_subscribers: set[asyncio.Queue] = set()


def add_subscriber(maxsize: int = 100) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    _subscribers.add(q)
    return q


def remove_subscriber(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def broadcast(event: Any) -> None:
    """Non-blocking. Drops events for subscribers whose queue is full (slow client)."""
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def subscriber_count() -> int:
    return len(_subscribers)
