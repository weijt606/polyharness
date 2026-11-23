"""Tests for the Anthropic API proposer (request shape, refusals, fallbacks).

No network: the SDK client is replaced with a fake that records requests and
replays scripted responses.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from polyharness.config import DEFAULT_API_MODEL, DEFAULT_EFFORT, ProposerConfig
from polyharness.proposer import api_proposer as ap
from polyharness.proposer import create_proposer
from polyharness.proposer.api_proposer import APIProposer, ProposerRefusalError


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use(name, inp, id_="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id_)


def _msg(content, stop_reason="end_turn", model=DEFAULT_API_MODEL, stop_details=None):
    return SimpleNamespace(
        content=content, stop_reason=stop_reason, model=model, stop_details=stop_details
    )


class _FakeStream:
    def __init__(self, msg):
        self._msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._msg


class _FakeClient:
    """Records every streamed request; returns scripted messages in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []
        self.messages = SimpleNamespace(stream=self._make("messages"))
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._make("beta")))

    def _make(self, ns):
        def stream(**kwargs):
            # Snapshot messages: the proposer keeps appending to the same list.
            self.calls.append((ns, {**kwargs, "messages": list(kwargs["messages"])}))
            return _FakeStream(self._responses.pop(0))

        return stream


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "ws"
    cand = root / "candidates" / "iter_1"
    cand.mkdir(parents=True)
    (cand / "harness.py").write_text("# harness\n")
    return root, cand


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(ap.anthropic, "Anthropic", lambda: client)


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


def test_defaults_are_current_generation():
    p = APIProposer()
    assert p.model == "claude-opus-5-5"
    assert p.effort == DEFAULT_EFFORT == "high"
    assert p.uses_fallbacks


def test_request_has_effort_caching_fallbacks_and_no_sampling(monkeypatch, ws):
    root, cand = ws
    client = _FakeClient([_msg([_text("done")])])
    _patch_client(monkeypatch, client)

    meta = APIProposer().propose(root, cand, 1, 0)

    assert meta["changes_summary"] == "done"
    assert meta["proposer_effort"] == "high"
    assert "served_by_models" not in meta
    ns, req = client.calls[0]
    assert ns == "beta"  # fallbacks are a beta parameter
    assert req["betas"] == [ap.FALLBACK_BETA]
    assert req["extra_body"] == {"fallbacks": "default"}
    assert req["output_config"] == {"effort": "high"}
    assert req["cache_control"] == {"type": "ephemeral"}
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in req


def test_temperature_is_never_sent_and_warns(monkeypatch, ws, capsys):
    root, cand = ws
    client = _FakeClient([_msg([_text("ok")])])
    _patch_client(monkeypatch, client)

    APIProposer(temperature=0.7).propose(root, cand, 1, 0)

    assert "temperature" not in client.calls[0][1]
    assert "proposer.temperature is ignored" in capsys.readouterr().err


def test_effort_none_and_unsupported_model_use_plain_endpoint(monkeypatch, ws):
    root, cand = ws
    client = _FakeClient([_msg([_text("ok")], model="claude-haiku-4-5")])
    _patch_client(monkeypatch, client)

    APIProposer(model="claude-haiku-4-5", effort=None).propose(root, cand, 1, 0)

    ns, req = client.calls[0]
    assert ns == "messages"
    assert "output_config" not in req
    assert "extra_body" not in req and "betas" not in req


def test_refusal_fallback_can_be_disabled(monkeypatch, ws):
    root, cand = ws
    client = _FakeClient([_msg([_text("ok")])])
    _patch_client(monkeypatch, client)

    APIProposer(refusal_fallback=False).propose(root, cand, 1, 0)

    ns, req = client.calls[0]
    assert ns == "messages"
    assert "extra_body" not in req


# ---------------------------------------------------------------------------
# Tool loop
# ---------------------------------------------------------------------------


def test_tool_loop_appends_history_and_writes_file(monkeypatch, ws):
    root, cand = ws
    first = _msg(
        [_tool_use("file_write", {"path": "harness.py", "content": "# improved\n"})],
        stop_reason="tool_use",
    )
    client = _FakeClient([first, _msg([_text("rewrote harness")])])
    _patch_client(monkeypatch, client)

    meta = APIProposer().propose(root, cand, 1, 0)

    assert (cand / "harness.py").read_text() == "# improved\n"
    assert meta["tool_calls"] == 1
    second_msgs = client.calls[1][1]["messages"]
    # Assistant content is replayed unchanged (append-only history).
    assert second_msgs[1] == {"role": "assistant", "content": first.content}
    assert second_msgs[2]["content"][0]["type"] == "tool_result"
    assert second_msgs[2]["content"][0]["tool_use_id"] == "tu_1"


