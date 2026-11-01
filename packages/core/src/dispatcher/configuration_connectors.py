"""Authorised file, conditional API and review-branch Git adapters for app-owned YAML."""

import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from dispatcher.configuration_document import Snapshot


class RevisionConflict(ValueError):
    """An external edit invalidated the reviewed version."""


class Connector(Protocol):
    """Connector targets are installation configuration, never arbitrary request URLs or paths."""

    def read(self) -> Snapshot:
        """Read current authoritative bytes and concurrency revision."""
        ...

    def write(self, expected: Snapshot, text: str) -> Snapshot:
        """Conditionally apply a reviewed edit or create a reviewable Git branch."""
        ...


class FileConnector:
    """Local app files must be in an operator-approved directory with no symlink components."""

    def __init__(self, root: Path, relative_path: str, max_bytes: int):
        self.root, self.relative_path, self.max_bytes = root.resolve(), relative_path, max_bytes

    def _path(self):
        relative = Path(self.relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Configuration path escapes the authorised directory")
        path = self.root
        for part in relative.parts:
            path /= part
            if path.is_symlink():
                raise ValueError("Symlink configuration paths are not supported")
        if not path.is_file():
            raise ValueError("Configuration file does not exist")
        return path

    def read(self):
        """Hash a bounded file; the hash is its optimistic concurrency revision."""
        with self._path().open("rb") as source:
            content = source.read(self.max_bytes + 1)
        if len(content) > self.max_bytes:
            raise ValueError("Configuration exceeds the document size limit")
        snapshot = Snapshot(content.decode("utf-8"), "")
        return Snapshot(snapshot.text, snapshot.digest)

    def write(self, expected, text):
        """Replace atomically; callers serialize writes and external writers must coordinate."""
        if self.read().revision != expected.revision:
            raise RevisionConflict("Configuration changed since review")
        path = self._path()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
                temporary = Path(target.name)
                os.fchmod(target.fileno(), stat.S_IMODE(path.stat().st_mode))
                target.write(text.encode())
                target.flush()
                os.fsync(target.fileno())
            if self.read().revision != expected.revision:
                raise RevisionConflict("Configuration changed during apply")
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        result = Snapshot(text, "")
        return Snapshot(text, result.digest)


class ApiConnector:
    """Use a configured endpoint with strong ETags and mandatory server-side If-Match handling."""

    def __init__(self, endpoint, token, timeout, max_bytes, transport=None):
        self.endpoint, self.max_bytes = endpoint, max_bytes
        self.client = httpx.Client(
            headers={"Authorization": "Bearer " + token} if token else {},
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    def read(self):
        """Bound response bytes before decoding; never follow a credential-bearing redirect."""
        with self.client.stream("GET", self.endpoint) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self.max_bytes:
                    raise ValueError("Configuration exceeds the document size limit")
                chunks.append(chunk)
            revision = response.headers.get("etag", "")
            if not revision.startswith('"') or not revision.endswith('"'):
                raise ValueError("Configuration APIs must return strong ETags")
            return Snapshot(b"".join(chunks).decode("utf-8"), revision)

    def write(self, expected, text):
        """A 412 is a review conflict; the source API is responsible for atomic compare-and-set."""
        response = self.client.put(
            self.endpoint,
            content=text.encode(),
            headers={"If-Match": expected.revision, "Content-Type": "application/yaml"},
        )
        if response.status_code == 412:
            raise RevisionConflict("Configuration changed since review")
        response.raise_for_status()
        current = self.read()
        if current.text != text:
            raise RevisionConflict("Configuration API did not retain the applied document")
        return current

    def close(self):
        """Release pooled API sockets after one configuration operation."""
        self.client.close()


class GitConnector:
    """Create an unpushed review branch using Git plumbing; preserve the current checkout/index."""

    def __init__(
        self, root: Path, relative_path: str, max_bytes: int, author: dict, timeout: float
    ):
        self.root, self.path, self.max_bytes = root.resolve(), relative_path, max_bytes
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise ValueError("Configuration path escapes the authorised repository")
        self.author, self.timeout = author, timeout

    def _git(self, *args, input=None, extra=None):
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            input=input,
            text=True,
            capture_output=True,
            timeout=self.timeout,
            env={**os.environ, **(extra or {})},
        )
        if result.returncode:
            raise ValueError("Authorised Git configuration operation failed")
        return result.stdout.strip()

    def read(self):
        """Use committed HEAD, not potentially unrelated uncommitted working files."""
        revision = self._git("rev-parse", "HEAD")
        entry = self._git("ls-tree", revision, "--", self.path)
        if not entry.startswith(("100644 blob ", "100755 blob ")):
            raise ValueError("Git configuration target must be a regular committed file")
        size = int(self._git("cat-file", "-s", f"{revision}:{self.path}"))
        if size > self.max_bytes:
            raise ValueError("Configuration exceeds the document size limit")
        # subprocess output is kept verbatim here: a trailing newline is part of the digest.
        result = subprocess.run(
            ["git", "-C", str(self.root), "show", f"{revision}:{self.path}"],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=True,
        )
        return Snapshot(result.stdout, revision)

    def write(self, expected, text):
        """Create a review branch; deployment and activation remain separate actions."""
        if self.read().revision != expected.revision:
            raise RevisionConflict("Repository changed since review")
        branch = "refs/heads/dispatcher-review/" + uuid4().hex
        with tempfile.TemporaryDirectory() as directory:
            extra = {"GIT_INDEX_FILE": str(Path(directory) / "index"), **self.author}
            self._git("read-tree", expected.revision, extra=extra)
            blob = self._git("hash-object", "-w", "--stdin", input=text)
            mode = self._git("ls-tree", expected.revision, "--", self.path).split()[0]
            self._git("update-index", "--add", "--cacheinfo", mode, blob, self.path, extra=extra)
            tree = self._git("write-tree", extra=extra)
            commit = self._git(
                "commit-tree",
                tree,
                "-p",
                expected.revision,
                input="Review AgentDispatcher configuration proposal\n",
                extra=extra,
            )
            if self.read().revision != expected.revision:
                raise RevisionConflict("Repository changed during apply")
            self._git("update-ref", branch, commit, "")
        return Snapshot(text, branch + "@" + commit)
