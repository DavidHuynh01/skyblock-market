"""Rules for the collector's AWS template, checked on every change.

The deploy role and the permissions boundary live in the aws-account repo
(github.com/DavidHuynh01/aws-account), whose policy tests guard them. These
check the collector's side: its roles carry that boundary, and its limits and
alarms are right.
"""
from pathlib import Path

import yaml

INFRA = Path(__file__).resolve().parent.parent / "infra"

BOUNDARY_ARN = {"Sub": "arn:aws:iam::${AWS::AccountId}:policy/${AWS::StackName}-role-boundary"}


class CfnLoader(yaml.SafeLoader):
    """Reads CloudFormation short tags: `!Ref X` becomes {"Ref": "X"}."""


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {suffix: loader.construct_sequence(node, deep=True)}
    return {suffix: loader.construct_mapping(node, deep=True)}


CfnLoader.add_multi_constructor("!", _tag)


def load(name):
    return yaml.load((INFRA / name).read_text(encoding="utf-8"), Loader=CfnLoader)


def test_the_collectors_roles_are_created_inside_the_boundary():
    fn = load("template.yaml")["Resources"]["CollectorFunction"]["Properties"]
    assert fn["PermissionsBoundary"] == BOUNDARY_ARN
    assert fn["Events"]["EveryMinute"]["Properties"]["PermissionsBoundary"] == BOUNDARY_ARN


def collector():
    return load("template.yaml")["Resources"]


def test_lambda_limits_leave_room_and_never_overlap_the_next_run():
    fn = collector()["CollectorFunction"]["Properties"]
    assert fn["Timeout"] == 55, "room for a slow fetch and save after the 30 s run deadline, under 60 s"
    assert fn["MemorySize"] == 192, "headroom over the ~100 MB a run uses"


def alarm(name):
    (found,) = [r["Properties"] for r in collector().values()
                if r["Type"] == "AWS::CloudWatch::Alarm" and r["Properties"]["AlarmName"] == {"Sub": "${AWS::StackName}-" + name}]
    assert found["AlarmActions"] == [{"Ref": "AlertTopic"}] and found["OKActions"] == [{"Ref": "AlertTopic"}]
    return found


def test_two_dropped_triggers_in_ten_minutes_raise_an_alarm():
    # One dropped trigger loses nothing (the next run saves that batch); two in
    # a row can lose a minute without any error being recorded.
    a = alarm("dropped")
    assert (a["Namespace"], a["MetricName"]) == ("AWS/Lambda", "AsyncEventsDropped")
    assert a["Period"] * a["EvaluationPeriods"] <= 600
    assert a["Threshold"] == 2 and a["ComparisonOperator"] == "GreaterThanOrEqualToThreshold"
    assert a["TreatMissingData"] == "notBreaching"


def test_a_feed_that_goes_quiet_raises_an_alarm():
    # Normal is ~2,400 sales per 30 minutes. Empty batches still write files,
    # so neither the failing nor the silent alarm would notice a quiet feed.
    a = alarm("quiet")
    assert (a["Namespace"], a["MetricName"]) == ("skyblock-market", "SalesSaved")
    assert a["Dimensions"] == [{"Name": "Service", "Value": "collector"}]
    assert a["Statistic"] == "Sum" and a["Period"] * a["EvaluationPeriods"] == 1800
    assert a["Threshold"] == 100 and a["ComparisonOperator"] == "LessThanThreshold"
