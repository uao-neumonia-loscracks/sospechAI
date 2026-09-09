"""Reglas de partida independientes de la interfaz y del modelo de lenguaje.

Este módulo se ejecuta en un solo proceso. Sus decisiones provisionales están
documentadas en docs/ACUERDOS_R2.md; todavía no es un servidor multijugador.
"""

import math
import time
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class GameState(StrEnum):
    """Etapas permitidas en este primer incremento."""

    LOBBY = "LOBBY"
    ROUND = "RONDA"
    DISCUSSION = "DISCUSION"
    VOTING = "VOTACION"
    REVEAL = "REVELACION"


class RuleViolation(ValueError):
    """Una acción del jugador no cumple las reglas o la etapa actual."""


@dataclass(frozen=True)
class Player:
    """Identidad interna; el indicador de IA no se publica durante la partida."""

    alias: str
    is_ai: bool


@dataclass(frozen=True)
class Message:
    """Una respuesta aceptada por el controlador."""

    round_number: int
    alias: str
    text: str


def normalize_text(text: str) -> str:
    """Unificar espacios y representación Unicode, conservando tildes y estilo."""
    return " ".join(unicodedata.normalize("NFC", text).split())


class Game:
    """Controlar respuestas, transiciones y votos de una partida en memoria."""

    def __init__(
        self,
        *,
        rounds: int = 2,
        max_words: int = 15,
        round_timeout: float | None = 20.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Crear una sala vacía con reglas explícitas y modificables."""
        if rounds < 1 or max_words < 1:
            raise ValueError("Las rondas y el límite de palabras deben ser positivos.")
        if round_timeout is not None and (
            not math.isfinite(round_timeout) or round_timeout <= 0
        ):
            raise ValueError("La ventana de respuesta debe ser finita y positiva.")
        self.rounds = rounds
        self.max_words = max_words
        self.state = GameState.LOBBY
        self.round_number = 0
        self._players: dict[str, Player] = {}
        self._messages: list[Message] = []
        self._votes: dict[str, str] = {}
        self.round_timeout = round_timeout
        self._clock = clock
        self._deadline: float | None = None
        self._interruption_reason: str | None = None

    def remaining_time(self) -> float | None:
        """Consultar el presupuesto de la ronda, usando un reloj monotónico."""
        if self.state != GameState.ROUND or self._deadline is None:
            return None
        return max(0.0, self._deadline - self._clock())

    def check_expiration(self) -> None:
        """Cerrar una ronda vencida; el servicio debe invocarlo también con un timer."""
        if self.remaining_time() == 0:
            self.interrupt("round_timeout")

    def interrupt(self, reason: str) -> None:
        """Revelar tras un fallo técnico y excluir la partida del cálculo de detección."""
        if self.state not in (GameState.ROUND, GameState.DISCUSSION, GameState.VOTING):
            raise RuleViolation("Solo se puede interrumpir una partida activa.")
        allowed = {
            "round_timeout",
            "engine_timeout",
            "engine_unavailable",
            "engine_protocol",
            "engine_rejected",
            "invalid_engine_response",
        }
        if reason not in allowed:
            raise ValueError(
                "Usa un código de interrupción conocido, sin datos del proveedor."
            )
        self._interruption_reason = reason
        self.state = GameState.REVEAL

    def validate_ai_turn(self, alias: str, expected_round: int) -> None:
        """Rechazar llamadas para humanos o turnos ya enviados antes de invocar la IA."""
        self.check_expiration()
        self._require_state(GameState.ROUND)
        if expected_round != self.round_number or not self._player(alias).is_ai:
            raise RuleViolation("El turno de IA ya no es válido.")
        if any(
            m.alias == alias and m.round_number == expected_round
            for m in self._messages
        ):
            raise RuleViolation("El impostor ya respondió esta ronda.")

    def _require_state(self, expected: GameState) -> None:
        """Rechazar operaciones que pertenecen a una etapa diferente."""
        if self.state != expected:
            raise RuleViolation(
                f"Esta acción requiere {expected}; la partida está en {self.state}."
            )

    def _player(self, alias: str) -> Player:
        """Resolver un alias registrado o informar una acción inválida."""
        if alias not in self._players:
            raise RuleViolation("Ese jugador no pertenece a la partida.")
        return self._players[alias]

    def add_player(self, *, is_ai: bool = False) -> str:
        """Registrar un participante; la marca de IA es una decisión del servidor."""
        self._require_state(GameState.LOBBY)
        if is_ai and any(player.is_ai for player in self._players.values()):
            raise RuleViolation("La partida ya tiene un impostor.")
        alias = f"Jugador {len(self._players) + 1}"
        self._players[alias] = Player(alias=alias, is_ai=is_ai)
        return alias

    def start(self) -> None:
        """Abrir la primera ronda con al menos dos humanos y una IA."""
        self._require_state(GameState.LOBBY)
        ai_count = sum(player.is_ai for player in self._players.values())
        human_count = len(self._players) - ai_count
        if ai_count != 1 or human_count < 2:
            raise RuleViolation(
                "Se necesitan al menos dos humanos y exactamente una IA."
            )
        self.round_number = 1
        self.state = GameState.ROUND
        self._deadline = (
            self._clock() + self.round_timeout
            if self.round_timeout is not None
            else None
        )

    def submit_message(
        self, alias: str, text: str, *, expected_round: int | None = None
    ) -> str:
        """Validar igual a humanos e IA y avanzar cuando todos hayan respondido."""
        self.check_expiration()
        self._require_state(GameState.ROUND)
        if expected_round is not None and expected_round != self.round_number:
            raise RuleViolation("La respuesta pertenece a otra ronda.")
        self._player(alias)
        current = [
            message
            for message in self._messages
            if message.round_number == self.round_number
        ]
        if any(message.alias == alias for message in current):
            raise RuleViolation("Ya enviaste una respuesta en esta ronda.")
        normalized = normalize_text(text)
        if not normalized:
            raise RuleViolation("Escribe una respuesta que contenga texto.")
        if len(normalized.split()) > self.max_words:
            raise RuleViolation(
                f"La respuesta admite máximo {self.max_words} palabras."
            )
        self._messages.append(Message(self.round_number, alias, normalized))
        if len(current) + 1 == len(self._players):
            if self.round_number < self.rounds:
                self.round_number += 1
                self._deadline = (
                    self._clock() + self.round_timeout
                    if self.round_timeout is not None
                    else None
                )
            else:
                self.state = GameState.DISCUSSION
        return normalized

    def open_voting(self) -> None:
        """Abrir la votación después de completar todas las rondas."""
        self._require_state(GameState.DISCUSSION)
        self.state = GameState.VOTING

    def cast_vote(self, voter_alias: str, suspect_alias: str) -> None:
        """Aceptar un voto por humano y revelar al impostor al recibirlos todos."""
        self._require_state(GameState.VOTING)
        voter = self._player(voter_alias)
        self._player(suspect_alias)
        if voter.is_ai:
            raise RuleViolation("En estas reglas provisionales, la IA no vota.")
        if voter_alias == suspect_alias:
            raise RuleViolation("En estas reglas provisionales, no puedes votarte.")
        if voter_alias in self._votes:
            raise RuleViolation("Ya registraste tu voto.")
        self._votes[voter_alias] = suspect_alias
        human_count = sum(not player.is_ai for player in self._players.values())
        if len(self._votes) == human_count:
            self.state = GameState.REVEAL

    def public_state(self) -> dict:
        """Ofrecer una vista sin identidades de IA ni votos individuales anticipados."""
        self.check_expiration()
        view = {
            "state": self.state.value,
            "round_number": self.round_number,
            "rounds": self.rounds,
            "max_words": self.max_words,
            "players": list(self._players),
            "messages": [
                {
                    "round_number": message.round_number,
                    "alias": message.alias,
                    "text": message.text,
                }
                for message in self._messages
            ],
            "votes_received": len(self._votes),
            "remaining_seconds": self.remaining_time(),
        }
        if self.state == GameState.REVEAL:
            view["result"] = self.result()
        return view

    def result(self) -> dict:
        """Revelar etiquetas y calcular aciertos solo después de cerrar la votación."""
        self._require_state(GameState.REVEAL)
        impostor = next(
            player.alias for player in self._players.values() if player.is_ai
        )
        scores = {
            alias: int(suspect == impostor) for alias, suspect in self._votes.items()
        }
        valid_game = self._interruption_reason is None
        return {
            "state": self.state.value,
            "impostor_alias": impostor,
            "rounds": self.rounds,
            "max_words": self.max_words,
            "votes": dict(self._votes),
            "vote_counts": dict(Counter(self._votes.values())),
            "scores": scores if valid_game else {},
            "valid_game": valid_game,
            "interruption_reason": self._interruption_reason,
            "tasa_deteccion": (
                sum(scores.values()) / len(scores) if valid_game else None
            ),
            "transcript": [
                {
                    "round_number": message.round_number,
                    "alias": message.alias,
                    "text": message.text,
                    "is_ai": self._players[message.alias].is_ai,
                }
                for message in self._messages
            ],
        }
