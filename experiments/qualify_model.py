"""Fixed model qualification. Default execution is strictly offline."""

import argparse
import json
import math
import os
from pathlib import Path
import time
import unicodedata
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/model.yaml"
RESULT_PATH = ROOT / "results/model-qualification/qualification.json"
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "meta-llama/llama-3.1-8b-instruct"
PROVIDER = "coreweave/bf16"
LOGICAL_IDS = ("E1", "E2", "M1", "M2", "M3", "A1", "A2", "E2E-E", "E2E-M", "E2E-A")


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    entity: str
    attribute: str
    value: str


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    memories: list[MemoryItem] = Field(min_length=1, max_length=1)


class MaintenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation: Literal["add", "update", "noop"]
    target_id: str | None = None

    @model_validator(mode="after")
    def check_target(self):
        if self.operation == "update":
            if self.target_id is None or not self.target_id.strip():
                raise ValueError("update requires a target_id")
        elif self.target_id is not None:
            raise ValueError("add and noop require a null target_id")
        return self


class AnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str

    @field_validator("answer")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("answer must be non-empty")
        return value


def load_config(path=CONFIG_PATH):
    config = yaml.safe_load(Path(path).read_text())
    if config["model"] != {"id": MODEL} or config["provider"] != {
        "gateway": "openrouter", "upstream": PROVIDER,
        "allow_fallbacks": False, "require_parameters": True,
    }:
        raise ValueError("Unexpected model or provider configuration")
    if config["provider"]["allow_fallbacks"] is not False or config["provider"]["require_parameters"] is not True:
        raise ValueError("Provider routing flags must be booleans")
    generation, transport = config["generation"], config["transport"]
    for key, upper in (("temperature", 2), ("top_p", 1)):
        value = generation[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= upper:
            raise ValueError(f"Invalid {key}")
    if type(generation["max_output_tokens"]) is not int or generation["max_output_tokens"] <= 0:
        raise ValueError("Invalid output token limit")
    retries = transport["max_retries"]
    if type(retries) is not int or retries < 0 or len(transport["retry_backoff_seconds"]) != retries:
        raise ValueError("Invalid retry configuration")
    for value in [transport["timeout_seconds"], *transport["retry_backoff_seconds"]]:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid transport timing")
    if transport["timeout_seconds"] == 0:
        raise ValueError("Timeout must be positive")
    if any(type(code) is not int or not 400 <= code <= 599 for code in transport["retry_status_codes"]):
        raise ValueError("Invalid retry status codes")
    return config


def memory(value):
    return {"entity": "Mira", "attribute": "locker_color", "value": value}


def active_memory(value):
    return [{"id": "mem-1", **memory(value)}]


EXTRACTION_PROMPT = (
    'Extract only current entity-attribute-value propositions. Do not return superseded '
    'historical values as current. Return JSON: {"memories":[{"entity":"...",'
    '"attribute":"...","value":"..."}]}. Use snake_case attribute names.'
)
MAINTENANCE_PROMPT = (
    'Add when no entity-attribute memory exists. Update when the same entity-attribute '
    'exists with a different current value. Noop when the same entity-attribute already '
    'has the candidate current value. Return JSON with "operation" ("add", "update", '
    'or "noop") and "target_id" (the existing memory ID for update, otherwise null).'
)
ANSWER_PROMPT = (
    'Answer using supplied active memory only. Return the canonical value in JSON: '
    '{"answer":"..."}.'
)


def request_body(config, logical_id, *, candidate=None, active=None):
    if logical_id not in LOGICAL_IDS:
        raise ValueError("Unknown logical ID")
    if logical_id in ("E1", "E2", "E2E-E"):
        prompt = EXTRACTION_PROMPT
        data = {"text": "Mira's locker is cobalt." if logical_id == "E1" else
                "Mira changed her locker color from amber to cobalt."}
    elif logical_id in ("M1", "M2", "M3", "E2E-M"):
        prompt = MAINTENANCE_PROMPT
        if logical_id == "E2E-M":
            if candidate is None or active is None:
                raise ValueError("End-to-end maintenance requires extracted candidate and state")
        else:
            candidate = memory("cobalt")
            active = [] if logical_id == "M1" else active_memory("amber" if logical_id == "M2" else "cobalt")
        data = {"active_memory": active, "candidate": candidate}
    else:
        prompt = ANSWER_PROMPT
        if logical_id == "E2E-A" and active is None:
            raise ValueError("End-to-end answering requires applied state")
        data = {"active_memory": active if logical_id == "E2E-A" else active_memory("cobalt"),
                "question": "What color is Mira's locker?" if logical_id == "A1" else
                "What color is Mira's locker now?"}
        if logical_id == "A2":
            data["superseded_historical_memory"] = [memory("amber")]
    return {
        "model": config["model"]["id"],
        "provider": {"order": [config["provider"]["upstream"]],
                     "allow_fallbacks": config["provider"]["allow_fallbacks"],
                     "require_parameters": config["provider"]["require_parameters"]},
        "temperature": config["generation"]["temperature"],
        "top_p": config["generation"]["top_p"],
        "max_tokens": config["generation"]["max_output_tokens"],
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": prompt},
                     {"role": "user", "content": json.dumps(data)}],
    }


