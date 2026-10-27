"""CloudWatch dashboard: pipeline, sync stats, issues by domain/state, assistant latency, Bedrock tokens, Guardrail."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_logs as logs
from constructs import Construct

NS = "EQH/AIDataAssistant"


class ObservabilityStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, pipeline, assistant, **kw) -> None:
        super().__init__(scope, cid, **kw)
        logs.MetricFilter(self, "LatencyFilter", log_group=logs.LogGroup.from_log_group_name(
            self, "AsstLogs", "/eqh-dq/assistant"), metric_namespace=f"{NS}/Assistant", metric_name="AnswerLatency",
            filter_pattern=logs.FilterPattern.literal('{ $.event = "answer" }'), metric_value="$.latency_s",
            unit=cw.Unit.SECONDS)
        p = cdk.Duration.days(1)
        sm = pipeline.state_machine

        def sync(name: str) -> cw.Metric:
            return cw.Metric(namespace=f"{NS}/DailySync", metric_name=name, statistic="Maximum", period=p)

        lat = cw.Metric(namespace=f"{NS}/Assistant", metric_name="AnswerLatency", period=cdk.Duration.hours(1))
        models = [cfg["models"][k] for k in ("chat", "enrich", "judge")] + [cfg["models"]["embed"]]
        dash = cw.Dashboard(self, "Dash", dashboard_name="eqh-dq-assistant")
        dash.add_widgets(
            cw.TextWidget(markdown="# EQH DQ Assistant pilot (synthetic data)", width=24, height=1))
        dash.add_widgets(
            cw.GraphWidget(title="Daily pipeline executions", width=8, left=[
                sm.metric_succeeded(period=p), sm.metric_failed(period=p)]),
            cw.GraphWidget(title="Sync: assets / edges / metrics", width=8, left=[
                sync("assets_harvested"), sync("edges"), sync("metrics")]),
            cw.GraphWidget(title="Sync: issues detected / resolved, re-embedded", width=8, left=[
                sync("issues_detected"), sync("issues_resolved"), sync("reembedded")]))
        dash.add_widgets(
            cw.GraphWidget(title="Open DQ issues by domain", width=12, stacked=True, left=[
                cw.MathExpression(expression=f"SEARCH('{{{NS}/Issues,Domain}} MetricName=\"OpenIssues\"', "
                                             f"'Maximum', 86400)", label="", period=p)]),
            cw.GraphWidget(title="Open DQ issues by state", width=12, stacked=True, left=[
                cw.MathExpression(expression=f"SEARCH('{{{NS}/Issues,State}} MetricName=\"OpenIssues\"', "
                                             f"'Maximum', 86400)", label="", period=p)]))
        dash.add_widgets(
            cw.GraphWidget(title="Assistant answer latency (s)", width=8, left=[
                lat.with_(statistic="p50", label="p50"), lat.with_(statistic="p95", label="p95")]),
            cw.GraphWidget(title="Bedrock tokens per model", width=8, left=[
                cw.Metric(namespace="AWS/Bedrock", metric_name=mname, dimensions_map={"ModelId": m}, statistic="Sum",
                          period=cdk.Duration.hours(1), label=f"{m} {mname}")
                for m in models for mname in ("InputTokenCount", "OutputTokenCount")]),
            cw.GraphWidget(title="Guardrail interventions", width=8, left=[
                cw.Metric(namespace="AWS/Bedrock/Guardrails", metric_name="InvocationsIntervened", statistic="Sum",
                          period=cdk.Duration.hours(1))]))
