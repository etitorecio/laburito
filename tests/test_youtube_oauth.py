import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from app import main, publish


def fake_request():
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/youtube/oauth/start",
        "raw_path": b"/api/youtube/oauth/start",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("laburito.example", 443),
    }
    return Request(scope)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class YouTubeOAuthTests(unittest.TestCase):
    def test_start_builds_google_authorization_url_for_selected_workspace_channel(self):
        with patch.object(publish, "youtube_credentials", return_value={
            "client_id": "client-id", "client_secret": "client-secret", "refresh_token": ""
        }):
            with patch.object(main.db, "query_one", return_value={"id": 7}):
                with patch.object(main.db, "set_setting") as save:
                    result = main.youtube_oauth_start(fake_request(), channel_id=7)
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(result["authorization_url"])
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "accounts.google.com")
        self.assertEqual(params["redirect_uri"][0], "https://laburito.example/api/youtube/callback")
        self.assertEqual(params["response_type"][0], "code")
        self.assertEqual(params["access_type"][0], "offline")
        self.assertIn("youtube.upload", params["scope"][0])
        self.assertGreaterEqual(len(params["state"][0]), 32)
        self.assertIn(("youtube_oauth_channel_id", "7"), [call.args for call in save.call_args_list])

    def test_callback_saves_refresh_token_to_selected_channel_and_returns_to_accounts(self):
        account = {"channel_id": "UC123", "channel_title": "Canal de prueba"}
        settings = ["expected-state", "995", "https://laburito.example/api/youtube/callback", "7"]
        with patch.object(main.db, "get_setting", side_effect=settings):
            with patch.object(main.time, "time", return_value=1000):
                with patch.object(publish, "youtube_credentials", return_value={
                    "client_id": "client-id", "client_secret": "client-secret", "refresh_token": ""
                }):
                    with patch.object(main.urllib.request, "urlopen", return_value=FakeResponse({
                        "access_token": "access-token", "refresh_token": "refresh-token"
                    })):
                        with patch.object(main.db, "query_one", return_value={"id": 7}):
                            with patch.object(main.db, "set_setting"):
                                with patch.object(publish, "youtube_account_status", return_value=account) as verify:
                                    with patch.object(publish, "save_youtube_account") as save_account:
                                        with patch.object(main.persistence, "configured", return_value=True):
                                            with patch.object(main.persistence, "sync_backup", return_value=True) as backup:
                                                response = main.youtube_oauth_callback("auth-code", "expected-state", "")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/#/cuentas")
        verify.assert_called_once_with(refresh_token_override="refresh-token")
        save_account.assert_called_once_with(7, "refresh-token", account)
        backup.assert_called_once_with()

    def test_callback_rejects_expired_or_mismatched_state_before_token_exchange(self):
        settings = ["expected-state", "0", "https://laburito.example/api/youtube/callback", "7"]
        with patch.object(main.db, "get_setting", side_effect=settings):
            with patch.object(main.time, "time", return_value=1000):
                with patch.object(main.urllib.request, "urlopen") as exchange:
                    with self.assertRaises(HTTPException) as error:
                        main.youtube_oauth_callback("auth-code", "wrong-state", "")
        self.assertEqual(error.exception.status_code, 403)
        exchange.assert_not_called()


if __name__ == "__main__":
    unittest.main()