def schema_for(logical_id):
    if logical_id in ("E1", "E2", "E2E-E"):
        return ExtractionResponse
    if logical_id in ("M1", "M2", "M3", "E2E-M"):
        return MaintenanceResponse
    return AnswerResponse


def normalize(value):
    return unicodedata.normalize("NFC", value.strip()).casefold()


def expected_output(logical_id):
    if schema_for(logical_id) is ExtractionResponse:
        return {"memories": [memory("cobalt")]}
    if schema_for(logical_id) is MaintenanceResponse:
        operation = {"M1": "add", "M2": "update", "M3": "noop", "E2E-M": "update"}[logical_id]
        return {"operation": operation, "target_id": "mem-1" if operation == "update" else None}
    return {"answer": "cobalt"}


def evaluate(logical_id, output):
    expected = expected_output(logical_id)
    if isinstance(output, ExtractionResponse):
        return all(normalize(value) == normalize(expected["memories"][0][key])
                   for key, value in output.memories[0].model_dump().items())
    if isinstance(output, MaintenanceResponse):
        return output.model_dump() == expected
    return normalize(output.answer) == normalize(expected["answer"])


def apply_update(active, candidate, decision):
    """Apply only the validated end-to-end update; never execute model-supplied code."""
    if decision.operation != "update":
        raise ValueError("End-to-end requires update")
    matches = [item for item in active if item["id"] == decision.target_id]
    if len(matches) != 1 or any(normalize(matches[0][key]) != normalize(getattr(candidate, key))
                                for key in ("entity", "attribute")):
        raise ValueError("Invalid update target")
    return [{**item, "value": candidate.value} if item["id"] == decision.target_id else dict(item)
            for item in active]


def retryable(config, *, status=None, error=None):
    return status in config["transport"]["retry_status_codes"] or isinstance(
        error, (httpx.NetworkError, httpx.ReadTimeout, httpx.WriteTimeout,
                httpx.ConnectTimeout, httpx.PoolTimeout))


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def empty_result(logical_id):
    return {"logical_id": logical_id, "request_status": "blocked", "attempts": [],
            "raw_assistant_content": None, "parsed_output": None,
            "usage": None, "latency_seconds": None,
            "parse_status": "not_run", "schema_status": "not_run", "evaluation_status": "not_run",
            "expected": expected_output(logical_id), "routing_ok": False, "accounting_ok": False}


def routing_ok(body, metadata, returned_model):
    # Verify only observed provider identity; do not infer an unexposed endpoint variant.
    routing = body.get("provider")
    if (body.get("model") != MODEL or returned_model != body.get("model")
            or not isinstance(routing, dict) or routing.get("order") != [PROVIDER]
            or routing.get("allow_fallbacks") is not False
            or routing.get("require_parameters") is not True):
        return False
    if not isinstance(metadata, dict) or not isinstance(metadata.get("endpoints"), dict):
        return False
    available = metadata["endpoints"].get("available")
    if not isinstance(available, list):
        return False
    selected = []
    for endpoint in available:
        if (not isinstance(endpoint, dict) or type(endpoint.get("selected")) is not bool
                or not isinstance(endpoint.get("provider"), str) or not endpoint["provider"].strip()):
            return False
        if endpoint["selected"]:
            selected.append(endpoint["provider"])
    return bool(selected) and all(normalize(provider) == "coreweave" for provider in selected)


