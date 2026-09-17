"""Runtime enumeration of the application's HTTP routes.

The authorization matrix (brief §6.4) has to fail when a new endpoint ships
without an entry, so the endpoint list it checks is read out of the running app
rather than written down by hand.

FastAPI 0.141 does not flatten included routers into `app.routes`; each
`include_router` call leaves an internal `_IncludedRouter` wrapper that holds
the original `APIRouter` and the prefix it was mounted under. Walking that
wrapper is the only way to see the real endpoints, so the traversal is
recursive and prefix-accumulating rather than a flat scan.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

# Starlette adds these to every route it builds; they are not separately
# authorized surfaces, so the matrix tracks the methods the app declares.
IMPLICIT_METHODS = frozenset({"HEAD", "OPTIONS"})


@dataclass(frozen=True, order=True)
class Endpoint:
    method: str
    path: str

    def __str__(self) -> str:
        return f"{self.method} {self.path}"


def iter_endpoints(app: FastAPI) -> list[Endpoint]:
    """Every method/path pair the app serves, deduplicated and sorted."""
    found: set[Endpoint] = set()

    def walk(routes: list[Any], prefix: str) -> None:
        for route in routes:
            included = getattr(route, "original_router", None)
            if included is not None:
                walk(included.routes, prefix + (route.include_context.prefix or ""))
            elif isinstance(route, APIRoute):
                for method in route.methods - IMPLICIT_METHODS:
                    found.add(Endpoint(method, prefix + route.path))

    walk(list(app.routes), "")
    return sorted(found)
