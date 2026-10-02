"""Reglas de partida independientes de la interfaz y del modelo de lenguaje.

Este módulo se ejecuta en un solo proceso. Sus decisiones provisionales están
documentadas en docs/ACUERDOS_R2.md; todavía no es un servidor multijugador.
"""

import math
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

# Reexportado para no romper a server, que importa el nombre desde este módulo.
# La implementación vive en src/common/text.py.
from src.common.text import normalize_text as normalize_text

# Reservado por el contrato: votar con este alias registra una abstención explícita.
ABSTAIN_SENTINEL = "__abstain__"

# Pregunta/tema de cada ronda: la IA la usa para generar su respuesta y la vista
# la expone a los humanos (round_prompt). Fijas por ahora; el servidor las inyecta.
DEFAULT_PROMPTS = (
    "¿Qué harías si se va la luz justo antes de entregar un trabajo?",
    "¿Qué comida escogerías después de una clase larga?",
)


class GameState(StrEnum):
    """Etapas permitidas en este primer incremento."""

    LOBBY = "LOBBY"
    ROUND = "RONDA"
    DISCUSSION = "DISCUSION"
    VOTING = "VOTACION"
    REVEAL = "REVELACION"


# Fases con ventana temporal propia y mínimo de humanos presentes para no
# cerrar la partida como inválida al vencer la ventana.
TIMED_STATES = {GameState.ROUND, GameState.DISCUSSION, GameState.VOTING}
QUORUM_MIN_HUMANS = 2

# Eventos de ciclo de vida que el dominio produce exactamente una vez por
# transición; el servidor los persiste en el flujo game_events.
GAME_EVENT_TYPES = ("game.started", "round.started", "round.completed", "game.closed")

# Sumidero opcional: recibe (tipo de evento, carga) en cada transición.
EventSink = Callable[[str, dict], None]


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


