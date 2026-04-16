from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class _Stream:
    """Single readable payload + coords (venice stream compatibility)."""

    data: Any
    coords: dict[str, Any]

    def read_json(self) -> Any:
        return self.data


class Connector:
    """In-memory data pipe compatible with LLMJury's prior venice.core.Connector usage."""

    def __init__(self, name: str = 'connector', persist_ext: str | None = None) -> None:
        self.name = name
        self.persist_ext = persist_ext
        self._chunks: list[dict[str, Any]] = []
        self._indexed_writes: list[tuple[int, Any]] = []

    def add_data(self, data: Any, **coords: Any) -> None:
        self._chunks.append({'data': data, 'coords': dict(coords)})

    def write_json(self, data: Any, index: int | None = None) -> None:
        self._indexed_writes.append((0 if index is None else int(index), data))

    def finished(self) -> None:
        return

    def reader(self) -> Iterator[_Stream]:
        for ch in self._chunks:
            yield _Stream(ch['data'], ch['coords'])

    def read_json(self) -> Any:
        if self._indexed_writes:
            self._indexed_writes.sort(key=lambda t: t[0])
            payloads = [p for _, p in self._indexed_writes]
            return payloads
        if not self._chunks:
            return []
        if len(self._chunks) == 1:
            return self._chunks[0]['data']
        merged: list[Any] = []
        for ch in self._chunks:
            d = ch['data']
            if isinstance(d, list):
                merged.extend(d)
            else:
                merged.append(d)
        return merged

    def all_text(self) -> str:
        if self._indexed_writes:
            parts: list[str] = []
            for _, payload in sorted(self._indexed_writes, key=lambda t: t[0]):
                parts.append(_payload_to_text(payload))
            return '\n'.join(parts)
        if not self._chunks:
            return ''
        parts = []
        for ch in self._chunks:
            parts.append(_payload_to_text(ch['data']))
        return '\n'.join(parts)


def _payload_to_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        c = payload.get('content')
        if c is not None:
            return str(c)
    if isinstance(payload, list):
        return '\n'.join(_payload_to_text(p) for p in payload)
    return str(payload)
