"""Compatibility helpers for inspecting routes across FastAPI versions."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def iter_registered_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Yield concrete routes, including routers deferred by newer FastAPI releases.

    Older FastAPI versions expand included routers into ``app.routes``. Newer
    versions may retain an ``_IncludedRouter`` wrapper and expose the original
    APIRouter through ``original_router`` instead. Tests should inspect both
    representations without depending on FastAPI's private wrapper type.
    """
    seen: set[int] = set()

    def walk(items: Iterable[Any]) -> Iterator[Any]:
        for item in items:
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)

            if hasattr(item, "path"):
                yield item

            original_router = getattr(item, "original_router", None)
            nested_routes = getattr(original_router, "routes", None)
            if nested_routes is not None:
                yield from walk(nested_routes)

    yield from walk(routes)
