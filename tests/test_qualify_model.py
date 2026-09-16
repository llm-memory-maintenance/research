"""Offline tests: every HTTP response is supplied by httpx.MockTransport."""

import importlib.util
import json
from pathlib import Path
import socket

import httpx
from pydantic import ValidationError
import pytest
import yaml

SPEC = importlib.util.spec_from_file_location(
    "qualify_model", Path(__file__).resolve().parents[1] / "experiments/qualify_model.py")
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network is forbidden in offline tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def config():
    return q.load_config()


def envelope(logical_id="E1", **changes):
    data = {"id": "gen-completion-1", "model": q.MODEL,
            "openrouter_metadata": {"endpoints": {"available": [
                {"provider": "CoreWeave", "selected": True},
                {"provider": "Other", "selected": False}]}},
            "choices": [{"message": {"content": json.dumps(q.expected_output(logical_id))}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40}}
    data.update(changes)
    return data


def single(config, data, logical_id="E1"):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))) as client:
        return q.call_model(client, config, logical_id, q.request_body(config, logical_id))


def test_config(config):
    assert config["model"]["id"] == q.MODEL
    assert config["transport"]["max_retries"] == 2
    assert config["transport"]["retry_backoff_seconds"] == [1, 2]


@pytest.mark.parametrize("section,key,value", [
    ("model", "id", "other"), ("provider", "upstream", "other"),
    ("provider", "allow_fallbacks", True), ("provider", "require_parameters", False),
    ("generation", "max_output_tokens", 0), ("transport", "max_retries", -1),
])
def test_invalid_config(tmp_path, config, section, key, value):
    config[section][key] = value
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        q.load_config(path)


def test_ten_calls_and_preflight(config):
    assert q.LOGICAL_IDS == ("E1", "E2", "M1", "M2", "M3", "A1", "A2", "E2E-E", "E2E-M", "E2E-A")
    assert q.preflight(config) == "READY_FOR_QUALIFICATION"


@pytest.mark.parametrize("logical_id", q.LOGICAL_IDS[:8])
def test_request(config, logical_id):
    body = q.request_body(config, logical_id)
    assert body["provider"] == {"order": ["coreweave/bf16"], "allow_fallbacks": False, "require_parameters": True}
    assert body["model"] == q.MODEL
    assert body["max_tokens"] == config["generation"]["max_output_tokens"]
    assert "max_output_tokens" not in body
    assert body["temperature"] == config["generation"]["temperature"]
    assert body["top_p"] == config["generation"]["top_p"]
    assert body["response_format"] == {"type": "json_object"}
    assert len(body["messages"]) == 2


@pytest.mark.parametrize("data", [
    {"memories": []}, {"memories": [q.memory("cobalt"), q.memory("amber")]},
    {"memories": [{**q.memory("cobalt"), "id": "x"}]},
    {"memories": [{**q.memory("cobalt"), "value": 3}]},
    {"memories": [q.memory("cobalt")], "extra": True},
])
def test_extraction_schema_rejects(data):
    with pytest.raises(ValidationError):
        q.ExtractionResponse.model_validate(data)


@pytest.mark.parametrize("operation,target", [("update", None), ("update", " "), ("add", "mem-1"), ("noop", "mem-1"), ("delete", None)])
def test_maintenance_invariants(operation, target):
    with pytest.raises(ValidationError):
        q.MaintenanceResponse(operation=operation, target_id=target)


@pytest.mark.parametrize("data", [{"answer": ""}, {"answer": "  "}, {"answer": 1}, {"answer": "cobalt", "extra": 1}])
def test_answer_schema(data):
    with pytest.raises(ValidationError):
        q.AnswerResponse.model_validate(data)


@pytest.mark.parametrize("logical_id", q.LOGICAL_IDS)
def test_fixture_scoring(logical_id):
    assert q.evaluate(logical_id, q.schema_for(logical_id).model_validate(q.expected_output(logical_id)))


@pytest.mark.parametrize("answer,correct", [(" COBALT ", True), ("amber", False), ("cobalt blue", False), ("cobalt.", False)])
def test_exact_answer(answer, correct):
    assert q.evaluate("A1", q.AnswerResponse(answer=answer)) is correct


def test_exact_extraction_and_target():
    assert q.evaluate("E1", q.ExtractionResponse(memories=[q.MemoryItem(entity=" MIRA ", attribute="LOCKER_COLOR", value=" Cobalt ")]))
    assert not q.evaluate("E2", q.ExtractionResponse(memories=[q.MemoryItem(**q.memory("amber"))]))
    assert not q.evaluate("M2", q.MaintenanceResponse(operation="update", target_id="mem-2"))
    assert q.normalize("e\u0301") == q.normalize("é")


