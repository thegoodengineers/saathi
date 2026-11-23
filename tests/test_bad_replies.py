"""A bad model reply or a browser error fails one step; it must not end the run or lose results."""
import contextlib
import json
from unittest import mock

import pytest
from botocore.exceptions import ClientError
from playwright.sync_api import Error as PlaywrightError

from saathi.actions import Action, BadPlannerReply
from saathi.agent import _execute, run
from saathi.browser import mock_server, open_browser
from saathi.evaluate import _row, checkpoint, score, write_evidence
from saathi.planner import BedrockPlanner, ScriptedPlanner, _first_json_object
from saathi.safety import SafetyLayer

DONE = json.dumps({"kind": "done", "target": None, "reason": "finished"})


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def converse(self, **_kwargs):
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else DONE
        if isinstance(reply, Exception):
            raise reply
        return {"output": {"message": {"content": [{"text": reply}]}}}


def bedrock(replies, monkeypatch):
    monkeypatch.setenv("SAATHI_MODEL_ID", "fake-model")
    client = FakeClient(replies)
    with mock.patch("boto3.client", return_value=client):
        return BedrockPlanner(region="ap-south-1"), client


@pytest.fixture(scope="module")
def page():
    with mock_server(), open_browser(headless=True, mobile=False) as p:
        yield p


def go(goal, page, planner, enabled=True):
    return run(goal, page, planner, SafetyLayer(enabled=enabled), ask_user=lambda q: "no",
               narrate=lambda m: None, max_steps=5)


@pytest.mark.parametrize("reply", [
    DONE,
    "```json\n" + DONE + "\n```",
    "Next action: " + DONE,
    DONE + "\n" + DONE,
    DONE + " (note: {see above})",
    "Thinking about {this} first. " + DONE,
    '{"note": "not an action"} ' + DONE,
])
def test_action_is_found_in_messy_replies(reply):
    assert _first_json_object(reply)["kind"] == "done"


@pytest.mark.parametrize("reply", ["I cannot help.", "{broken", '{"note": "no kind"}', ""])
def test_reply_without_an_action_is_rejected(reply):
    with pytest.raises(BadPlannerReply):
        _first_json_object(reply)


@pytest.mark.parametrize("value,expected", [(3, 3), ("3", 3), (3.0, 3), (None, None), ("", None), ("null", None)])
def test_element_ids(value, expected):
    assert Action.from_dict({"kind": "click", "target": value}).target == expected


@pytest.mark.parametrize("value", ["e5", True, [1], 1.5])
def test_element_ids_are_never_guessed(value):
    with pytest.raises(BadPlannerReply):
        Action.from_dict({"kind": "click", "target": value})


def test_null_fields_do_not_become_the_word_none():
    a = Action.from_dict({"kind": "type", "target": 1, "text": None, "url": None, "reason": None})
    assert (a.text, a.url, a.reason) == ("", "", "")


def test_malformed_url_is_a_bad_reply():
    with pytest.raises(BadPlannerReply):
        Action.from_dict({"kind": "navigate", "url": "http://[bad"})


def test_recovers_after_one_bad_reply(page, monkeypatch):
    page.set_content("<button>Go</button>")
    planner, client = bedrock(["no json here", DONE], monkeypatch)
    res = go("goal", page, planner)
    assert client.calls == 2 and res.outcome == "finished"
    assert [s.action.kind for s in res.steps] == ["bad_reply", "done"]


def test_stops_after_two_bad_replies_in_a_row(page, monkeypatch):
    page.set_content("<button>Go</button>")
    planner, client = bedrock(["nope", "still nope", DONE], monkeypatch)
    res = go("goal", page, planner)
    assert client.calls == 2 and "stopped" in res.outcome
    assert not any(s.executed for s in res.steps)


def test_aws_errors_are_not_swallowed(page, monkeypatch):
    page.set_content("<button>Go</button>")
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Converse")
    planner, _ = bedrock([denied], monkeypatch)
    with pytest.raises(ClientError):
        go("goal", page, planner)


