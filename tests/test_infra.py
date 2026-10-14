"""Security rules for the AWS templates, checked on every change.

The deploy role is what GitHub Actions runs as. Whoever controls the pipeline
controls that role, so it must never be able to grant itself, or any role it
creates, more than the collector needs.
"""
from pathlib import Path

import yaml

INFRA = Path(__file__).resolve().parent.parent / "infra"

# Actions that create a role or widen what a role may do.
ROLE_WRITES = {
    "iam:CreateRole",
    "iam:PutRolePolicy",
    "iam:AttachRolePolicy",
    "iam:DetachRolePolicy",
    "iam:DeleteRolePolicy",
    "iam:PutRolePermissionsBoundary",
}
BOUNDARY_REF = {"Ref": "RoleBoundary"}
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


def actions(statement):
    a = statement["Action"]
    return set(a if isinstance(a, list) else [a])


def deploy_statements():
    role = load("github-oidc.yaml")["Resources"]["DeployRole"]["Properties"]
    return [s for p in role["Policies"] for s in p["PolicyDocument"]["Statement"]]


def test_roles_can_only_be_created_or_widened_inside_the_boundary():
    found = set()
    for s in deploy_statements():
        writes = actions(s) & ROLE_WRITES
        if s["Effect"] == "Allow" and writes:
            found |= writes
            assert s["Condition"]["StringEquals"]["iam:PermissionsBoundary"] == BOUNDARY_REF, s["Sid"]
    assert found == ROLE_WRITES, "every role-writing action is granted, and only with the boundary"


def test_nothing_can_remove_a_boundary_or_grant_everything():
    for s in deploy_statements():
        if s["Effect"] == "Allow":
            assert not actions(s) & {"iam:DeleteRolePermissionsBoundary", "iam:*", "*"}, s["Sid"]


def test_stack_roles_can_only_be_passed_to_lambda_and_the_scheduler():
    passes = [s for s in deploy_statements() if "iam:PassRole" in actions(s)]
    assert passes
    for s in passes:
        assert s["Condition"]["StringEquals"]["iam:PassedToService"] == [
            "lambda.amazonaws.com",
            "scheduler.amazonaws.com",
        ]


def test_the_boundary_allows_only_what_the_collector_needs():
    boundary = load("github-oidc.yaml")["Resources"]["RoleBoundary"]["Properties"]["PolicyDocument"]
    granted = set()
    for s in boundary["Statement"]:
        assert s["Effect"] == "Allow"
        granted |= actions(s)
        if "s3:PutObject" in actions(s):
            assert s["Resource"]["Sub"].endswith("/raw/*"), "sales can only be added, under raw/"
    assert granted == {
        "s3:PutObject",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "lambda:InvokeFunction",
    }


def test_the_collectors_roles_are_created_inside_the_boundary():
    fn = load("template.yaml")["Resources"]["CollectorFunction"]["Properties"]
    assert fn["PermissionsBoundary"] == BOUNDARY_ARN
    assert fn["Events"]["EveryMinute"]["Properties"]["PermissionsBoundary"] == BOUNDARY_ARN