def test_local_state_application():
    initial = q.active_memory("amber")
    candidate = q.MemoryItem(**q.memory("cobalt"))
    updated = q.apply_update(initial, candidate, q.MaintenanceResponse(operation="update", target_id="mem-1"))
    assert initial == q.active_memory("amber")
    assert updated == q.active_memory("cobalt")
    with pytest.raises(ValueError):
        q.apply_update(initial, candidate, q.MaintenanceResponse(operation="update", target_id="mem-2"))


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_retry_status(config, status):
    assert q.retryable(config, status=status)


@pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 422, 501])
def test_no_retry_status(config, status):
    assert not q.retryable(config, status=status)


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadError, httpx.WriteError,
    httpx.CloseError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_retry_errors(config, error):
    assert q.retryable(config, error=error("mock"))


def test_other_errors_not_retried(config):
    assert not q.retryable(config, error=httpx.RemoteProtocolError("mock"))
    assert not q.retryable(config, error=ValueError("mock"))


def test_retry_codes_follow_config(config):
    config["transport"]["retry_status_codes"] = [418]
    assert q.retryable(config, status=418)
    assert not q.retryable(config, status=503)


def test_retry_response_metadata_recorded(config, monkeypatch):
    monkeypatch.setattr(q.time, "sleep", lambda _: None)
    metadata = envelope()["openrouter_metadata"]
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
            503, json={"id": "retry-id", "openrouter_metadata": metadata},
            headers={"x-request-id": "header-id"}))) as client:
        result = q.call_model(client, config, "E1", q.request_body(config, "E1"))
    assert len(result["attempts"]) == 3
    for attempt in result["attempts"]:
        assert attempt["request_id"] == "header-id"
        assert attempt["response_id"] == "retry-id"
        assert attempt["openrouter_metadata"] == metadata
        assert attempt["latency_seconds"] >= 0


@pytest.mark.parametrize("failure", [503, httpx.ConnectError])
def test_retry_attempts_and_backoff(config, monkeypatch, failure):
    sleeps, requests = [], []
    monkeypatch.setattr(q.time, "sleep", sleeps.append)

    def respond(request):
        requests.append(request)
        assert request.headers["X-OpenRouter-Metadata"] == "enabled"
        assert str(request.url) == q.URL
        assert request.method == "POST"
        assert request.extensions["timeout"]["read"] == 180
        if len(requests) < 3:
            if isinstance(failure, int):
                return httpx.Response(failure)
            raise failure("mock")
        return httpx.Response(200, json=envelope())

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = q.call_model(client, config, "E1", q.request_body(config, "E1"))
    assert sleeps == [1, 2]
    assert len(result["attempts"]) == 3
    assert result["evaluation_status"] == "passed"
    assert [a["will_retry"] for a in result["attempts"]] == [True, True, False]


@pytest.mark.parametrize("status,attempts", [(401, 1), (429, 3)])
def test_http_failures(config, monkeypatch, status, attempts):
    monkeypatch.setattr(q.time, "sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as client:
        result = q.call_model(client, config, "E1", q.request_body(config, "E1"))
    assert len(result["attempts"]) == attempts
    assert result["request_status"] == "failed"


@pytest.mark.parametrize("content,parse,schema,evaluation", [
    ('```json\n{}\n```', "failed", "not_run", "not_run"),
    ('{"memories": []}', "passed", "failed", "not_run"),
    (json.dumps({"memories": [q.memory("amber")]}), "passed", "passed", "failed"),
    ('I cannot help.', "failed", "not_run", "not_run"),
])
def test_no_output_retries(config, content, parse, schema, evaluation):
    result = single(config, envelope(choices=[{"message": {"content": content}}]))
    assert len(result["attempts"]) == 1
    assert (result["parse_status"], result["schema_status"], result["evaluation_status"]) == (parse, schema, evaluation)
    assert result["raw_assistant_content"] == content


@pytest.mark.parametrize("metadata,ok", [
    (envelope()["openrouter_metadata"], True),
    ({"endpoints": {"available": [{"provider": "CoreWeave", "selected": False}]}}, False),
    ({"endpoints": {"available": [
        {"provider": "CoreWeave", "selected": False},
        {"provider": "Other", "selected": True}]}}, False),
    ({"endpoints": {"available": [
        {"provider": "CoreWeave", "selected": True},
        {"provider": "Other", "selected": True}]}}, False),
    (None, False), ([], False), ("CoreWeave", False), ({}, False),
    ({"provider": "CoreWeave", "provider_name": "CoreWeave"}, False),
    ({"endpoints": None}, False), ({"endpoints": []}, False),
    ({"endpoints": {}}, False), ({"endpoints": {"available": {}}}, False),
    ({"endpoints": {"available": []}}, False),
    ({"endpoints": {"available": [None]}}, False),
    ({"endpoints": {"available": [{"provider": "CoreWeave"}]}}, False),
    ({"endpoints": {"available": [{"provider": "CoreWeave", "selected": "true"}]}}, False),
    ({"endpoints": {"available": [{"provider": "CoreWeave", "selected": 1}]}}, False),
    ({"endpoints": {"available": [{"provider": None, "selected": True}]}}, False),
])
def test_provider_evidence(config, metadata, ok):
    assert single(config, envelope(openrouter_metadata=metadata))["routing_ok"] is ok


def test_absent_provider_metadata(config):
    data = envelope()
    del data["openrouter_metadata"]
    assert not single(config, data)["routing_ok"]


@pytest.mark.parametrize("key,value", [
    ("order", ["coreweave"]), ("order", [q.PROVIDER, "other"]),
    ("allow_fallbacks", True), ("allow_fallbacks", 0),
    ("require_parameters", False), ("require_parameters", 1),
])
def test_routing_requires_pinned_request(config, key, value):
    body = q.request_body(config, "E1")
    body["provider"][key] = value
    assert not q.routing_ok(body, envelope()["openrouter_metadata"], q.MODEL)


@pytest.mark.parametrize("headers,request_id", [({}, None), ({"x-request-id": "header-id"}, "header-id")])
def test_request_and_response_ids_are_distinct(config, headers, request_id):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, json=envelope(), headers=headers))) as client:
        result = q.call_model(client, config, "E1", q.request_body(config, "E1"))
    attempt = result["attempts"][0]
    assert attempt["request_id"] == request_id
    assert attempt["response_id"] == "gen-completion-1"


