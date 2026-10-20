"""F7D: per-session review gate for an external authenticated host.

NOT a login, HTTP server or CSRF implementation. The host must supply a
trusted authenticated identity callback and guard the UI event. This gate
never executes Maestro, geometry, book retrieval, CAD or LLMs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
from threading import RLock
import time
from typing import Any, Callable

from .maestro import MaestroError
from .natural_intake import preview_natural_request


@dataclass(frozen=True)
class _Pending:
    principal: str
    session: str
    expires: float
    challenge: str
    fingerprint: str
    snapshot: str


class ReviewGate:
    """Single-process staging bound to host-authenticated principal/session.

    identity(context) must be resolved server-side AFTER host authentication.
    Never use principal/session IDs supplied by a model or browser request.
    """

    def __init__(
        self, *, authenticated_identity: Callable[[Any], tuple[str, str]],
        ttl_seconds: int = 600, max_pending: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not callable(authenticated_identity) or not callable(clock):
            raise MaestroError("F7D exige un proveedor de identidad y reloj confiables.")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise MaestroError("ttl_seconds debe estar entre 1 y 3600.")
        if type(max_pending) is not int or not 1 <= max_pending <= 1000:
            raise MaestroError("max_pending debe estar entre 1 y 1000.")
        self._identity = authenticated_identity
        self._clock = clock
        self._ttl = ttl_seconds
        self._capacity = max_pending
        self._lock = RLock()
        self._pending: dict[str, _Pending] = {}

    def _principal(self, context: Any) -> tuple[str, str]:
        try:
            pair = self._identity(context)
        except Exception:
            raise MaestroError("F7D no pudo verificar la identidad autenticada.") from None
        if (type(pair) is not tuple or len(pair) != 2
                or any(type(v) is not str or not v or len(v) > 128
                       or v != v.strip() for v in pair)):
            raise MaestroError("F7D identidad y sesión autenticadas inválidas.")
        return pair

    def _expire(self, now: float) -> None:
        for key, value in list(self._pending.items()):
            if value.expires <= now:
                del self._pending[key]

    def stage(self, context: Any, utterance: str,
              candidate: dict[str, Any]) -> dict[str, Any]:
        """Stage exact JSON without executing the untrusted suggestion."""
        user, session = self._principal(context)
        preview = preview_natural_request(utterance, candidate)
        if preview["status"] != "NEEDS_USER_CONFIRMATION":
            raise MaestroError("Se exige una propuesta JSON explícita.")
        snapshot = json.dumps(
            {"utterance": preview["utterance"],
             "request": preview["proposed_request"]},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        review_id, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self._lock:
            now = self._clock()
            self._expire(now)
            if len(self._pending) >= self._capacity:
                raise MaestroError("Capacidad de revisiones pendientes agotada.")
            self._pending[review_id] = _Pending(
                user, session, now + self._ttl, nonce, digest, snapshot
            )
        return {
            "status": "NEEDS_USER_CONFIRMATION",
            "review_id": review_id,
            "confirmation_challenge": nonce,
            "fingerprint": digest,
            "utterance": preview["utterance"],
            "proposed_request": preview["proposed_request"],
            "expires_in_seconds": self._ttl,
            "executed_tools": [],
            "fabrication_ready": False, "cutting_ready": False,
            "drilling_ready": False, "purchase_ready": False,
        }

    def consume(
        self, context: Any, *, review_id: str,
        confirmation_challenge: str, fingerprint: str,
    ) -> dict[str, Any]:
        """Consume once and RETURN reviewed JSON, never call Maestro.

        The trusted host MUST enforce a deliberate human UI action, a valid
        authentication session and its own CSRF/same-origin checks first.
        """
        user, session = self._principal(context)
        if any(type(v) is not str or not v or len(v) > 256
               for v in (review_id, confirmation_challenge, fingerprint)):
            raise MaestroError("Confirmación F7D inválida.")
        with self._lock:
            self._expire(self._clock())
            record = self._pending.get(review_id)
            if record is None:
                raise MaestroError("Revisión inexistente, caducada o ya utilizada.")
            if not (hmac.compare_digest(user, record.principal)
                    and hmac.compare_digest(session, record.session)):
                raise MaestroError("La revisión pertenece a otra sesión autenticada.")
            if not (hmac.compare_digest(confirmation_challenge, record.challenge)
                    and hmac.compare_digest(fingerprint, record.fingerprint)):
                raise MaestroError("Confirmación diferente de la propuesta mostrada.")
            del self._pending[review_id]
        approved = json.loads(record.snapshot)
        return {
            "status": "APPROVED_FOR_MAESTRO_REVALIDATION_ONLY",
            "approved_request": approved["request"],
            "utterance": approved["utterance"],
            "executed_tools": [],
            "fabrication_ready": False, "cutting_ready": False,
            "drilling_ready": False, "purchase_ready": False,
        }

    def cancel(self, context: Any, *, review_id: str) -> None:
        """Revoke a ticket, but only from its authenticated session."""
        user, session = self._principal(context)
        if type(review_id) is not str or not review_id:
            raise MaestroError("Identificador de revisión inválido.")
        with self._lock:
            self._expire(self._clock())
            record = self._pending.get(review_id)
            if record is None:
                return
            if not (hmac.compare_digest(user, record.principal)
                    and hmac.compare_digest(session, record.session)):
                raise MaestroError("No es posible cancelar una revisión de otra sesión.")
            del self._pending[review_id]
