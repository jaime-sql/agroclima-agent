from agroclima_agent.nebius import Completion
from agroclima_agent.pipeline import PLAN_RETRY_STEP, PLAN_TIMEOUT_SECONDS, _complete_plan


class _Client:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0)


def _done(text="ok", error=None, mock=False):
    return Completion(text=text, model="m", mock=mock, tokens=None, latency_ms=1, error=error)


def test_plan_retries_once_after_a_live_error():
    client = _Client([_done("", error="timeout"), _done("plan")])
    out = _complete_plan(client, step="plan", model="m", user_text="u", mock_text="t")
    assert out.text == "plan"
    assert [c["step"] for c in client.calls] == ["plan", PLAN_RETRY_STEP]
    assert all(c["timeout"] == PLAN_TIMEOUT_SECONDS for c in client.calls)


def test_plan_does_not_retry_on_success_or_mock():
    for first in (_done("plan"), _done("t", mock=True)):
        client = _Client([first])
        _complete_plan(client, step="plan", model="m", user_text="u", mock_text="t")
        assert len(client.calls) == 1


def test_plan_retry_is_only_once():
    client = _Client([_done("", error="timeout"), _done("", error="timeout")])
    out = _complete_plan(client, step="plan", model="m", user_text="u", mock_text="t")
    assert out.error == "timeout"
    assert len(client.calls) == 2
