from typing import Any, Callable

import pytest

from api_client import rest_client


class UnauthorizedResponse:
    status_code = 401


def arrange_failed_token_refresh(monkeypatch, *, http_method: str) -> None:
    def fake_get_token(force_refresh: bool = False) -> str:
        if force_refresh:
            raise rest_client.auth.AuthError("token refresh is unavailable")
        return "cached-token"

    def fake_http_request(*args: Any, **kwargs: Any) -> UnauthorizedResponse:
        return UnauthorizedResponse()

    monkeypatch.setattr(
        rest_client.auth,
        "get_token",
        fake_get_token,
    )
    monkeypatch.setattr(
        rest_client.httpx,
        http_method,
        fake_http_request,
    )


def assert_refresh_failure_becomes_api_error(
    operation: Callable[[], Any],
) -> None:
    with pytest.raises(
        rest_client.APIError,
        match="authentication failed: token refresh is unavailable",
    ):
        operation()


def test_get_refresh_auth_failure_becomes_api_error(monkeypatch) -> None:
    arrange_failed_token_refresh(
        monkeypatch,
        http_method="get",
    )

    assert_refresh_failure_becomes_api_error(
        lambda: rest_client._get("/airspace/nfzs"),
    )


def test_multipart_refresh_auth_failure_becomes_api_error(monkeypatch) -> None:
    arrange_failed_token_refresh(
        monkeypatch,
        http_method="post",
    )

    assert_refresh_failure_becomes_api_error(
        lambda: rest_client._post_multipart(
            "/ml_detections/upload",
            files={},
        ),
    )


def test_media_refresh_auth_failure_becomes_api_error(monkeypatch) -> None:
    arrange_failed_token_refresh(
        monkeypatch,
        http_method="get",
    )

    assert_refresh_failure_becomes_api_error(
        lambda: rest_client.get_media_bytes(
            "https://media.example.test/image.jpg",
        ),
    )


def test_json_post_refresh_auth_failure_becomes_api_error(monkeypatch) -> None:
    arrange_failed_token_refresh(
        monkeypatch,
        http_method="post",
    )

    assert_refresh_failure_becomes_api_error(
        lambda: rest_client._post_json(
            "/aircraft/drones/example/commands",
            json_body={},
        ),
    )


def test_json_patch_refresh_auth_failure_becomes_api_error(monkeypatch) -> None:
    arrange_failed_token_refresh(
        monkeypatch,
        http_method="patch",
    )

    assert_refresh_failure_becomes_api_error(
        lambda: rest_client._patch_json(
            "/aircraft/drones/example",
            json_body={},
        ),
    )