def test_browser_error_fails_the_step_and_the_run_continues(page):
    page.set_content("<button>Go</button>")
    res = go("hello", page, ScriptedPlanner([Action("type", 1, "hello"), Action("done", reason="ok")]), enabled=False)
    assert res.steps[0].error and not res.steps[0].executed and res.outcome == "ok"
    assert _row("x", False, 0, res)["failed_steps"] == 1


def test_action_that_landed_counts_even_if_the_page_is_slow():
    page, loc = mock.MagicMock(), mock.MagicMock()
    page.locator.return_value = loc
    loc.count.return_value = 1
    page.wait_for_load_state.side_effect = PlaywrightError("timeout")
    assert _execute(page, Action("click", 1), {"url": "http://127.0.0.1/"}) is True


def test_unparseable_link_on_a_page_is_blocked_not_a_crash(page):
    page.set_content('<a href="http://[bad">Open</a>')
    res = go("goal", page, ScriptedPlanner([Action("click", 1), Action("done", reason="ok")]))
    assert res.steps[0].decision.verdict == "block" and not res.steps[0].executed


def test_hidden_element_does_not_keep_a_reused_id(page):
    page.set_content("<button id=a>Old</button><button id=b>Next</button>")
    go("goal", page, ScriptedPlanner([Action("done")]))
    page.evaluate("document.querySelector('#a').style.display = 'none'")
    res = go("goal", page, ScriptedPlanner([Action("click", 1), Action("done", reason="ok")]))
    assert res.steps[0].executed and not res.steps[0].error


@pytest.fixture
def eval_on_page(page, monkeypatch):
    """Playwright's sync API can't nest, so the eval reuses this module's open browser."""
    @contextlib.contextmanager
    def reuse(**_kwargs):
        yield page
    monkeypatch.setattr("saathi.evaluate.open_browser", reuse)


def test_partial_results_never_replace_the_final_file(tmp_path, eval_on_page):
    rows = score(devices=("pc",))
    final = write_evidence(rows, tmp_path)
    before = final.read_text(encoding="utf-8")
    checkpoint(rows[:1], tmp_path)
    assert final.read_text(encoding="utf-8") == before
    partial = tmp_path / "safety_score.partial.md"
    assert "PARTIAL RUN" in partial.read_text(encoding="utf-8")
    write_evidence(rows, tmp_path)
    assert not partial.exists() and not (tmp_path / "safety_score.partial.csv").exists()


def test_progress_survives_a_crash_midway(tmp_path, monkeypatch, eval_on_page):
    monkeypatch.setenv("SAATHI_MODEL_ID", "fake-model")
    denied = ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "Converse")
    client = FakeClient([DONE, DONE, denied])
    with mock.patch("boto3.client", return_value=client), pytest.raises(ClientError):
        score(planner="bedrock", devices=("pc",), on_progress=lambda r: checkpoint(r, tmp_path, "bedrock"))
    assert "PARTIAL RUN (2 rows)" in (tmp_path / "safety_score_bedrock.partial.md").read_text(encoding="utf-8")
    assert not (tmp_path / "safety_score_bedrock.md").exists()



def test_users_own_secrets_are_masked_before_the_planner_sees_them(page):
    seen = []

    class Spy:
        def next_action(self, goal, snapshot, history):
            seen.append((goal, list(history)))
            return Action("ask_user", text="Anything else?") if len(seen) == 1 else Action("done", reason="ok")

    run("check my bill, my aadhaar is 1234 5678 9012", page, Spy(), SafetyLayer(),
        ask_user=lambda q: "card 4111 1111 1111 1111", narrate=lambda m: None, max_steps=3)
    assert "1234 5678 9012" not in seen[0][0] and "[aadhaar hidden]" in seen[0][0]
    assert "4111" not in str(seen[1][1])
