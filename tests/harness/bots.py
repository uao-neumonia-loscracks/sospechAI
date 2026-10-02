"""Arnés de jugadores bot: partidas completas sin convocar personas (A10).

Los bots son deterministas: responden desde un banco fijo y votan con una
estrategia reproducible. El impostor pasa por el camino real del orquestador
(`apply_ai_turn` -> `EngineClient` -> contrato gRPC). La única fuente de
variación del sistema queda detrás de ese contrato, en el engine.
"""

import random
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from proto import impostor_pb2 as pb
from src.orchestrator.game import Game

VoteMode = Literal["fixed", "random"]

PROMPTS = (
    "Si se va la luz justo antes de entregar un trabajo, ¿qué harías?",
    "¿Qué comida escogerías después de una clase larga?",
    "¿Qué es lo primero que haces al llegar a la casa?",
)

RESPONSE_BANK = (
    (
        "Compartiría internet desde el celular y le avisaría al profe.",
        "Me iría a una cafetería a terminarlo allá.",
        "Revisaría la batería del portátil y buscaría otra conexión.",
        "Le escribiría al grupo para ver quién lo puede subir.",
        "Uy, me tocaría rogarle al profe por una prórroga.",
        "Lo mandaría desde el celular aunque quede feo.",
    ),
    (
        "Una arepa con queso, tengo hambre desde hace rato.",
        "Arroz con pollo y un juguito bien frío.",
        "Una empanada con ají y una gaseosa.",
        "Algo caliente, un caldito de papa.",
        "Una hamburguesa de la esquina, sin pensarlo.",
        "Pandebono con avena, lo de siempre.",
    ),
    (
        "Me quito los zapatos y me tiro a la cama.",
        "Saludo a mi mamá y busco qué comer.",
        "Pongo a cargar el celular porque siempre llega muerto.",
        "Me baño, con este calor no se puede otra cosa.",
        "Saco al perro, que me está esperando.",
        "Prendo el televisor mientras me cambio.",
    ),
)

IMPOSTOR_BANK = (
    "Pues yo le escribiría al profe de una y ya.",
    "Yo me comería una bandeja paisa completa, parce.",
    "Tomo agua y me acuesto un rato.",
)

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct:featherless-ai"


@dataclass(frozen=True)
class HarnessConfig:
    """Parámetros de una partida simulada; todos explícitos y reproducibles."""

    bots: int = 5
    rounds: int = 2
    max_words: int = 15
    round_timeout: float = 20.0
    response_delay: float = 2.0
    vote_mode: VoteMode = "fixed"
    seed: int = 0
    prompt_version: str = "v2"
    persona_id: str = "p1"
    model_id: str = DEFAULT_MODEL_ID

    def __post_init__(self) -> None:
        """Rechazar configuraciones que no pueden producir una partida válida."""
        if self.bots < 2:
            raise ValueError("Se necesitan al menos dos bots humanos.")
        if not 1 <= self.rounds <= len(PROMPTS):
            raise ValueError(f"Las rondas deben estar entre 1 y {len(PROMPTS)}.")
        if self.response_delay < 0:
            raise ValueError("La demora de respuesta no puede ser negativa.")
        if self.vote_mode not in ("fixed", "random"):
            raise ValueError("vote_mode debe ser 'fixed' o 'random'.")


@dataclass
class SimulatedClock:
    """Reloj controlado: la ventana de ronda se prueba sin pausas reales."""

    now: float = 0.0

    def __call__(self) -> float:
        """Devolver el instante simulado actual."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Avanzar el tiempo simulado."""
        self.now += seconds


class ScriptedEngineStub:
    """Engine doble determinista que respeta el contrato de streaming.

    Emite la respuesta palabra por palabra y cierra con un chunk final vacío
    con `is_final=True`, igual que el engine real. Registra cada petición.
    """

    def __init__(self, responses: tuple[str, ...] = IMPOSTOR_BANK) -> None:
        """Guardar el banco de respuestas del impostor."""
        self.responses = responses
        self.requests: list[pb.UtteranceRequest] = []

    def GenerateUtterance(
        self, request: pb.UtteranceRequest, *, timeout: float
    ) -> Iterator[pb.UtteranceChunk]:
        """Registrar la petición y devolver el stream de la respuesta que toca."""
        text = self.responses[len(self.requests) % len(self.responses)]
        self.requests.append(request)
        return self._stream(text)

    @staticmethod
    def _stream(text: str) -> Iterator[pb.UtteranceChunk]:
        """Partir el texto en deltas y cerrar con el final vacío del contrato."""
        for index, word in enumerate(text.split()):
            delta = word if index == 0 else f" {word}"
            yield pb.UtteranceChunk(text_delta=delta, token_index=index)
        yield pb.UtteranceChunk(is_final=True)


def bot_reply(bot_index: int, round_index: int) -> str:
    """Respuesta fija del bot para una ronda; el banco se recorre en ciclo."""
    bank = RESPONSE_BANK[round_index % len(RESPONSE_BANK)]
    return bank[bot_index % len(bank)]


def choose_votes(
    voters: list[str], candidates: list[str], mode: VoteMode, seed: int
) -> dict[str, str]:
    """Decidir el voto de cada bot sin conocer quién es el impostor.

    `fixed`: cada bot vota al siguiente participante de la lista, en ciclo.
    `random`: elección al azar entre los demás, con semilla reproducible.
    """
    rng = random.Random(seed)
    votes: dict[str, str] = {}
    for voter in voters:
        others = [alias for alias in candidates if alias != voter]
        if mode == "fixed":
            position = candidates.index(voter)
            votes[voter] = candidates[(position + 1) % len(candidates)]
        else:
            votes[voter] = rng.choice(others)
    return votes


def build_request(
    config: HarnessConfig, prompt: str, game: Game
) -> pb.UtteranceRequest:
    """Armar la petición del impostor con la pregunta y el historial público."""
    history = [
        pb.Message(alias=message["alias"], text=message["text"])
        for message in game.public_state()["messages"]
    ]
    return pb.UtteranceRequest(
        room_id="arnes-bots",
        persona_id=config.persona_id,
        prompt=prompt,
        history=history,
        config=pb.GenerationConfig(
            temperature=0.9,
            top_p=0.9,
            max_words=config.max_words,
            system_prompt_version=config.prompt_version,
            engine_backend="hf-router",
            model_id=config.model_id,
        ),
    )
