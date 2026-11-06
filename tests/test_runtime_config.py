import asyncio
import json
import os
import unittest
from unittest import mock

import uvicorn
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

import backend.main as app
from backend.runtime_config import (
    ServerConfigError,
    capture_enabled,
    divert_recording_allowed,
    local_origins,
    public_bind_warning,
    resolve_bind,
    resolve_cors_origins,
    sync_token,
)


class BindConfigTests(unittest.TestCase):
    def test_default_is_loopback_8000(self):
        self.assertEqual(resolve_bind({}), ("127.0.0.1", 8000))

    def test_roco_names_override_generic_names(self):
        environ = {
            "ROCO_HOST": "0.0.0.0",
            "HOST": "10.0.0.8",
            "ROCO_PORT": "9000",
            "PORT": "7000",
        }
        self.assertEqual(resolve_bind(environ), ("0.0.0.0", 9000))

    def test_generic_names_are_used_when_roco_names_are_blank(self):
        environ = {"ROCO_HOST": "  ", "HOST": "10.1.2.3", "ROCO_PORT": "", "PORT": "8123"}
        self.assertEqual(resolve_bind(environ), ("10.1.2.3", 8123))

    def test_bracketed_ipv6_loopback_is_normalized(self):
        self.assertEqual(resolve_bind({"ROCO_HOST": "[::1]", "ROCO_PORT": "8000"}), ("::1", 8000))
        self.assertIsNone(public_bind_warning("::1"))
        self.assertIsNone(public_bind_warning("[::1]"))

    def test_public_bind_warns_without_changing_the_host(self):
        self.assertEqual(resolve_bind({"ROCO_HOST": "0.0.0.0"}), ("0.0.0.0", 8000))
        self.assertIn("GET /api/token", public_bind_warning("0.0.0.0"))

    def test_invalid_port_and_host_are_rejected(self):
        with self.assertRaises(ServerConfigError):
            resolve_bind({"PORT": "0"})
        with self.assertRaises(ServerConfigError):
            resolve_bind({"PORT": "8000abc"})
        with self.assertRaises(ServerConfigError):
            resolve_bind({"HOST": "http://0.0.0.0"})

    def test_process_environment_is_the_default_source(self):
        with mock.patch.dict(os.environ, {"ROCO_HOST": "10.9.8.7", "ROCO_PORT": "8123"}, clear=False):
            self.assertEqual(resolve_bind(), ("10.9.8.7", 8123))


class CorsConfigTests(unittest.TestCase):
    def test_local_origins_follow_the_port(self):
        origins, warnings = resolve_cors_origins("127.0.0.1", 8123, {})
        self.assertEqual(warnings, [])
        self.assertEqual(origins, list(local_origins(8123)))

    def test_public_origin_is_added_and_wildcard_is_ignored(self):
        origins, warnings = resolve_cors_origins(
            "0.0.0.0",
            8000,
            {"ROCO_CORS_ORIGINS": " https://warehouse.example.com/, *, https://warehouse.example.com/app "},
        )
        self.assertEqual(origins[0:3], list(local_origins(8000)))
        self.assertIn("https://warehouse.example.com", origins)
        self.assertNotIn("*", origins)
        self.assertNotIn("https://warehouse.example.com/app", origins)
        self.assertTrue(any("*" in item for item in warnings))
        self.assertTrue(any("/app" in item for item in warnings))

    def test_specific_bind_host_is_allowed_without_opening_every_origin(self):
        origins, warnings = resolve_cors_origins("192.168.1.10", 8000, {})
        self.assertEqual(warnings, [])
        self.assertIn("http://192.168.1.10:8000", origins)
        self.assertNotIn("http://0.0.0.0:8000", origins)

    def test_wildcard_bind_does_not_invent_an_origin(self):
        origins, _warnings = resolve_cors_origins("0.0.0.0", 8000, {})
        self.assertNotIn("http://0.0.0.0:8000", origins)


class CaptureFlagTests(unittest.TestCase):
    def test_capture_defaults_off_away_from_windows(self):
        self.assertFalse(capture_enabled({}, platform_name="linux"))
        self.assertTrue(capture_enabled({}, platform_name="win32"))
        self.assertFalse(capture_enabled({"ROCO_ENABLE_CAPTURE": "0"}, platform_name="win32"))
        self.assertTrue(capture_enabled({"ROCO_ENABLE_CAPTURE": "yes"}, platform_name="linux"))
        self.assertFalse(capture_enabled({"ROCO_ENABLE_CAPTURE": "maybe"}, platform_name="win32"))
        self.assertEqual(sync_token({}), "")
        self.assertEqual(sync_token({"ROCO_SYNC_TOKEN": "  abc  "}), "abc")

    def test_divert_stays_windows_only(self):
        self.assertFalse(divert_recording_allowed({"ROCO_ENABLE_CAPTURE": "1"}, platform_name="linux"))
        self.assertFalse(divert_recording_allowed({"ROCO_ENABLE_CAPTURE": "0"}, platform_name="win32"))
        self.assertTrue(divert_recording_allowed({}, platform_name="win32"))


