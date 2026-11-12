"""Private source identities for adapted content, never a public document schema."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class NativeArtifact:
    """The exact received JSON bytes remain the immutable evidence root."""

    identity: str
    payload: bytes = field(repr=False)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.identity or not isinstance(self.payload, bytes):
            raise ValueError('native artifact needs an identity and actual JSON bytes')
        if not isinstance(json.loads(self.payload), dict):
            raise ValueError('native artifact root must be an object')
        object.__setattr__(self, 'sha256', hashlib.sha256(self.payload).hexdigest())

    @classmethod
    def from_object(cls, value: dict[str, Any], *, identity: str = 'in_memory_native') -> NativeArtifact:
        """Controlled structures have their own bytes; never claim a file digest."""
        return cls(identity, json.dumps(value, ensure_ascii=False, sort_keys=True).encode())

    def read(self) -> dict[str, Any]:
        return json.loads(self.payload)


@dataclass(frozen=True, slots=True)
class NativeLocator:
    artifact_sha256: str
    view: str
    path: str
    text_spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class NativeContentItem:
    """An input-owned occurrence, cell, relation container or media declaration."""

    identity: str
    kind: str
    locator: NativeLocator
    input_page: int | None
    branch: str
    branch_page: int | None
    original_page: int | None
    parent: str | None = None
    order: tuple[int, ...] = ()
    order_basis: str = 'unknown'
    raw_text: str | None = None
    details_json: str = '{}'

    @property
    def details(self) -> dict[str, Any]:
        return json.loads(self.details_json)


@dataclass(frozen=True, slots=True)
class NativeExecutionState:
    """Only original execution metadata is retained; observed answers are ignored."""

    artifact_identity: str | None
    artifact_sha256: str | None
    metadata_json: str

    @property
    def metadata(self) -> dict[str, Any]:
        return json.loads(self.metadata_json)


@dataclass(frozen=True, slots=True)
class NativeContentContract:
    artifact: NativeArtifact
    pipeline: str
    producer: str
    selected_pages: tuple[int, ...]
    original_pages: tuple[int, ...] | None
    items: tuple[NativeContentItem, ...]
    execution: NativeExecutionState
    page_bindings_json: str

    @property
    def page_bindings(self) -> list[dict[str, Any]]:
        return json.loads(self.page_bindings_json)

    def audit(self) -> dict[str, Any]:
        from dataclasses import asdict

        return {
            'artifact': {'identity': self.artifact.identity, 'sha256': self.artifact.sha256,
                         'identity_basis': 'actual_received_json_bytes'},
            'pipeline': self.pipeline, 'producer': self.producer,
            'configuration': {'artifact_sha256': self.artifact.sha256, 'view': 'configuration',
                              'path': '#/config' if 'config' in self.artifact.read() else None,
                              'basis': 'saved_configuration_identity; not a new execution attestation'},
            'selected_pages': list(self.selected_pages),
            'original_pages': list(self.original_pages) if self.original_pages else None,
            'page_bindings': self.page_bindings,
            'execution': {'artifact_identity': self.execution.artifact_identity,
                          'artifact_sha256': self.execution.artifact_sha256,
                          **self.execution.metadata},
            'inventory': [{**asdict(item), 'details': item.details} for item in self.items],
            'source_reads': 'disabled', 'media_reads': 'disabled',
            'primary_views': {'docling': 'document', 'glm': 'json_result'},
            'audit_views_supply_answers': False,
        }
