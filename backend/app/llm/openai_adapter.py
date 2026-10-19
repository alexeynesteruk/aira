"""Bounded OpenAI Responses transport with explicit candidate and failure records."""

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)
from openai.types.chat import ChatCompletion
from openai.types.responses import Response
from pydantic import BaseModel, ValidationError

from app.schemas import ErrorCode, OperationalError, RunPhase

from .config import OpenAISettings


@dataclass(frozen=True)
class ModelMetrics:
    attempts: int
    duration_ms: float
    input_tokens: int | None
    output_tokens: int | None
    request_ids: tuple[str, ...]
    response_ids: tuple[str, ...]


@dataclass(frozen=True)
class ModelCandidate[T: BaseModel]:
    value: T
    model: str
    prompt_version: str
    metrics: ModelMetrics


class ModelFailure(Exception):
    def __init__(self, error: OperationalError, metrics: ModelMetrics):
        super().__init__(error.message)
        self.error = error
        self.metrics = metrics


def strict_output_schema(output_type: type[BaseModel]) -> dict[str, Any]:
    """Adapt only wire shape. Domain invariants still run after model output."""
    schema = output_type.model_json_schema()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if "const" in node:
                node["enum"] = [node.pop("const")]
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


def transport_timeout(settings: OpenAISettings) -> httpx.Timeout:
    """Bound a stuck send separately from a slow model response.

    A full request budget on the write lets a proxy that stops reading the body
    leave the assessment in progress for the entire generation deadline.
    """
    budget = settings.request_timeout_seconds
    handshake = min(60.0, budget)
    return httpx.Timeout(connect=handshake, read=budget, write=handshake, pool=handshake)


def _extract_json_payload(raw: str) -> str:
    """Extract valid JSON from raw model output that may contain markdown fences or commentary."""
    text = raw.strip()
    if not text:
        return text
    fence_match = re.search(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    inner_fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if inner_fence:
        candidate = inner_fence.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1].strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    return text