def test_accounting_and_model(config):
    result = single(config, envelope())
    assert result["accounting_ok"]
    assert result["usage"]["cost"] is None
    assert result["usage"]["cached_tokens"] is None
    assert result["attempts"][0]["service_tier"] is None
    assert not single(config, envelope(usage={"prompt_tokens": 30}))["accounting_ok"]
    assert not single(config, envelope(model="other"))["routing_ok"]
    result = single(config, envelope(usage={"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.1,
                                           "prompt_tokens_details": {"cached_tokens": 12}}))
    assert result["accounting_ok"]
    assert result["usage"]["cached_tokens"] == 12


def mock_run(config, failed_id=None):
    requests = []

    def respond(request):
        logical_id = q.LOGICAL_IDS[len(requests)]
        requests.append(json.loads(request.content))
        data = envelope(logical_id)
        if logical_id == failed_id:
            data["choices"][0]["message"]["content"] = "invalid"
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = q.run_qualification(client, config)
    return result, requests


def test_full_e2e(config):
    result, requests = mock_run(config)
    assert result["final_status"] == "QUALIFIED"
    assert len(requests) == len(result["logical_calls"]) == 10
    assert json.loads(requests[8]["messages"][1]["content"])["active_memory"] == q.active_memory("amber")
    assert json.loads(requests[9]["messages"][1]["content"])["active_memory"] == q.active_memory("cobalt")
    assert result["local_update_applied"]
    assert result["started_at"] <= result["ended_at"]


@pytest.mark.parametrize("failed_id,count", [("E2E-E", 8), ("E2E-M", 9)])
def test_failed_dependencies(config, failed_id, count):
    result, requests = mock_run(config, failed_id)
    assert len(requests) == count
    assert len(result["logical_calls"]) == 10
    assert result["final_status"] == "NOT_QUALIFIED"
    assert result["logical_calls"][-1]["request_status"] == "blocked"
    assert not result["local_update_applied"]


@pytest.mark.parametrize("field,value", [("request_status", "failed"), ("parse_status", "failed"),
    ("schema_status", "failed"), ("evaluation_status", "failed"), ("routing_ok", False), ("accounting_ok", False)])
def test_each_criterion_required(config, field, value):
    result, _ = mock_run(config)
    for call in result["logical_calls"]:
        previous = call[field]
        call[field] = value
        assert q.final_status(result["logical_calls"], True) == "NOT_QUALIFIED"
        call[field] = previous
    assert q.final_status(result["logical_calls"][:-1], True) == "NOT_QUALIFIED"
    assert q.final_status(result["logical_calls"], False) == "NOT_QUALIFIED"


def test_secret_redaction(config, monkeypatch):
    secret = "sk-offline-sentinel-secret"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    result, _ = mock_run(config)
    result["logical_calls"][0]["raw_assistant_content"] = secret
    result["logical_calls"][0]["attempts"][0]["openrouter_metadata"] = {secret: [secret]}
    serialized = q.serialize_result(result)
    assert secret not in serialized
    assert "Authorization" not in serialized
    assert "[REDACTED]" in serialized


def test_default_cli_no_inference(config, monkeypatch, capsys, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Default CLI must not initialize inference")
    monkeypatch.setattr(q.httpx, "Client", forbidden)
    monkeypatch.setattr(q, "run_qualification", forbidden)
    original_get = q.os.environ.get

    def guarded_get(key, *args):
        if key == "OPENROUTER_API_KEY":
            forbidden()
        return original_get(key, *args)

    monkeypatch.setattr(q.os.environ, "get", guarded_get)
    monkeypatch.setattr(q, "RESULT_PATH", tmp_path / "qualification.json")
    assert q.main([]) == 0
    assert capsys.readouterr().out == "READY_FOR_QUALIFICATION\n"
    assert not q.RESULT_PATH.exists()
