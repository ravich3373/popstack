"""ASGI-level tests for the bearer-auth middleware — the only thing standing
between Tailscale Funnel and your vault (review finding #6)."""

import asyncio

from popstack.server import _BearerAuth


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _run(middleware, scope):
    sent: list[dict] = []

    async def send(msg):
        sent.append(msg)

    async def receive():
        return {"type": "http.request"}

    asyncio.run(middleware(scope, receive, send))
    return sent[0]["status"]


def _scope(method="POST", auth=None):
    headers = [(b"authorization", auth)] if auth is not None else []
    return {"type": "http", "method": method, "headers": headers}


def test_missing_token_is_401():
    mw = _BearerAuth(_ok_app, "secret")
    assert _run(mw, _scope(auth=None)) == 401


def test_wrong_token_is_401():
    mw = _BearerAuth(_ok_app, "secret")
    assert _run(mw, _scope(auth=b"Bearer nope")) == 401


def test_correct_token_passes():
    mw = _BearerAuth(_ok_app, "secret")
    assert _run(mw, _scope(auth=b"Bearer secret")) == 200


def test_options_preflight_bypasses_auth():
    mw = _BearerAuth(_ok_app, "secret")
    assert _run(mw, _scope(method="OPTIONS", auth=None)) == 204