class OpenAIAdapter:
    def __init__(self, settings: OpenAISettings, *, client: AsyncOpenAI | None = None):
        self.settings = settings
        # One retry owner. Never inherit an author's gateway or SDK retry multiplier.
        self._deadline = transport_timeout(settings)
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            max_retries=0,
            timeout=self._deadline,
        )
        if self._client.max_retries != 0:
            raise ValueError("The injected SDK client must disable SDK retries")
        self._use_max_tokens: bool = False
        self._use_json_object: bool = False
        self._no_response_format: bool = False

    async def close(self) -> None:
        await self._client.close()

    async def _call_chat_completions(
        self,
        *,
        instructions: str,
        source_text: str,
        output_type: type[BaseModel],
    ) -> Any:
        while True:
            extra_instructions = ""
            fmt: dict[str, Any] | None = None
            if self._no_response_format:
                extra_instructions = (
                    f"\n\nYou must respond with only a valid JSON object matching this schema:\n"
                    f"{json.dumps(strict_output_schema(output_type), indent=2)}"
                )
                fmt = None
            elif self._use_json_object:
                extra_instructions = (
                    f"\n\nYou must respond with a valid JSON object matching this schema:\n"
                    f"{json.dumps(strict_output_schema(output_type), indent=2)}"
                )
                fmt = {"type": "json_object"}
            else:
                fmt = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_type.__name__,
                        "schema": strict_output_schema(output_type),
                        "strict": True,
                    },
                }

            token_kwargs: dict[str, Any]
            if self._use_max_tokens:
                token_kwargs = {"max_tokens": self.settings.max_output_tokens}
            else:
                token_kwargs = {"max_completion_tokens": self.settings.max_output_tokens}

            extra_body = (
                {"timeout": self.settings.request_timeout_seconds}
                if self.settings.backend == "litellm"
                else None
            )

            kwargs: dict[str, Any] = {
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": f"{instructions}{extra_instructions}"},
                    {"role": "user", "content": source_text},
                ],
                "timeout": self._deadline,
                "extra_body": extra_body,
                **token_kwargs,
            }
            if fmt is not None:
                kwargs["response_format"] = fmt

            try:
                return await self._client.chat.completions.create(**kwargs)
            except APIStatusError as exc:
                if exc.status_code == 400:
                    err_text = f"{exc.message} {getattr(exc, 'body', '')}".lower()
                    if "max_completion_tokens" in err_text and not self._use_max_tokens:
                        self._use_max_tokens = True
                        continue
                    if (
                        (
                            "json_schema" in err_text
                            or "response_format" in err_text
                            or "schema" in err_text
                        )
                        and not self._use_json_object
                        and not self._no_response_format
                    ):
                        self._use_json_object = True
                        continue
                    if (
                        ("response_format" in err_text or "format" in err_text)
                        and self._use_json_object
                        and not self._no_response_format
                    ):
                        self._no_response_format = True
                        continue
                raise

    async def interpret[T: BaseModel](
        self,
        *,
        phase: RunPhase,
        instructions: str,
        source_text: str,
        output_type: type[T],
        prompt_version: str,
    ) -> ModelCandidate[T]:
        started = time.monotonic()
        attempts = 0
        input_tokens: int | None = None
        output_tokens: int | None = None
        request_ids: list[str] = []
        response_ids: list[str] = []

        def metrics() -> ModelMetrics:
            return ModelMetrics(
                attempts=attempts,
                duration_ms=(time.monotonic() - started) * 1000,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_ids=tuple(request_ids),
                response_ids=tuple(response_ids),
            )

        def failure(
            code: ErrorCode,
            message: str,
            action: str,
            retryable: bool = False,
            provider_code: str | None = None,
        ) -> ModelFailure:
            return ModelFailure(
                OperationalError(
                    code=code,
                    message=message,
                    retryable=retryable,
                    action=action,
                    stage=phase,
                    provider_code=provider_code,
                ),
                metrics(),
            )

        try:
            async with asyncio.timeout(self.settings.stage_timeout_seconds):
                for attempt in range(1, self.settings.max_attempts + 1):
                    attempts = attempt
                    try:
                        response: Any
                        if self.settings.transport == "chat_completions":
                            response = await self._call_chat_completions(
                                instructions=instructions,
                                source_text=source_text,
                                output_type=output_type,
                            )
                        else:
                            response = await self._client.responses.create(
                                model=self.settings.model,
                                instructions=instructions,
                                input=source_text,
                                text={
                                    "format": {
                                        "type": "json_schema",
                                        "name": output_type.__name__,
                                        "schema": strict_output_schema(output_type),
                                        "strict": True,
                                    }
                                },
                                max_output_tokens=self.settings.max_output_tokens,
                                store=False,
                                truncation="disabled",
                                timeout=self._deadline,
                            )
                    except (APIConnectionError, APIStatusError) as exc:
                        code, message, action, retryable = _classify_error(exc)
                        request_id = getattr(exc, "request_id", None)
                        if isinstance(request_id, str):
                            request_ids.append(request_id)
                        if retryable and attempt < self.settings.max_attempts:
                            await asyncio.sleep(_retry_delay(exc, attempt))
                            continue
                        raise failure(
                            code, message, action, retryable, _provider_code(exc)
                        ) from None
                    except (json.JSONDecodeError, APIResponseValidationError):
                        raise failure(
                            ErrorCode.INVALID_OUTPUT,
                            "The provider returned an invalid response envelope.",
                            "Check the provider response before retrying.",
                        ) from None

                    if self.settings.transport == "chat_completions":
                        if not isinstance(response, ChatCompletion):
                            raise failure(
                                ErrorCode.INVALID_OUTPUT,
                                "The provider returned an invalid response envelope.",
                                "Check the provider response before retrying.",
                            )
                        request_id = response._request_id
                        if request_id:
                            request_ids.append(request_id)
                        try:
                            response = ChatCompletion.model_validate(response.to_dict())
                        except ValidationError:
                            raise failure(
                                ErrorCode.INVALID_OUTPUT,
                                "The provider returned an invalid response envelope.",
                                "Check the provider response before retrying.",
                            ) from None
                        response_ids.append(response.id)
                        if response.usage is not None:
                            input_tokens = response.usage.prompt_tokens
                            output_tokens = response.usage.completion_tokens
                        choice = response.choices[0] if response.choices else None
                        if choice is None or choice.finish_reason != "stop":
                            raise failure(
                                ErrorCode.INVALID_OUTPUT,
                                "The model did not finish a complete response.",
                                "Review the output budget and retry the assessment.",
                            )
                        if choice.message.refusal is not None:
                            raise failure(
                                ErrorCode.REFUSED,
                                "The model declined this request.",
                                "Review the source content and request scope.",
                            )
                        if not isinstance(choice.message.content, str):
                            raise failure(
                                ErrorCode.INVALID_OUTPUT,
                                "The model did not finish a complete response.",
                                "Review the output budget and retry the assessment.",
                            )
                        output_text = choice.message.content
                    else:
                        if not isinstance(response, Response):
                            raise failure(
                                ErrorCode.INVALID_OUTPUT,
                                "The provider returned an invalid response envelope.",
                                "Check the provider response before retrying.",
                            )
                        request_id = response._request_id
                        if request_id:
                            request_ids.append(request_id)
                        try:
                            response = Response.model_validate(response.to_dict())
                        except ValidationError:
                            raise failure(
                                ErrorCode.INVALID_OUTPUT,
                                "The provider returned an invalid response envelope.",
                                "Check the provider response before retrying.",
                            ) from None
                        response_ids.append(response.id)
                        if response.usage is not None:
                            input_tokens = response.usage.input_tokens
                            output_tokens = response.usage.output_tokens
                        if response.status != "completed" or response.error is not None:
                            raise failure(
                                ErrorCode.INVALID_OUTPUT,
                                "The model did not finish a complete response.",
                                "Review the output budget and retry the assessment.",
                            )
                        for item in response.output:
                            if item.type == "message" and item.status != "completed":
                                raise failure(
                                    ErrorCode.INVALID_OUTPUT,
                                    "The model returned an incomplete output message.",
                                    "Review the output budget and retry the assessment.",
                                )
                            if item.type == "message" and any(
                                part.type == "refusal" for part in item.content
                            ):
                                raise failure(
                                    ErrorCode.REFUSED,
                                    "The model declined this request.",
                                    "Review the source content and request scope.",
                                )
                        output_text = response.output_text
                    try:
                        clean_payload = _extract_json_payload(output_text)
                        candidate = output_type.model_validate_json(clean_payload)
                    except (ValidationError, ValueError):
                        raise failure(
                            ErrorCode.INVALID_OUTPUT,
                            "The model returned an invalid structured response.",
                            "Review the schema and validation diagnostics before retrying.",
                        ) from None
                    return ModelCandidate(candidate, response.model, prompt_version, metrics())
        except TimeoutError:
            raise failure(
                ErrorCode.TIMEOUT,
                "The model stage exceeded its deadline.",
                "Retry the assessment after checking provider availability.",
                True,
            ) from None
        raise AssertionError("Validated attempt count must permit at least one call")