class AppWiringTests(unittest.TestCase):
    def test_frontend_directory_is_the_project_frontend(self):
        frontend = app._FRONTEND_DIR
        self.assertTrue(os.path.isabs(frontend))
        self.assertTrue(frontend.endswith(os.path.join("frontend")))
        self.assertNotIn("\\", frontend)
        self.assertTrue(os.path.isfile(os.path.join(frontend, "index.html")))

    def test_cors_middleware_uses_the_resolved_list(self):
        origins = [
            layer.kwargs.get("allow_origins")
            for layer in app.app.user_middleware
            if getattr(layer.cls, "__name__", "") == "CORSMiddleware"
        ]
        self.assertEqual(origins, [app.CORS_ORIGINS])

    def test_main_passes_the_configured_bind(self):
        with mock.patch.object(uvicorn, "run") as run:
            app.main()
        run.assert_called_once_with(app.app, host=app.BIND_HOST, port=app.BIND_PORT)

    def test_mutating_request_still_requires_the_token(self):
        denied = asyncio.run(app.require_local_token(_request("POST"), _allow))
        self.assertEqual(denied.status_code, 401)

        allowed = asyncio.run(
            app.require_local_token(_request("POST", {"x-roco-token": app.API_TOKEN}), _allow)
        )
        self.assertEqual(allowed.status_code, 200)

        reading = asyncio.run(app.require_local_token(_request("GET"), _allow))
        self.assertEqual(reading.status_code, 200)

    def test_sync_token_only_opens_the_warehouse_import(self):
        headers = {"x-roco-token": "sync-secret"}
        with mock.patch.dict(os.environ, {"ROCO_SYNC_TOKEN": "sync-secret"}, clear=False):
            denied = asyncio.run(app.require_local_token(_request("POST", headers), _allow))
            allowed = asyncio.run(
                app.require_local_token(_request("POST", headers, "/api/sync/warehouse"), _allow)
            )
            missing = asyncio.run(app.require_local_token(_request("POST", path="/api/sync/warehouse"), _allow))
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(json.loads(denied.body)["detail"], "需要本机令牌")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(missing.status_code, 401)
        self.assertIn("同步令牌", json.loads(missing.body)["detail"])

    def test_record_and_stop_are_forbidden_when_capture_is_disabled(self):
        with mock.patch("backend.main.capture_enabled", return_value=False):
            with self.assertRaises(HTTPException) as recorded:
                app.api_record_packets({"mode": "divert"})
            with self.assertRaises(HTTPException) as stopped:
                app.api_stop_packets()
        self.assertEqual(recorded.exception.status_code, 403)
        self.assertIn("WinDivert", recorded.exception.detail)
        self.assertEqual(stopped.exception.status_code, 403)

    def test_divert_stays_forbidden_when_capture_is_on_but_not_windows(self):
        with (
            mock.patch("backend.main.capture_enabled", return_value=True),
            mock.patch("backend.main.divert_recording_allowed", return_value=False),
        ):
            with self.assertRaises(HTTPException) as caught:
                app.api_record_packets({"mode": "divert"})
        self.assertEqual(caught.exception.status_code, 403)
        self.assertIn("Windows", caught.exception.detail)

    def test_windows_divert_still_reaches_the_recorder(self):
        with (
            mock.patch("backend.main.capture_enabled", return_value=True),
            mock.patch("backend.main.divert_recording_allowed", return_value=True),
            mock.patch("backend.main._run_locked", return_value=None) as run,
        ):
            with self.assertRaises(HTTPException) as caught:
                app.api_record_packets({"mode": "divert"})
        self.assertEqual(caught.exception.status_code, 409)
        run.assert_called_once()


def _request(method: str, headers: dict | None = None, path: str = "/api/update_gender") -> Request:
    raw = []
    for key, value in (headers or {}).items():
        raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))
    scope = {"type": "http", "http_version": "1.1", "method": method, "path": path, "headers": raw}
    return Request(scope)


async def _allow(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    unittest.main()
