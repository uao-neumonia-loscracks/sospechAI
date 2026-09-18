"""Cliente HTTP de la fuente de datos del contrato UI-orquestador (UIF-07).

Usa exclusivamente stdlib ``urllib`` (UIF-12: ninguna dependencia nueva).
``room_code`` se normaliza a mayúsculas en el cliente (contrato §3), todas las
peticiones autenticadas llevan ``X-Session-Token`` (contrato §6) y las
respuestas no-2xx se traducen a ``ApiError`` ramificado por `code` (contrato
§8). Los fallos de red se convierten en ``ApiError("internal", 500, ...)`` sin
exponer el detalle del proveedor de red.
"""

import json
from urllib import error as http_error
from urllib import request as http_request

from src.ui.api import ApiError, RoomIdentity, StateSnapshot

_NETWORK_ERROR_MESSAGE = "El orquestador no está disponible (error de red)."
_MALFORMED_ERROR_MESSAGE = "El orquestador devolvió un error sin formato JSON."


class HttpSospechAI:
    """Fuente ``SospechAI`` que habla HTTP+JSON con el orquestador (contrato §§6-8)."""

    def __init__(self, base_url: str) -> None:
        """Fijar la base URL del orquestador sin la barra final."""
        self.base_url = base_url.rstrip("/")
        self._timeout = 5.0

    def create_room(self) -> RoomIdentity:
        """POST /rooms: crear la sala y unirse como anfitrión (201, contrato §6.1)."""
        body = self._request("POST", "/rooms", None, None)
        return RoomIdentity(body["room_code"], body["session_token"], body["alias"])

    def join_room(self, room_code: str) -> RoomIdentity:
        """POST /rooms/{code}/join: unirse a la sala en LOBBY (201, contrato §6.2)."""
        code = self._code(room_code)
        body = self._request("POST", f"/rooms/{code}/join", None, None)
        return RoomIdentity(code, body["session_token"], body["alias"])

    def get_state(self, room_code: str, session_token: str) -> StateSnapshot:
        """GET /rooms/{code}/state: leer la instantánea de estado (200, contrato §8)."""
        body = self._request(
            "GET", f"/rooms/{self._code(room_code)}/state", session_token, None
        )
        return StateSnapshot.from_mapping(body)

    def start(self, room_code: str, session_token: str) -> None:
        """POST /rooms/{code}/start: registrar la IA y arrancar (204, contrato §6.3)."""
        self._request(
            "POST", f"/rooms/{self._code(room_code)}/start", session_token, None
        )

    def open_voting(self, room_code: str, session_token: str) -> None:
        """POST /rooms/{code}/voting/open: abrir la votación (204, contrato §6.5)."""
        self._request(
            "POST", f"/rooms/{self._code(room_code)}/voting/open", session_token, None
        )

    def submit_message(self, room_code: str, session_token: str, text: str) -> None:
        """POST /rooms/{code}/messages: enviar un mensaje de ronda (204, contrato §6.4)."""
        self._request(
            "POST",
            f"/rooms/{self._code(room_code)}/messages",
            session_token,
            {"text": text},
        )

    def submit_vote(self, room_code: str, session_token: str, suspect: str) -> None:
        """POST /rooms/{code}/votes: emitir el voto de un humano (204, contrato §6.6)."""
        self._request(
            "POST",
            f"/rooms/{self._code(room_code)}/votes",
            session_token,
            {"suspect": suspect},
        )

    def _request(
        self,
        method: str,
        path: str,
        session_token: str | None,
        payload: dict | None,
    ) -> dict | None:
        """Ejecutar la petición y devolver el cuerpo JSON (o None en 204)."""
        headers: dict[str, str] = {}
        data = None
        if session_token is not None:
            headers["X-Session-Token"] = session_token
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        request = http_request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with http_request.urlopen(request, timeout=self._timeout) as response:
                if response.status == 204:
                    return None
                return json.loads(response.read().decode("utf-8"))
        except http_error.HTTPError as exc:
            self._raise_error(exc)
        except (http_error.URLError, OSError):
            raise ApiError("internal", 500, _NETWORK_ERROR_MESSAGE) from None

    def _raise_error(self, exc: http_error.HTTPError) -> None:
        """Traducir una respuesta no-2xx a ``ApiError`` por `code` (contrato §8)."""
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError("malformed_request", 400, _MALFORMED_ERROR_MESSAGE) from None
        code = body.get("code", "malformed_request")
        message = body.get("message", _MALFORMED_ERROR_MESSAGE)
        raise ApiError(code, exc.code, message) from None

    def _code(self, room_code: str) -> str:
        """Normalizar el código de sala a mayúsculas como el servidor (contrato §3)."""
        return room_code.upper()
