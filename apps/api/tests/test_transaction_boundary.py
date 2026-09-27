"""A durable commit must precede the first HTTP success byte, including commit failures."""

import ast
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI

from fleetpilot import db as database


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_commit", [False, True])
async def test_commit_before_response(monkeypatch, fail_commit):
    events = []

    class Session:
        info = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def commit(self):
            events.append("commit")
            if fail_commit:
                raise RuntimeError("Synthetic commit failure")

        async def rollback(self):
            events.append("rollback")

    monkeypatch.setattr(database, "Session", Session)
    app = FastAPI()

    @app.post("/")
    async def command(db=Depends(database.get_db, scope="function")):
        events.append("command")
        return {"saved": True}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            events.append(message["status"])

    scope = dict(type="http", method="POST", path="/", raw_path=b"/", query_string=b"",
                 headers=[], scheme="http", server=("test", 80), client=("test", 1),
                 http_version="1.1", root_path="")
    if fail_commit:
        with pytest.raises(RuntimeError, match="Synthetic commit failure"):
            await app(scope, receive, send)
        assert events == ["command", "commit", "rollback", 500]
    else:
        await app(scope, receive, send)
        assert events == ["command", "commit", 200]


def test_database_dependencies_use_commit_before_response_scope():
    count = 0
    for path in Path(database.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Depends" and node.args
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "get_db"):
                assert any(k.arg == "scope" and isinstance(k.value, ast.Constant)
                           and k.value.value == "function" for k in node.keywords), path.name
                count += 1
    assert count > 0
