"""Exercise the proposed endpoint with AgentDesk's real JWT verifier and an isolated user store."""

import argparse
import importlib.util
import secrets
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4


def main():
    """Run without contacting AgentDesk production, changing users, or printing credentials."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--agentdesk", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.agentdesk / "backend"))
    from core import auth
    from core.config import settings
    from fastapi import HTTPException
    from jose import jwt

    spec = importlib.util.spec_from_file_location(
        "dispatcher_identity_under_test", Path(__file__).with_name("route_dispatcher_identity.py")
    )
    endpoint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(endpoint)
    settings.secret_key = secrets.token_urlsafe(32)
    settings.dev_mode, settings.require_auth = False, True

    class IdentityTests(unittest.TestCase):
        def setUp(self):
            self.database = MagicMock()
            connection = self.database.conn.return_value.__enter__.return_value
            self.cursor = connection.cursor.return_value.__enter__.return_value
            self.cursor.fetchone.return_value = (uuid4(), 2, "editor", True, "approved")
            self.database.is_available.return_value = True
            self.patcher = patch.object(endpoint, "db", self.database)
            self.patcher.start()
            self.addCleanup(self.patcher.stop)

        def token(self, **changes):
            payload = {"sub": "42", "exp": datetime.now(timezone.utc).timestamp() + 60, **changes}
            return "Bearer " + jwt.encode(payload, settings.secret_key, algorithm=auth.ALGORITHM)

        def rejected(self, credential, status):
            with self.assertRaises(HTTPException) as caught:
                endpoint.dispatcher_identity(credential)
            self.assertEqual(caught.exception.status_code, status)

        def test_real_signature_and_expiration(self):
            result = endpoint.dispatcher_identity(self.token())
            self.assertEqual(result["client_id"], "2")
            self.assertEqual(result["role"], "member")
            self.assertNotIn("email", result)
            self.rejected(self.token(exp=1), 401)
            self.rejected(
                "Bearer "
                + jwt.encode(
                    {"sub": "42", "exp": 9999999999}, "another-secret", algorithm=auth.ALGORITHM
                ),
                401,
            )
            self.rejected(
                "Bearer "
                + jwt.encode({"sub": "42"}, settings.secret_key, algorithm=auth.ALGORITHM),
                401,
            )
            self.rejected("Bearer ad_integration", 401)

        def test_live_membership_changes(self):
            credential = self.token()
            for row in (
                None,
                (uuid4(), 2, "editor", False, "approved"),
                (uuid4(), 2, "admin", True, "pending"),
                (uuid4(), None, "admin", True, "approved"),
            ):
                self.cursor.fetchone.return_value = row
                self.rejected(credential, 403)

        def test_no_development_or_database_fallback(self):
            credential = self.token()
            with patch.object(settings, "dev_mode", True):
                self.rejected(credential, 503)
            with patch.object(settings, "require_auth", False):
                self.rejected(credential, 503)
            self.database.is_available.return_value = False
            self.rejected(credential, 503)
            self.database.is_available.return_value = True
            self.cursor.execute.side_effect = RuntimeError("private database diagnostics")
            self.rejected(credential, 503)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(IdentityTests)
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
