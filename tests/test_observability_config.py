"""Offline checks for the observability wiring; never call AWS."""
import json
from pathlib import Path

import botocore.session
from botocore.validate import validate_parameters
import yaml

ROOT = Path(__file__).resolve().parents[1]


class CloudFormationLoader(yaml.SafeLoader):
    """Preserve CFN intrinsics as data without evaluating or executing them."""


def _intrinsic(loader, tag, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {tag if tag == 'Ref' else f'Fn::{tag}': value}


CloudFormationLoader.add_multi_constructor('!', _intrinsic)
TEMPLATE = yaml.load(
    (ROOT / 'infra/observability/template.yaml').read_text(), Loader=CloudFormationLoader
)
RESOURCES = TEMPLATE['Resources']


def test_ecs_definition_matches_aws_api_schema():
    definition = json.loads((ROOT / 'ecs-task-definition.json').read_text())
    model = botocore.session.get_session().get_service_model('ecs')
    validate_parameters(definition, model.operation_model('RegisterTaskDefinition').input_shape)


def test_mcp_logs_use_administrator_created_london_group():
    definition = json.loads((ROOT / 'ecs-task-definition.json').read_text())
    container = next(c for c in definition['containerDefinitions'] if c['name'] == 'afterward-mcp')
    assert container['logConfiguration'] == {
        'logDriver': 'awslogs',
        'options': {
            'awslogs-group': '/ecs/afterward-mcp',
            'awslogs-region': 'eu-west-2',
            'awslogs-stream-prefix': 'mcp',
        },
    }
    assert not any(r['Type'] == 'AWS::Logs::LogGroup' for r in RESOURCES.values())
    assert TEMPLATE['Parameters']['McpLogGroupName']['Default'] == '/ecs/afterward-mcp'


def test_tool_alarm_matches_emf_metric_dimensions_and_threshold():
    alarm = RESOURCES['ToolErrorsAlarm']['Properties']
    assert (alarm['Namespace'], alarm['MetricName']) == ('AfterWard', 'tool_errors')
    assert alarm['Dimensions'] == [{'Name': 'service', 'Value': 'mcp'}]
    assert alarm['Statistic'] == 'Sum'
    assert alarm['Threshold'] == {'Ref': 'ToolErrorThreshold'}
    assert TEMPLATE['Parameters']['ToolErrorThreshold']['Default'] == 3
    assert alarm['ComparisonOperator'] == 'GreaterThanThreshold'
    assert (alarm['Period'], alarm['EvaluationPeriods']) == (300, 1)


def test_dlq_alarm_detects_any_visible_message():
    alarm = RESOURCES['DeadLetterQueueAlarm']['Properties']
    assert (alarm['Namespace'], alarm['MetricName']) == ('AWS/SQS', 'ApproximateNumberOfMessagesVisible')
    assert alarm['Dimensions'] == [{'Name': 'QueueName', 'Value': {'Ref': 'DeadLetterQueueName'}}]
    assert alarm['Threshold'] == 0
    assert alarm['ComparisonOperator'] == 'GreaterThanThreshold'
    assert alarm['Statistic'] == 'Maximum'


def test_all_alarms_publish_to_sns_and_optional_email_is_wired():
    for name in ('ToolErrorsAlarm', 'DeadLetterQueueAlarm', 'McpAvailabilityAlarm'):
        assert RESOURCES[name]['Properties']['AlarmActions'] == [{'Ref': 'AlarmTopic'}]
    assert RESOURCES['AlarmTopic']['Type'] == 'AWS::SNS::Topic'
    subscription = RESOURCES['AlarmEmailSubscription']
    assert subscription['Condition'] == 'HasAlarmEmail'
    assert subscription['Properties'] == {
        'TopicArn': {'Ref': 'AlarmTopic'}, 'Protocol': 'email', 'Endpoint': {'Ref': 'AlarmEmail'},
    }
    statement = RESOURCES['AlarmTopicPolicy']['Properties']['PolicyDocument']['Statement'][0]
    assert statement['Principal'] == {'Service': 'cloudwatch.amazonaws.com'}
    assert statement['Action'] == 'sns:Publish'
    assert statement['Resource'] == {'Ref': 'AlarmTopic'}
    assert statement['Condition']['StringEquals']['aws:SourceAccount'] == {'Ref': 'AWS::AccountId'}
    source_arns = statement['Condition']['ArnEquals']['aws:SourceArn']
    assert {a['Fn::Sub'].rsplit(':', 1)[-1] for a in source_arns} == {
        'afterward-tool-errors', 'afterward-document-dlq-not-empty', 'afterward-mcp-no-healthy-targets',
    }


def test_saved_queries_include_mcp_log_group():
    for resource in RESOURCES.values():
        if resource['Type'] == 'AWS::Logs::QueryDefinition':
            groups = resource['Properties']['LogGroupNames']
            assert {'Ref': 'McpLogGroupName'} in groups['Fn::Split'][1]['Fn::Join'][1]


def test_availability_alarm_detects_no_healthy_targets_and_missing_metrics():
    alarm = RESOURCES['McpAvailabilityAlarm']['Properties']
    assert alarm['Namespace'] == 'AWS/ApplicationELB'
    assert alarm['MetricName'] == 'HealthyHostCount'
    assert alarm['Dimensions'] == [
        {'Name': 'LoadBalancer', 'Value': {'Ref': 'McpLoadBalancerFullName'}},
        {'Name': 'TargetGroup', 'Value': {'Ref': 'McpTargetGroupFullName'}},
    ]
    assert alarm['Statistic'] == 'Minimum'
    assert alarm['Threshold'] == 1
    assert alarm['ComparisonOperator'] == 'LessThanThreshold'
    assert (alarm['Period'], alarm['EvaluationPeriods'], alarm['DatapointsToAlarm']) == (60, 3, 3)
    assert alarm['TreatMissingData'] == 'breaching'


def test_availability_dimensions_require_explicit_full_names():
    import re

    for name, valid, invalid in (
        ('McpLoadBalancerFullName', 'app/example-alb/0123456789abcdef',
         ('arn:aws:elasticloadbalancing:eu-west-2:123456789012:loadbalancer/app/example/0123',
          'example.eu-west-2.elb.amazonaws.com', 'example-alb', '')),
        ('McpTargetGroupFullName', 'targetgroup/example-tg/0123456789abcdef',
         ('arn:aws:elasticloadbalancing:eu-west-2:123456789012:targetgroup/example/0123',
          'example-tg', '')),
    ):
        parameter = TEMPLATE['Parameters'][name]
        assert parameter['Type'] == 'String'
        assert 'Default' not in parameter
        assert re.fullmatch(parameter['AllowedPattern'], valid)
        for value in invalid:
            assert not re.fullmatch(parameter['AllowedPattern'], value)
