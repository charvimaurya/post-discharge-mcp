"""Reminder Lambda deployment files: least privilege, one schedule, real time."""

import json
import re
from pathlib import Path


DEPLOYMENT = Path(__file__).resolve().parents[2] / "deployment"


def _load(name):
    return json.loads((DEPLOYMENT / name).read_text(encoding="utf-8"))


def _actions_by_table(policy):
    return {
        statement["Resource"].rsplit("/", 1)[-1]: sorted(statement["Action"])
        for statement in policy["Statement"]
    }


def test_reminder_policy_grants_only_what_the_handler_uses():
    assert _actions_by_table(_load("reminder-policy.json")) == {
        "PostDischargeRecoveryState": ["dynamodb:GetItem", "dynamodb:UpdateItem"],
        "PostDischargeEventHistory": ["dynamodb:Query"],
    }


def test_reminder_env_has_no_clock_override_or_secrets():
    variables = _load("reminder-env.json")["Variables"]

    assert set(variables) == {"RECOVERY_STATE_TABLE", "EVENT_HISTORY_TABLE"}


def test_scheduler_can_only_invoke_the_reminder_function():
    statement = _load("scheduler-invoke-policy.json")["Statement"][0]

    assert statement["Action"] == "lambda:InvokeFunction"
    assert statement["Resource"].endswith(":function:AfterwardReminderChecker")


def test_schedule_input_never_sets_demo_now():
    target = _load("reminder-schedule-target.json")

    assert json.loads(target["Input"]) == {}
    assert target["Arn"].endswith(":function:AfterwardReminderChecker")


def test_readme_creates_exactly_one_five_minute_schedule():
    readme = (DEPLOYMENT / "README.md").read_text(encoding="utf-8")

    schedules = re.findall(r"aws scheduler create-schedule .*", readme)

    assert len(schedules) == 1
    assert '--schedule-expression "rate(5 minutes)"' in schedules[0]
    assert "DEMO_FIXED_NOW" not in (DEPLOYMENT / "reminder-env.json").read_text(encoding="utf-8")
