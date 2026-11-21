"""Check a request without making it, for the browser tests (tests/ui).

The browser tests fake every save, so they can never change the Tablo or the settings. That also
meant they couldn't see a save the server would refuse: 1.4.1's Customize on Home sent a section
the server didn't know, every save was refused, and the tests (and the page, which showed
"[object Object]") didn't notice. The tests' fake now asks here first: the request is matched to
its route and its path, query and body are validated the way FastAPI does it, and nothing runs.

Harmless in normal use: nothing is changed, and it's behind the same guards as every other /api
call (TabloView's own header, the PIN for other devices). Uses FastAPI's own validation helpers,
which are internal; if they can't be used, the answer is "can't tell" (unknown), never a refusal.
"""

import json
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from starlette.datastructures import QueryParams
from starlette.routing import Match

router = APIRouter(prefix="/api/dev", tags=["dev"])


class CheckRequest(BaseModel):
    method: str = Field(max_length=10)
    url: str = Field(max_length=4000)
    body: Optional[str] = Field(default=None, max_length=2_000_000)


def _routes(app) -> Iterator[Any]:
    """Every route, with its full path: FastAPI 0.16x keeps included routers nested
    (_IncludedRouter), and walks them with _iter_routes_with_context; older ones list them flat."""
    import fastapi.routing
    walk = getattr(fastapi.routing, "_iter_routes_with_context", None)
    if walk is None:
        yield from app.router.routes
        return
    for route, context in walk(app.router.routes):
        yield context or route


async def _errors(route: Any, path_params: Dict[str, Any], query: str, body: Optional[str]) -> List[Any]:
    from fastapi.dependencies import utils
    dep = route.dependant
    errors: List[Any] = []
    errors += utils.request_params_to_args(dep.path_params, path_params)[1]
    errors += utils.request_params_to_args(dep.query_params, QueryParams(query))[1]
    if dep.body_params:
        try:
            received = json.loads(body) if body else None
        except ValueError:
            return [{"type": "json_invalid", "loc": ["body"], "msg": "JSON decode error"}]
        embed = getattr(route, "_embed_body_fields", None)
        if embed is None:
            embed = utils._should_embed_body_fields(dep.body_params)
        errors += (await utils.request_body_to_args(dep.body_params, received, embed))[1]
    return errors


@router.post("/check")
async def check(req: CheckRequest, request: Request):
    """{ok, detail}: whether this request would be accepted, with FastAPI's 422 detail if not (or a
    404 status when no route takes it). {ok: true, unknown: true}: it couldn't be checked."""
    parts = urlsplit(req.url)
    method = req.method.upper()
    scope = {"type": "http", "path": parts.path, "method": method, "root_path": "",
             "query_string": parts.query.encode(), "headers": []}
    for route in _routes(request.app):
        if getattr(route, "dependant", None) is None:  # (static files, pages)
            continue
        match, child = route.matches(scope)
        if match != Match.FULL:
            continue
        try:
            errors = await _errors(route, child.get("path_params") or {}, parts.query, req.body)
        except Exception as e:  # FastAPI's internals changed: can't tell, so don't refuse
            return {"ok": True, "unknown": True, "why": f"{type(e).__name__}: {e}"}
        return {"ok": not errors, "detail": jsonable_encoder(errors)}
    # The page asking for something that isn't there: the server would answer 404
    return {"ok": False, "status": 404, "detail": f"No {method} {parts.path} on this server"}