class Game:
    """Controlar respuestas, transiciones y votos de una partida en memoria."""

    def __init__(
        self,
        *,
        rounds: int = 2,
        max_words: int = 15,
        round_timeout: float | None = 20.0,
        prompts: Sequence[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        event_sink: EventSink | None = None,
    ) -> None:
        """Crear una sala vacía con reglas explícitas y preguntas inyectables."""
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
        self.prompts = tuple(prompts) if prompts is not None else DEFAULT_PROMPTS
        self._players: dict[str, Player] = {}
        self._messages: list[Message] = []
        self._votes: dict[str, str | None] = {}
        self._explicit_abstentions: set[str] = set()
        self.round_timeout = round_timeout
        self._clock = clock
        self._deadline: float | None = None
        self._interruption_reason: str | None = None
        self._close_reason: str | None = None
        self.event_sink = event_sink

    def remaining_time(self) -> float | None:
        """Consultar el presupuesto de la fase temporal actual, si tiene ventana."""
        if self.state not in TIMED_STATES or self._deadline is None:
            return None
        return max(0.0, self._deadline - self._clock())

    def _set_deadline(self) -> None:
        """Fijar la ventana de la fase temporal desde el reloj compartido."""
        self._deadline = (
            self._clock() + self.round_timeout
            if self.round_timeout is not None
            else None
        )

    def _emit(self, event_type: str, payload: dict) -> None:
        """Entregar un evento de ciclo de vida al sumidero conectado, si lo hay."""
        if self.event_sink is not None:
            self.event_sink(event_type, payload)

    def check_expiration(self) -> None:
        """Aplicar el vencimiento de la fase actual; el servicio también lo invoca."""
        if self.remaining_time() != 0:
            return
        if self.state == GameState.ROUND:
            if self._submitted_humans() < QUORUM_MIN_HUMANS:
                self.interrupt("quorum_lost")
            else:
                self.interrupt("round_timeout")
        elif self.state == GameState.DISCUSSION:
            self.state = GameState.VOTING
            self._set_deadline()
        elif self.state == GameState.VOTING:
            for alias, player in self._players.items():
                if not player.is_ai and alias not in self._votes:
                    self._votes[alias] = None
            if self._present_humans() < QUORUM_MIN_HUMANS:
                self.interrupt("quorum_lost")
            else:
                self._complete_reveal("voting_timeout")

    def _submitted_humans(self) -> int:
        """Contar humanos distintos que ya respondieron en la ronda actual."""
        submitted = {
            message.alias
            for message in self._messages
            if message.round_number == self.round_number
            and not self._players[message.alias].is_ai
        }
        return len(submitted)

    def _present_humans(self) -> int:
        """Contar humanos que votaron o se abstuvieron explícitamente."""
        present = {
            alias for alias, vote in self._votes.items() if vote is not None
        } | set(self._explicit_abstentions)
        return len(present)

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
            "quorum_lost",
        }
        if reason not in allowed:
            raise ValueError(
                "Usa un código de interrupción conocido, sin datos del proveedor."
            )
        self._interruption_reason = reason
        self.state = GameState.REVEAL
        self._emit_close()

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
        self._set_deadline()
        self._emit("game.started", {"rounds": self.rounds, "max_words": self.max_words})
        self._emit("round.started", {"round_number": 1})

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
                finished = self.round_number
                self.round_number += 1
                self._set_deadline()
                self._emit("round.completed", {"round_number": finished})
                self._emit("round.started", {"round_number": self.round_number})
            else:
                self.state = GameState.DISCUSSION
                self._set_deadline()
                self._emit("round.completed", {"round_number": self.round_number})
        return normalized

    def open_voting(self) -> None:
        """Abrir la votación después de completar todas las rondas."""
        self.check_expiration()
        self._require_state(GameState.DISCUSSION)
        self.state = GameState.VOTING
        self._set_deadline()

    def cast_vote(self, voter_alias: str, suspect_alias: str | None) -> None:
        """Aceptar un voto o una abstención y revelar al completarse la votación.

        Un `suspect_alias` nulo registra una abstención explícita: cuenta como
        acción para cerrar la votación, pero no es un voto escrutable.
        """
        self.check_expiration()
        self._require_state(GameState.VOTING)
        voter = self._player(voter_alias)
        if voter.is_ai:
            raise RuleViolation("En estas reglas provisionales, la IA no vota.")
        if voter_alias in self._votes:
            raise RuleViolation("Ya registraste tu voto.")
        if suspect_alias is not None:
            self._player(suspect_alias)
            if voter_alias == suspect_alias:
                raise RuleViolation("En estas reglas provisionales, no puedes votarte.")
        self._votes[voter_alias] = suspect_alias
        if suspect_alias is None:
            self._explicit_abstentions.add(voter_alias)
        human_count = sum(not player.is_ai for player in self._players.values())
        if len(self._votes) == human_count:
            self._complete_reveal("completed")

    def _complete_reveal(self, reason: str) -> None:
        """Revelar al cerrar la votación y notificar el motivo del cierre."""
        self._close_reason = reason
        self.state = GameState.REVEAL
        self._emit_close()

    def _emit_close(self) -> None:
        """Emitir el cierre de partida exactamente una vez al entrar en revelación."""
        assert (self._interruption_reason is None) != (self._close_reason is None)
        self._emit("game.closed", self._close_payload())

    def _close_payload(self) -> dict:
        """Construir la carga del cierre con motivo, validez y tasa de detección."""
        _, _, tasa_deteccion = self._detection_stats()
        valid_game = self._interruption_reason is None
        return {
            "reason": self._interruption_reason or self._close_reason,
            "valid_game": valid_game,
            "tasa_deteccion": tasa_deteccion if valid_game else None,
            "rounds": self.rounds,
        }

    def public_state(self) -> dict:
        """Ofrecer una vista sin identidades de IA ni votos individuales anticipados."""
        self.check_expiration()
        view = {
            "state": self.state.value,
            "round_number": self.round_number,
            "round_prompt": (
                self.prompts[self.round_number - 1]
                if self.round_number >= 1 and self.round_number <= len(self.prompts)
                else None
            ),
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

    def _detection_stats(self) -> tuple[dict[str, int], dict[str, int], float | None]:
        """Calcular aciertos y conteos sobre votos reales; excluir abstenciones.

        La tasa de detección es `None` cuando no hay votos escrutables, incluso
        en una partida válida, para no fabricar datos inexistentes.
        """
        impostor = next(
            player.alias for player in self._players.values() if player.is_ai
        )
        scorable = {
            alias: suspect
            for alias, suspect in self._votes.items()
            if suspect is not None
        }
        scores = {
            alias: int(suspect == impostor) for alias, suspect in scorable.items()
        }
        vote_counts = dict(Counter(scorable.values()))
        tasa_deteccion = sum(scores.values()) / len(scores) if scores else None
        return scores, vote_counts, tasa_deteccion

    def result(self) -> dict:
        """Revelar etiquetas y calcular aciertos solo después de cerrar la votación."""
        self._require_state(GameState.REVEAL)
        impostor = next(
            player.alias for player in self._players.values() if player.is_ai
        )
        scores, vote_counts, tasa_deteccion = self._detection_stats()
        valid_game = self._interruption_reason is None
        return {
            "state": self.state.value,
            "impostor_alias": impostor,
            "rounds": self.rounds,
            "max_words": self.max_words,
            "votes": dict(self._votes),
            "vote_counts": vote_counts,
            "scores": scores if valid_game else {},
            "valid_game": valid_game,
            "interruption_reason": self._interruption_reason,
            "tasa_deteccion": tasa_deteccion if valid_game else None,
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
