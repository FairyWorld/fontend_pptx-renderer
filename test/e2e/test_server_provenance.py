from __future__ import annotations

import asyncio
import hashlib
import importlib.util
from pathlib import Path

import pytest

import server


RUN_ALL_PATH = Path(__file__).resolve().parent / "scripts" / "run_all_shapes_eval.py"


def test_render_artifacts_bind_reference_and_candidate_screenshots(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROJECT_ROOT", tmp_path)
    reference = tmp_path / "test/e2e/reports/case_pdf.png"
    candidate = tmp_path / "test/e2e/reports/case_html.png"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"native")
    candidate.write_bytes(b"renderer")

    artifacts = server._render_artifacts(reference, candidate)

    assert artifacts == {
        "reference": {
            "path": "test/e2e/reports/case_pdf.png",
            "sizeBytes": 6,
            "sha256": hashlib.sha256(b"native").hexdigest(),
        },
        "candidate": {
            "path": "test/e2e/reports/case_html.png",
            "sizeBytes": 8,
            "sha256": hashlib.sha256(b"renderer").hexdigest(),
        },
    }


def _load_run_all_module():
    spec = importlib.util.spec_from_file_location("run_all_shapes_eval", RUN_ALL_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_slide_url_includes_explicit_font_profile(monkeypatch):
    monkeypatch.setenv("PPTX_E2E_FONT_PROFILE", "font-profiles/office-zh.json")

    url = server._render_slide_url("sample", 2, None)

    assert "file=testdata/cases/sample/source.pptx" in url
    assert "slide=2" in url
    assert "fontProfile=font-profiles%2Foffice-zh.json" in url


def test_render_slide_url_omits_font_profile_by_default(monkeypatch):
    monkeypatch.delenv("PPTX_E2E_FONT_PROFILE", raising=False)

    assert "fontProfile=" not in server._render_slide_url("sample", 0, None)


@pytest.mark.parametrize(
    "profile_ref",
    ["../escape.json", "/absolute.json", "https://example.com/profile.json", r"..\escape.json"],
)
def test_render_slide_url_rejects_non_local_font_profile(monkeypatch, profile_ref: str):
    monkeypatch.setenv("PPTX_E2E_FONT_PROFILE", profile_ref)

    with pytest.raises(ValueError, match="testdata-relative"):
        server._render_slide_url("sample", 0, None)


def test_batch_result_preserves_case_provenance():
    run_all = _load_run_all_module()
    provenance = {
        "schemaVersion": 1,
        "inputs": {"sourcePptx": {"sha256": "abc"}},
        "runtime": {"browser": {"name": "chromium", "version": "140"}},
    }

    result = run_all._result_from_evaluate_response(
        "sample",
        {
            "avgSsim": 0.9,
            "avgColorHistCorr": 0.99,
            "slideCount": 1,
            "visibleSlideCount": 1,
            "supported": False,
            "quality": {"needsReview": True},
            "provenance": provenance,
        },
    )

    assert result["provenance"] == provenance


def test_server_counts_per_slide_runtime_errors_separately_from_visual_metrics():
    per_slide = [
        {"slideIdx": 0, "ssim": 0.99},
        {"slideIdx": 1, "ssim": None, "error": "Target page closed"},
    ]

    assert server._evaluation_errors(per_slide) == [
        {"slideIdx": 1, "error": "Target page closed"},
    ]


def test_empty_runtime_error_message_remains_an_evaluation_error():
    run_all = _load_run_all_module()
    per_slide = [{"slideIdx": 0, "error": ""}]
    expected = [{"slideIdx": 0, "error": "Unknown slide evaluation error"}]

    assert server._evaluation_errors(per_slide) == expected
    assert run_all._evaluation_errors_from_response({"perSlide": per_slide}) == expected


def test_batch_retry_recovers_a_transient_per_slide_runtime_error():
    run_all = _load_run_all_module()

    class Response:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, _url):
            self.calls += 1
            if self.calls == 1:
                return Response(
                    {
                        "perSlide": [
                            {"slideIdx": 0, "ssim": None, "error": "Target page closed"}
                        ]
                    }
                )
            return Response(
                {
                    "avgSsim": 0.99,
                    "avgColorHistCorr": 1.0,
                    "slideCount": 1,
                    "visibleSlideCount": 1,
                    "supported": True,
                    "quality": {"needsReview": False},
                    "perSlide": [{"slideIdx": 0, "ssim": 0.99}],
                }
            )

    client = Client()
    result, error = asyncio.run(
        run_all._eval_one(
            client,
            asyncio.Semaphore(1),
            "http://127.0.0.1:8081",
            "sample",
            retries=1,
        )
    )

    assert error is None
    assert result is not None
    assert result["summary"]["ssim"] == 0.99
    assert client.calls == 2


def test_browser_init_replaces_a_disconnected_browser(monkeypatch):
    events = []
    close_started = None
    release_close = None

    class Browser:
        def __init__(self, connected):
            self.connected = connected

        def is_connected(self):
            return self.connected

        async def close(self):
            events.append("close-browser")
            if not self.connected:
                close_started.set()
                await release_close.wait()

    class Playwright:
        def __init__(self, browser):
            self.chromium = self
            self.browser = browser

        async def launch(self, **_options):
            events.append("launch-browser")
            return self.browser

        async def stop(self):
            events.append("stop-playwright")

    class Starter:
        async def start(self):
            events.append("start-playwright")
            return fresh_playwright

    stale_browser = Browser(False)
    stale_playwright = Playwright(stale_browser)
    fresh_browser = Browser(True)
    fresh_playwright = Playwright(fresh_browser)
    monkeypatch.setattr(server, "_browser", stale_browser)
    monkeypatch.setattr(server, "_playwright", stale_playwright)
    monkeypatch.setattr(server, "async_playwright", lambda: Starter())
    monkeypatch.setattr(server, "_browser_init_lock", asyncio.Lock())

    async def get_concurrently():
        nonlocal close_started, release_close
        close_started = asyncio.Event()
        release_close = asyncio.Event()
        first = asyncio.create_task(server.get_browser())
        await close_started.wait()
        second = asyncio.create_task(server.get_browser())
        await asyncio.sleep(0)
        release_close.set()
        results = await asyncio.gather(first, second)
        initialization_events = list(events)
        await server.close_browser()
        return results, initialization_events

    results, initialization_events = asyncio.run(get_concurrently())

    assert results == [fresh_browser, fresh_browser]
    assert initialization_events == [
        "close-browser",
        "stop-playwright",
        "start-playwright",
        "launch-browser",
    ]


def test_browser_init_stops_playwright_when_launch_is_cancelled(monkeypatch):
    events = []

    class Playwright:
        chromium = None

        def __init__(self):
            self.chromium = self

        async def launch(self, **_options):
            events.append("launch-browser")
            raise asyncio.CancelledError()

        async def stop(self):
            events.append("stop-playwright")

    playwright = Playwright()

    class Starter:
        async def start(self):
            events.append("start-playwright")
            return playwright

    monkeypatch.setattr(server, "_browser", None)
    monkeypatch.setattr(server, "_playwright", None)
    monkeypatch.setattr(server, "async_playwright", lambda: Starter())
    monkeypatch.setattr(server, "_browser_init_lock", asyncio.Lock())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(server.get_browser())

    assert events == ["start-playwright", "launch-browser", "stop-playwright"]
    assert server._browser is None
    assert server._playwright is None