def test_mid_output_fallback_drops_declined_partial(monkeypatch, ws):
    """Tool calls the declined model emitted before the fallback boundary are
    neither executed nor echoed back; the fallback block keeps its position."""
    root, cand = ws
    declined_call = _tool_use("file_write", {"path": "harness.py", "content": "# BAD\n"}, id_="tu_bad")
    thinking = SimpleNamespace(type="thinking", thinking="", signature="sig")
    boundary = SimpleNamespace(type="fallback")
    good_call = _tool_use("file_write", {"path": "harness.py", "content": "# good\n"}, id_="tu_good")
    first = _msg(
        [thinking, _text("partial"), declined_call, boundary, good_call],
        stop_reason="tool_use",
        model="claude-opus-4-8",
    )
    client = _FakeClient([first, _msg([_text("done")], model="claude-opus-4-8")])
    _patch_client(monkeypatch, client)

    meta = APIProposer().propose(root, cand, 1, 0)

    assert (cand / "harness.py").read_text() == "# good\n"
    assert meta["tool_calls"] == 1
    echoed = client.calls[1][1]["messages"][1]["content"]
    assert [b.type for b in echoed] == ["text", "fallback", "tool_use"]
    assert echoed[2].id == "tu_good"
    results = client.calls[1][1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu_good"]
    assert meta["served_by_models"] == ["claude-opus-4-8"]


def test_echo_content_without_fallback_is_unchanged():
    content = [SimpleNamespace(type="thinking"), _text("a"), _tool_use("list_dir", {"path": "."})]
    assert ap._echo_content(content) == content


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_refusal_raises_with_category(monkeypatch, ws):
    root, cand = ws
    details = SimpleNamespace(category="cyber", explanation="x")
    client = _FakeClient([_msg([], stop_reason="refusal", stop_details=details)])
    _patch_client(monkeypatch, client)

    with pytest.raises(ProposerRefusalError, match="cyber"):
        APIProposer().propose(root, cand, 1, 0)


def test_refusal_without_details(monkeypatch, ws):
    root, cand = ws
    client = _FakeClient([_msg([], stop_reason="refusal")])
    _patch_client(monkeypatch, client)

    with pytest.raises(ProposerRefusalError, match="unspecified"):
        APIProposer().propose(root, cand, 1, 0)


def test_fallback_model_is_recorded(monkeypatch, ws):
    root, cand = ws
    client = _FakeClient([_msg([_text("ok")], model="claude-opus-4-8")])
    _patch_client(monkeypatch, client)

    meta = APIProposer().propose(root, cand, 1, 0)

    assert meta["served_by_models"] == ["claude-opus-4-8"]


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


def test_factory_passes_effort_and_fallback():
    cfg = ProposerConfig(effort="xhigh", refusal_fallback=False)
    p = create_proposer(cfg)
    assert isinstance(p, APIProposer)
    assert p.effort == "xhigh"
    assert not p.uses_fallbacks


def test_factory_effort_null():
    p = create_proposer(ProposerConfig(effort=None))
    assert p.effort is None


def test_config_rejects_bad_effort():
    with pytest.raises(ValueError):
        ProposerConfig(effort="ultra")


# ---------------------------------------------------------------------------
# Real SDK request serialization (network intercepted by a mock transport)
# ---------------------------------------------------------------------------

try:  # anthropic >= 1.0 is built on httpx2; older releases on httpx
    import httpx2 as _httpx  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on installed SDK major
    import httpx as _httpx

_SSE = (
    'event: message_start\ndata: {"type":"message_start","message":{"id":"m","type":"message",'
    '"role":"assistant","model":"claude-opus-5-5","content":[],"stop_reason":null,'
    '"stop_sequence":null,"usage":{"input_tokens":1,"output_tokens":1}}}\n\n'
    'event: content_block_start\ndata: {"type":"content_block_start","index":0,'
    '"content_block":{"type":"text","text":""}}\n\n'
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
    '"delta":{"type":"text_delta","text":"done"}}\n\n'
    'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
    'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn",'
    '"stop_sequence":null},"usage":{"output_tokens":2}}\n\n'
    'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)


@pytest.mark.parametrize("fallback", [True, False])
def test_real_sdk_serializes_request(monkeypatch, ws, fallback):
    """The installed SDK accepts every parameter we send (no TypeError) and
    puts them on the wire as intended."""
    import json

    root, cand = ws
    captured = []

    def handler(request):
        captured.append((request, json.loads(request.content)))
        return _httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_SSE.encode()
        )

    real_client = ap.anthropic.Anthropic
    http_client = ap.anthropic.DefaultHttpxClient(transport=_httpx.MockTransport(handler))
    monkeypatch.setattr(
        ap.anthropic, "Anthropic", lambda: real_client(api_key="test-key", http_client=http_client)
    )

    meta = APIProposer(refusal_fallback=fallback).propose(root, cand, 1, 0)

    assert meta["changes_summary"] == "done"
    request, body = captured[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"] == {"effort": "high"}
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["stream"] is True
    assert "temperature" not in body
    if fallback:
        assert body["fallbacks"] == "default"
        assert ap.FALLBACK_BETA in request.headers.get("anthropic-beta", "")
    else:
        assert "fallbacks" not in body
        assert "anthropic-beta" not in request.headers


# ---------------------------------------------------------------------------
# Review regressions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model", ["claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-1", "claude-3-7-sonnet-latest"]
)
def test_effort_not_sent_to_models_without_effort(model, capsys):
    p = APIProposer(model=model)  # effort defaults to "high"
    assert p.effort is None
    assert "does not support proposer.effort" in capsys.readouterr().err
    assert "output_config" not in p._build_request("s", [])


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-4-6", "claude-future-9"])
def test_effort_kept_for_supporting_and_unknown_models(model):
    assert APIProposer(model=model).effort == "high"


def test_default_max_tokens_is_large_when_unset():
    assert APIProposer().max_tokens == 64000
    assert APIProposer(max_tokens=2048).max_tokens == 2048
    assert create_proposer(ProposerConfig()).max_tokens == 64000


def test_max_tokens_truncation_is_a_failure(monkeypatch, ws):
    root, cand = ws
    client = _FakeClient([_msg([_text("half a pl")], stop_reason="max_tokens")])
    _patch_client(monkeypatch, client)

    with pytest.raises(RuntimeError, match="truncated at max_tokens"):
        APIProposer().propose(root, cand, 1, 0)


def test_tool_budget_summary_keeps_tools_and_forbids_calls(monkeypatch, ws):
    root, cand = ws
    monkeypatch.setattr(ap, "_MAX_TOOL_ROUNDS", 2)
    loop = [
        _msg([_tool_use("list_dir", {"path": "."}, id_=f"tu_{i}")], stop_reason="tool_use")
        for i in range(2)
    ]
    client = _FakeClient([*loop, _msg([_text("summary of edits")])])
    _patch_client(monkeypatch, client)

    meta = APIProposer().propose(root, cand, 1, 0)

    assert meta["changes_summary"] == "summary of edits"
    _, final = client.calls[-1]
    assert final["tools"]  # history has tool_use blocks: tools must stay declared
    assert final["tool_choice"] == {"type": "none"}
    msgs = final["messages"]
    # No two user turns in a row: the instruction joins the last tool results.
    assert [m["role"] for m in msgs[-2:]] == ["assistant", "user"]
    last = msgs[-1]["content"]
    assert last[0]["type"] == "tool_result" and last[-1]["type"] == "text"


def test_summary_ignores_declined_partial_text(monkeypatch, ws):
    root, cand = ws
    content = [_text("declined partial"), SimpleNamespace(type="fallback"), _text("fallback summary")]
    client = _FakeClient([_msg(content, model="claude-opus-4-8")])
    _patch_client(monkeypatch, client)
    assert APIProposer().propose(root, cand, 1, 0)["changes_summary"] == "fallback summary"

    # Fallback model produced no text: the declined text is NOT recorded.
    client2 = _FakeClient([_msg([_text("declined partial"), SimpleNamespace(type="fallback")])])
    _patch_client(monkeypatch, client2)
    assert APIProposer().propose(root, cand, 1, 0)["changes_summary"] == ""


def _status_error(status, body):
    import httpx as _hx  # error construction only needs a response object

    req = _hx.Request("POST", "https://api.anthropic.com/v1/messages")
    return ap.anthropic.APIStatusError("boom", response=_hx.Response(status, request=req), body=body)


def test_mid_stream_overloaded_error_is_retried():
    exc = _status_error(200, {"type": "error", "error": {"type": "overloaded_error", "message": "x"}})
    assert ap._is_retryable(exc)


def test_non_transient_errors_are_not_retried():
    exc = _status_error(400, {"type": "error", "error": {"type": "invalid_request_error"}})
    assert not ap._is_retryable(exc)
    assert ap._is_retryable(_status_error(529, None))


def test_stream_retries_then_succeeds(monkeypatch, ws):
    root, cand = ws
    monkeypatch.setattr(ap.time, "sleep", lambda s: None)
    calls = {"n": 0}
    ok = _msg([_text("done")])

    def stream(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _status_error(200, {"type": "error", "error": {"type": "overloaded_error"}})
        return _FakeStream(ok)

    client = SimpleNamespace(
        messages=SimpleNamespace(stream=stream), beta=SimpleNamespace(messages=SimpleNamespace(stream=stream))
    )
    _patch_client(monkeypatch, client)

    assert APIProposer().propose(root, cand, 1, 0)["changes_summary"] == "done"
    assert calls["n"] == 2


def test_openai_backend_uses_its_own_default_model():
    from polyharness.config import DEFAULT_OPENAI_MODEL

    p = create_proposer(ProposerConfig(backend="openai"))
    assert p.model == DEFAULT_OPENAI_MODEL
    assert p.max_tokens is None  # not sent: local servers decide