def _classify_error(exc: APIConnectionError | APIStatusError) -> tuple[ErrorCode, str, str, bool]:
    if isinstance(exc, APITimeoutError):
        return (ErrorCode.TIMEOUT, "The model request timed out.", "Retry the assessment.", True)
    if isinstance(exc, APIConnectionError):
        return (
            ErrorCode.INTERNAL_ERROR,
            "Could not reach the model provider.",
            "Check the network connection and retry.",
            True,
        )
    if exc.status_code in (401, 403):
        return (
            ErrorCode.ACCESS_DENIED,
            "The provider rejected the configured access.",
            "Check the server API key and model access.",
            False,
        )
    if exc.status_code == 429:
        # Quota exhaustion needs intervention, not automatic retry.
        quota = _provider_code(exc) == "insufficient_quota"
        return (
            ErrorCode.THROTTLED,
            "The provider's usage limit was reached.",
            (
                "Enable API project quota or configure a key with available quota."
                if quota
                else "Check the account quota or retry after the rate limit clears."
            ),
            not quota,
        )
    if exc.status_code in (408, 409) or exc.status_code >= 500:
        return (
            ErrorCode.INTERNAL_ERROR,
            "The provider could not complete the request.",
            "Retry after the provider recovers.",
            True,
        )
    return (
        ErrorCode.INVALID_OUTPUT,
        "The provider rejected the model or request configuration.",
        "Check model access and structured-output compatibility.",
        False,
    )


def _provider_code(exc: APIConnectionError | APIStatusError) -> str | None:
    if not isinstance(exc, APIStatusError):
        return None
    # Do not echo arbitrary provider payloads into logs or exported diagnostics.
    known = {
        "insufficient_quota",
        "rate_limit_exceeded",
        "invalid_api_key",
        "model_not_found",
        "invalid_json_schema",
        "unsupported_value",
        "context_length_exceeded",
        "server_error",
    }
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body)
    error = error if isinstance(error, dict) else {}
    # The provider can report exhausted quota in `type` with a null/different code.
    # This occurred in the live preflight; do not retry an account billing failure.
    for field in ("type", "code"):
        if error.get(field) == "insufficient_quota":
            return "insufficient_quota"
    code = error.get("code")
    return code if isinstance(code, str) and code in known else f"http_{exc.status_code}"


def _retry_delay(exc: APIConnectionError | APIStatusError, attempt: int) -> float:
    if isinstance(exc, APIStatusError):
        try:
            seconds = float(exc.response.headers.get("retry-after", ""))
            if 0 <= seconds <= 5:
                return seconds
        except ValueError:
            pass
    return float(random.uniform(0.1, 0.3) * 2 ** (attempt - 1))
