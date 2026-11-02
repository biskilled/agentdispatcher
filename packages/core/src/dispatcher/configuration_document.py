"""Narrow YAML scalar edits preserve the application's original document and comments."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

import yaml
from pydantic import Field, model_validator
from yaml.nodes import MappingNode, ScalarNode
from yaml.tokens import AliasToken, AnchorToken

from dispatcher.contracts import Contract


class EditableField(Contract):
    """Operator-approved model enums or bounded numeric/boolean parameters; no arbitrary strings."""

    kind: Literal["model", "integer", "number", "boolean"]
    models: list[str] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def constrained(self):
        """Model capabilities are represented by an explicit, operator-reviewed candidate list."""
        if self.kind == "model" and not self.models:
            raise ValueError("Model fields require an explicit compatible model list")
        if self.kind in ("integer", "number") and (
            self.minimum is None or self.maximum is None or self.minimum > self.maximum
        ):
            raise ValueError("Numeric parameters require valid lower and upper limits")
        return self

    def validate_value(self, value):
        """Reject coercion, non-finite numbers and values outside the approved field contract."""
        if self.kind == "model":
            valid = isinstance(value, str) and value in self.models
        elif self.kind == "boolean":
            valid = isinstance(value, bool)
        else:
            valid = type(value) in ((int,) if self.kind == "integer" else (int, float))
            valid = valid and math.isfinite(value) and self.minimum <= value <= self.maximum
        if not valid:
            raise ValueError("Configuration value is outside its approved field contract")


class ConfigSource(Contract):
    """Installation-authorized target and safe editable schema; web users cannot expand it."""

    tenant_id: UUID
    app: str
    environment: str
    kind: Literal["file", "api", "git"]
    root: Path | None = None
    path: str = ""
    endpoint: str = ""
    token_env: str = ""
    writable: bool = False
    fields: dict[str, EditableField] = Field(min_length=1)
    author_name: str = ""
    author_email: str = ""
    publish_remote: str = Field(default="", pattern=r"^([a-zA-Z0-9][a-zA-Z0-9_.-]*)?$")

    def fingerprint(self):
        """Invalidate proposals if the operator changes targets or permissions."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    """Connector revision and original bytes stay in memory, never in the usage database."""

    text: str
    revision: str

    @property
    def digest(self):
        """Use a content digest for version attribution and activation checks."""
        return hashlib.sha256(self.text.encode()).hexdigest()


class YamlDocument:
    """Only edit existing, unaliased block-mapping scalar nodes; unsupported syntax fails closed."""

    def __init__(self, text: str, fields: dict[str, EditableField], max_bytes: int):
        if len(text.encode()) > max_bytes:
            raise ValueError("Configuration exceeds the document size limit")
        self.text, self.fields, self.max_bytes = text, fields, max_bytes
        try:
            if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(text)):
                raise ValueError("YAML anchors and aliases are not supported for reviewed edits")
            self.root = yaml.compose(text, Loader=yaml.SafeLoader)
            self.values = yaml.safe_load(text)
            self._check(self.root)
        except (yaml.YAMLError, RecursionError):
            raise ValueError("Configuration is not supported safe YAML") from None

    def _check(self, node, depth=0):
        if depth > 30:
            raise ValueError("YAML nesting exceeds the supported depth")
        if isinstance(node, MappingNode):
            seen = set()
            for key, value in node.value:
                if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                    raise ValueError("YAML mapping keys must be strings")
                if key.value in seen:
                    raise ValueError("Duplicate YAML keys are not supported")
                seen.add(key.value)
                self._check(value, depth + 1)
        elif isinstance(getattr(node, "value", None), list):
            for value in node.value:
                self._check(value, depth + 1)

    def _field(self, path):
        node, value = self.root, self.values
        for part in path.split("."):
            if not isinstance(node, MappingNode) or node.flow_style:
                raise ValueError("Editable paths must use block mappings")
            pairs = {key.value: child for key, child in node.value}
            if part not in pairs:
                raise ValueError("Editable field is absent from the configuration")
            node, value = pairs[part], value[part]
        if not isinstance(node, ScalarNode) or node.style in ("|", ">"):
            raise ValueError("Only single-line scalar parameters can be changed")
        if node.start_mark.line != node.end_mark.line:
            raise ValueError("Multiline parameters are not supported")
        return node, value

    def inventory(self):
        """Expose safe parameters; prompts, credentials and other YAML stay local."""
        result = {}
        for path, policy in self.fields.items():
            _, value = self._field(path)
            policy.validate_value(value)
            result[path] = value
        return result

    def replace(self, changes: dict):
        """Return exact scalar diffs and new YAML, without reserializing unrelated content."""
        if not changes or not set(changes) <= set(self.fields):
            raise ValueError("Changes must target explicitly approved fields")
        edits, diff = [], []
        for path, value in changes.items():
            self.fields[path].validate_value(value)
            node, before = self._field(path)
            self.fields[path].validate_value(before)
            edits.append((node.start_mark.index, node.end_mark.index, json.dumps(value)))
            diff.append({"path": path, "before": before, "after": value})
        result = self.text
        for start, end, replacement in sorted(edits, reverse=True):
            result = result[:start] + replacement + result[end:]
        if len(result.encode()) > self.max_bytes:
            raise ValueError("Edited configuration exceeds the document size limit")
        return result, diff
