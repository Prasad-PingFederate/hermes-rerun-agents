"""
Hermes Enterprise Event-Stream Bus.

Inspired by OpenHands / event-sourced agent architectures, provides an
append-only typed event stream for actions, observations, AST verdicts,
and test execution telemetry.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class HermesEvent:
    """Typed atomic event emitted across the multi-agent sprint lifecycle."""
    event_id: str
    event_type: str  # ActionTriggered, ObservationReceived, PatchSynthesized, ASTVerified, RerunVerdict
    source_agent: str
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventStreamBus:
    """Enterprise append-only event bus recording and streaming multi-agent actions."""

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.storage_dir = self.workspace_path / ".rerun_tasks"
        self.log_file = self.storage_dir / "event_stream.jsonl"
        self._events: List[HermesEvent] = []
        self._subscribers: List[Callable[[HermesEvent], None]] = []

    def subscribe(self, callback: Callable[[HermesEvent], None]) -> None:
        """Register a subscriber callback for real-time live events."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def emit(
        self,
        event_type: str,
        source_agent: str,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HermesEvent:
        """Emits a new typed event to memory, disk log, and all active subscribers."""
        ev = HermesEvent(
            event_id=f"ev_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
            event_type=event_type,
            source_agent=source_agent,
            timestamp=time.time(),
            payload=payload or {},
            metadata=metadata or {},
        )
        self._events.append(ev)

        # Notify subscribers
        for sub in self._subscribers:
            try:
                sub(ev)
            except Exception:
                pass

        # Append to disk JSONL
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(ev.to_json() + "\n")
        except Exception:
            pass

        return ev

    def get_events(self, event_type: Optional[str] = None) -> List[HermesEvent]:
        """Returns all emitted events, optionally filtered by event type."""
        if event_type:
            return [e for e in self._events if e.event_type == event_type]
        return list(self._events)

    def replay_from_disk(self) -> List[HermesEvent]:
        """Replays all events recorded in event_stream.jsonl."""
        replayed: List[HermesEvent] = []
        if not self.log_file.is_file():
            return replayed
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        replayed.append(HermesEvent(**data))
        except Exception:
            pass
        return replayed
