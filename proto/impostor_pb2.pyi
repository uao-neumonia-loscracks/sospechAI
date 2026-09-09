from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class UtteranceRequest(_message.Message):
    __slots__ = ("room_id", "persona_id", "prompt", "history", "config")
    ROOM_ID_FIELD_NUMBER: _ClassVar[int]
    PERSONA_ID_FIELD_NUMBER: _ClassVar[int]
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    room_id: str
    persona_id: str
    prompt: str
    history: _containers.RepeatedCompositeFieldContainer[Message]
    config: GenerationConfig
    def __init__(self, room_id: _Optional[str] = ..., persona_id: _Optional[str] = ..., prompt: _Optional[str] = ..., history: _Optional[_Iterable[_Union[Message, _Mapping]]] = ..., config: _Optional[_Union[GenerationConfig, _Mapping]] = ...) -> None: ...

class Message(_message.Message):
    __slots__ = ("alias", "text", "ts_ms")
    ALIAS_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    TS_MS_FIELD_NUMBER: _ClassVar[int]
    alias: str
    text: str
    ts_ms: int
    def __init__(self, alias: _Optional[str] = ..., text: _Optional[str] = ..., ts_ms: _Optional[int] = ...) -> None: ...

class GenerationConfig(_message.Message):
    __slots__ = ("temperature", "top_p", "max_words", "system_prompt_version", "engine_backend", "model_id")
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    TOP_P_FIELD_NUMBER: _ClassVar[int]
    MAX_WORDS_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_PROMPT_VERSION_FIELD_NUMBER: _ClassVar[int]
    ENGINE_BACKEND_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    temperature: float
    top_p: float
    max_words: int
    system_prompt_version: str
    engine_backend: str
    model_id: str
    def __init__(self, temperature: _Optional[float] = ..., top_p: _Optional[float] = ..., max_words: _Optional[int] = ..., system_prompt_version: _Optional[str] = ..., engine_backend: _Optional[str] = ..., model_id: _Optional[str] = ...) -> None: ...

class UtteranceChunk(_message.Message):
    __slots__ = ("text_delta", "is_final", "token_index")
    TEXT_DELTA_FIELD_NUMBER: _ClassVar[int]
    IS_FINAL_FIELD_NUMBER: _ClassVar[int]
    TOKEN_INDEX_FIELD_NUMBER: _ClassVar[int]
    text_delta: str
    is_final: bool
    token_index: int
    def __init__(self, text_delta: _Optional[str] = ..., is_final: _Optional[bool] = ..., token_index: _Optional[int] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = ("healthy", "model_id", "detail")
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    healthy: bool
    model_id: str
    detail: str
    def __init__(self, healthy: _Optional[bool] = ..., model_id: _Optional[str] = ..., detail: _Optional[str] = ...) -> None: ...
