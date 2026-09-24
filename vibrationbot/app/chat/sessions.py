from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from app.config import MAX_SESSION_TURNS, MAX_SESSIONS


@dataclass
class Turn:
    question: str
    answer: str


@dataclass
class Session:
    session_id: str
    turns: list[Turn] = field(default_factory=list)


class SessionService:
    """In-memory chat sessions, LRU-bounded and safe for concurrent access.

    FastAPI runs the sync chat handlers in a threadpool, so several requests
    genuinely mutate this state at once — every access is therefore locked.
    Sessions are capped so a long-running server cannot grow without bound.
    """

    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()
        self._max_sessions = max(1, max_sessions)

    def _touch(self, session_id: str) -> Session | None:
        """Mark a session most-recently-used. Caller must hold the lock."""
        session = self._sessions.get(session_id)
        if session is not None:
            self._sessions.move_to_end(session_id)
        return session

    def get_or_create(self, session_id: str | None) -> str:
        sid = session_id or str(uuid.uuid4())
        with self._lock:
            if self._touch(sid) is None:
                self._sessions[sid] = Session(session_id=sid)
                while len(self._sessions) > self._max_sessions:
                    self._sessions.popitem(last=False)
        return sid

    def add_turn(self, session_id: str, question: str, answer: str) -> None:
        with self._lock:
            session = self._touch(session_id)
            if session is None:
                session = Session(session_id=session_id)
                self._sessions[session_id] = session
                while len(self._sessions) > self._max_sessions:
                    self._sessions.popitem(last=False)
            session.turns.append(Turn(question=question, answer=answer))
            if len(session.turns) > MAX_SESSION_TURNS:
                del session.turns[:-MAX_SESSION_TURNS]

    def get_history(self, session_id: str) -> list[Turn]:
        with self._lock:
            session = self._touch(session_id)
            return list(session.turns) if session else []

    def get_last_question(self, session_id: str) -> str | None:
        turns = self.get_history(session_id)
        return turns[-1].question if turns else None


session_service = SessionService()
