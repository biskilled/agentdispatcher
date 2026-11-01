"""Full OIDC redirect/token/JWKS verification with a local cryptographic identity provider."""

import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from dispatcher.api import create_app
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey


@pytest.mark.parametrize(
    "failure",
    [None, "issuer", "audience", "signature", "expired", "nonce", "state", "missing_token"],
)
def test_oidc_callback_verifies_claims_and_replay(settings, failure):
    key = RSAKey.generate_key(2048, parameters={"kid": "test-signing"})
    issuer = "https://oidc.example.test"
    client_id = "test-client"
    nonce = ""
    callback_count = 0

    def provider(request):
        nonlocal callback_count
        if request.url.path == "/metadata":
            return httpx.Response(
                200,
                json={
                    "issuer": issuer,
                    "authorization_endpoint": issuer + "/authorize",
                    "token_endpoint": issuer + "/token",
                    "jwks_uri": issuer + "/keys",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if request.url.path == "/keys":
            return httpx.Response(200, json={"keys": [key.as_dict(private=False)]})
        if request.url.path == "/token":
            callback_count += 1
            params = parse_qs(request.content.decode())
            assert params["code_verifier"][0]
            now = int(time.time())
            claims = {
                "iss": issuer,
                "sub": uuid4().hex,
                "aud": client_id,
                "iat": now,
                "exp": now + 300,
                "nonce": nonce,
                "email": "verified@example.test",
                "email_verified": True,
            }
            if failure == "issuer":
                claims["iss"] = "https://other.example.test"
            if failure == "audience":
                claims["aud"] = "other-client"
            if failure == "expired":
                claims["exp"] = now - 600
            if failure == "nonce":
                claims["nonce"] = "incorrect"
            signing = RSAKey.generate_key(2048) if failure == "signature" else key
            response = {"access_token": "fixture", "token_type": "Bearer"}
            if failure != "missing_token":
                response["id_token"] = jwt.encode(
                    {"alg": "RS256", "kid": "test-signing"}, claims, signing
                )
            return httpx.Response(200, json=response)
        raise AssertionError(f"Unexpected provider path: {request.url.path}")

    configured = settings.model_copy(
        update={"google_client_id": client_id, "google_metadata_url": issuer + "/metadata"}
    )
    app = create_app(configured, oauth_transport=httpx.MockTransport(provider))
    with TestClient(app) as client:
        start = client.get("/api/auth/google/start", follow_redirects=False)
        assert start.status_code == 302
        query = parse_qs(urlparse(start.headers["location"]).query)
        assert query["code_challenge_method"] == ["S256"]
        state, nonce = query["state"][0], query["nonce"][0]
        original_cookies = dict(client.cookies)
        params = {"code": "fixture", "state": "wrong" if failure == "state" else state}
        result = client.get("/api/auth/google/callback", params=params, follow_redirects=False)
        assert result.status_code == (307 if failure is None else 401), result.text
        if failure is None:
            assert client.get("/api/auth/me").json()["tenants"] == []
        else:
            assert client.get("/api/auth/me").status_code == 401
        client.cookies.clear()
        client.cookies.update(original_cookies)
        assert (
            client.get(
                "/api/auth/google/callback", params=params, follow_redirects=False
            ).status_code
            == 401
        )
        assert callback_count == (0 if failure == "state" else 1)