def call_model(client, config, logical_id, body):
    result = empty_result(logical_id)
    result["request"] = body
    result["request_status"] = "failed"
    start = time.monotonic()
    for number in range(config["transport"]["max_retries"] + 1):
        attempt = {"attempt": number + 1, "started_at": timestamp(), "http_status": None,
                   "error_type": None, "requested_model": body["model"],
                   "requested_provider_endpoint": PROVIDER, "returned_model": None,
                   "openrouter_metadata": None, "request_id": None, "response_id": None,
                   "service_tier": None,
                   "usage": None}
        result["attempts"].append(attempt)
        attempt_start = time.monotonic()
        response = None
        envelope = None
        error = None
        try:
            response = client.post(URL, json=body, headers={"X-OpenRouter-Metadata": "enabled"},
                                   timeout=config["transport"]["timeout_seconds"])
            attempt["http_status"] = response.status_code
            attempt["request_id"] = response.headers.get("x-request-id")
            try:
                envelope = response.json()
            except ValueError:
                pass
            if isinstance(envelope, dict):
                attempt.update(returned_model=envelope.get("model"),
                               openrouter_metadata=envelope.get("openrouter_metadata"),
                               response_id=envelope.get("id"),
                               service_tier=envelope.get("service_tier"))
                attempt["usage"] = envelope.get("usage")
        except httpx.RequestError as exc:
            error = exc
            attempt["error_type"] = type(exc).__name__
        attempt["latency_seconds"] = time.monotonic() - attempt_start
        again = retryable(config, status=attempt["http_status"], error=error)
        attempt["will_retry"] = again and number < config["transport"]["max_retries"]
        if attempt["will_retry"]:
            time.sleep(config["transport"]["retry_backoff_seconds"][number])
            continue
        if response is None or not response.is_success:
            break
        result["request_status"] = "success"
        if not isinstance(envelope, dict):
            result["parse_status"] = "failed"
            break
        usage = envelope.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        details = usage.get("prompt_tokens_details")
        details = details if isinstance(details, dict) else {}
        attempt["usage"] = {key: usage.get(key) for key in
                            ("prompt_tokens", "completion_tokens", "total_tokens", "cost")}
        attempt["usage"]["cached_tokens"] = details.get("cached_tokens")
        result["usage"] = attempt["usage"]
        result["accounting_ok"] = all(type(usage.get(key)) is int and usage[key] >= 0
                                       for key in ("prompt_tokens", "completion_tokens"))
        result["routing_ok"] = routing_ok(body, attempt["openrouter_metadata"], attempt["returned_model"])
        try:
            content = envelope["choices"][0]["message"]["content"]
            result["raw_assistant_content"] = content
            if not isinstance(content, str):
                raise ValueError("Missing text content")
            parsed = json.loads(content)  # Exactly one assistant-content parse; no repair.
        except (KeyError, IndexError, TypeError, ValueError):
            result["parse_status"] = "failed"
            break
        result["parse_status"] = "passed"
        result["parsed_output"] = parsed
        try:
            output = schema_for(logical_id).model_validate(parsed)
        except ValidationError:
            result["schema_status"] = "failed"
            break
        result["schema_status"] = "passed"
        result["evaluation_status"] = "passed" if evaluate(logical_id, output) else "failed"
        break
    result["latency_seconds"] = time.monotonic() - start
    return result


def final_status(calls, local_update_applied):
    complete = [call["logical_id"] for call in calls] == list(LOGICAL_IDS)
    passed = all(call["request_status"] == "success" and call["parse_status"] == "passed"
                 and call["schema_status"] == "passed" and call["evaluation_status"] == "passed"
                 and call["routing_ok"] and call["accounting_ok"] for call in calls)
    return "QUALIFIED" if complete and passed and local_update_applied else "NOT_QUALIFIED"


def run_qualification(client, config):
    result = {"started_at": timestamp(), "model_configuration": config["model"],
              "provider_configuration": config["provider"], "generation": config["generation"],
              "transport": config["transport"], "fixture_identifiers": list(LOGICAL_IDS),
              "logical_calls": [], "local_update_applied": False}
    calls = result["logical_calls"]
    for logical_id in LOGICAL_IDS[:8]:
        calls.append(call_model(client, config, logical_id, request_body(config, logical_id)))
    active = active_memory("amber")
    extraction = calls[-1]
    if extraction["evaluation_status"] == "passed":
        candidate = ExtractionResponse.model_validate(extraction["parsed_output"]).memories[0]
        calls.append(call_model(client, config, "E2E-M", request_body(
            config, "E2E-M", candidate=candidate.model_dump(), active=active)))
        if calls[-1]["evaluation_status"] == "passed":
            decision = MaintenanceResponse.model_validate(calls[-1]["parsed_output"])
            active = apply_update(active, candidate, decision)
            result["local_update_applied"] = True
            calls.append(call_model(client, config, "E2E-A", request_body(config, "E2E-A", active=active)))
        else:
            calls.append(empty_result("E2E-A"))
    else:
        calls.extend([empty_result("E2E-M"), empty_result("E2E-A")])
    result["final_active_memory"] = active
    result["ended_at"] = timestamp()
    result["final_status"] = final_status(calls, result["local_update_applied"])
    return result


def serialize_result(result):
    # Redact even a secret echoed by a server in content, metadata, or JSON keys.
    secret = os.environ.get("OPENROUTER_API_KEY")

    def scrub(value):
        if isinstance(value, str):
            return value.replace(secret, "[REDACTED]") if secret else value
        if isinstance(value, dict):
            return {scrub(key): scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return json.dumps(scrub(result), indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def preflight(config):
    if len(LOGICAL_IDS) != 10 or len(set(LOGICAL_IDS)) != 10:
        raise ValueError("Exactly ten unique calls required")
    for logical_id in LOGICAL_IDS:
        output = schema_for(logical_id).model_validate(expected_output(logical_id))
        if not evaluate(logical_id, output):
            raise ValueError("Invalid fixture schema")
    for logical_id in LOGICAL_IDS[:8]:
        body = request_body(config, logical_id)
        if not routing_ok(body, {"endpoints": {"available": [
                {"provider": "CoreWeave", "selected": True}]}}, MODEL):
            raise ValueError("Invalid routing request")
    return "READY_FOR_QUALIFICATION"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-inference", action="store_true")
    args = parser.parse_args(argv)
    config = load_config()
    ready = preflight(config)
    if not args.authorize_inference:
        print(ready)
        return 0
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        parser.error("OPENROUTER_API_KEY must be set for authorized inference")
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, follow_redirects=False) as client:
        result = run_qualification(client, config)
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(serialize_result(result))
    print(result["final_status"])
    return 0 if result["final_status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
