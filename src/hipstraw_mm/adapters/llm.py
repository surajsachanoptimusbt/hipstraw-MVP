"""OpenAI Structured Outputs client (research R1, Constitution VII).

One request per call, with explicit inputs and a strict-schema response. No tools and no multi-turn
loop. A response that fails schema validation is retried once, then LLMSchemaError is raised.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from hipstraw_mm.adapters.replay import ReplayStore
from hipstraw_mm.errors import ConfigError, ExternalServiceError
from hipstraw_mm.logging_setup import EventLog

T = TypeVar("T", bound=BaseModel)


class LLMSchemaError(Exception):
    pass


def _default_client() -> Any:
    from openai import OpenAI

    return OpenAI()


class LLMClient:
    def __init__(
        self,
        model: str | None,
        replay: ReplayStore,
        log: EventLog | None = None,
        client_factory: Callable[[], Any] = _default_client,
    ) -> None:
        self.model = model
        self.replay = replay
        self.log = log
        self._client_factory = client_factory
        self._client: Any | None = None
        self.calls = 0

    def parse(
        self,
        schema: type[T],
        messages: list[dict[str, str]],
        match_key: str,
        prompt_version: str,
        *,
        run_id: str | None = None,
        step: str = "",
        company_record_id: str | None = None,
    ) -> T:
        key = f"{schema.__name__}:{match_key}"
        request = {
            "model": self.model,
            "schema": schema.__name__,
            "promptVersion": prompt_version,
            "messages": messages,
        }
        problem = ""
        for attempt in (1, 2):
            self.calls += 1
            raw = self.replay.call("model", key, request, lambda: self._live(schema, messages))
            self._log(run_id, step, company_record_id, schema, prompt_version, attempt, raw)
            content = raw.get("content")
            if content:
                try:
                    return schema.model_validate_json(content)
                except ValidationError as exc:
                    problem = f"schema validation failed: {exc.error_count()} errors"
            else:
                problem = raw.get("error") or raw.get("refusal") or "empty response"
        raise LLMSchemaError(f"{schema.__name__} for {match_key!r}: {problem}")

    def _live(self, schema: type[BaseModel], messages: list[dict[str, str]]) -> dict[str, Any]:
        import openai

        if not self.model:
            raise ConfigError("LLM_MODEL is not set")
        if self._client is None:
            self._client = self._client_factory()
        try:
            completion = self._client.chat.completions.parse(
                model=self.model, messages=messages, response_format=schema
            )
        except (ValidationError, openai.LengthFinishReasonError, openai.ContentFilterFinishReasonError) as exc:
            # Recorded as a failed response, so replay reproduces the same retry path.
            return {"content": None, "refusal": None, "error": f"{type(exc).__name__}", "model": self.model}
        except openai.OpenAIError as exc:
            raise ExternalServiceError(f"model call failed: {type(exc).__name__}: {exc}") from exc
        choice = completion.choices[0]
        return {
            "content": choice.message.content,
            "refusal": choice.message.refusal,
            "finishReason": choice.finish_reason,
            "model": completion.model,
        }

    def _log(
        self,
        run_id: str | None,
        step: str,
        company_record_id: str | None,
        schema: type[BaseModel],
        prompt_version: str,
        attempt: int,
        raw: dict[str, Any],
    ) -> None:
        if self.log is None:
            return
        self.log.event(
            "model_call",
            run_id=run_id,
            step=step,
            company_record_id=company_record_id,
            schema=schema.__name__,
            promptVersion=prompt_version,
            model=raw.get("model") or self.model,
            attempt=attempt,
            ok=bool(raw.get("content")),
        )
