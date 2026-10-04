"""WebSocket fan-out. Camera worker threads publish via publish_threadsafe()."""
import asyncio
import json


class Hub:
    def __init__(self):
        self.clients: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.clients.discard(q)

    def _push(self, text: str) -> None:
        for q in list(self.clients):
            if q.full():  # slow client: drop oldest
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(text)

    def publish_threadsafe(self, msg: dict) -> None:
        if self.loop and self.clients:
            self.loop.call_soon_threadsafe(self._push, json.dumps(msg, ensure_ascii=False))


hub = Hub()
