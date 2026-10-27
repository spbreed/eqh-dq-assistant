"""ECS Fargate jobs (profiler -> daily_sync -> enrich), Step Functions, EventBridge Scheduler, failure alarms."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cwa
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_logs as logs
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

import pilot_config
from stacks.image import REPO

MANTLE_ACTIONS = ["bedrock-mantle:CreateInference", "bedrock-mantle:Get*", "bedrock-mantle:List*"]


def bedrock_statements(region: str, account: str, cfg: dict) -> list[iam.PolicyStatement]:
    m = cfg["models"]
    model_arns = [f"arn:aws:bedrock:{region}::foundation-model/{m['embed']}"]
    for role in ("chat", "enrich", "judge"):
        mid = m[role]
        model_arns += [f"arn:aws:bedrock:*::foundation-model/{mid}",
                       f"arn:aws:bedrock:{region}:{account}:inference-profile/us.{mid}"]
    return [
        iam.PolicyStatement(actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                            resources=model_arns),
        # bedrock-mantle (OpenAI-compatible endpoint) authorises with its own IAM namespace
        iam.PolicyStatement(actions=MANTLE_ACTIONS, resources=["*"]),
    ]


class PipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, network, security, data, meta, **kw) -> None:
        super().__init__(scope, cid, **kw)
        # imported by ARN so grants land on role policies (no cross-stack key-policy cycle)
        key = kms.Key.from_key_arn(self, "Cmk", security.key.key_arn)
        tag = self.node.try_get_context("image_tag") or "latest"
        repo = ecr.Repository.from_repository_name(self, "Repo", REPO)
        image = ecs.ContainerImage.from_ecr_repository(repo, tag)
        self.cluster = ecs.Cluster(self, "Cluster", cluster_name="eqh-dq", vpc=network.vpc,
                                   container_insights_v2=ecs.ContainerInsights.ENABLED)
        self.task_sg = ec2.SecurityGroup(self, "TaskSg", vpc=network.vpc, description="Pipeline tasks (egress only)")
        self.log_group = logs.LogGroup(self, "Logs", log_group_name="/eqh-dq/pipeline",
                                       retention=logs.RetentionDays.ONE_MONTH, encryption_key=key,
                                       removal_policy=cdk.RemovalPolicy.DESTROY)

        harvest = iam.Role.from_role_name(self, "Harvest", pilot_config.HARVEST_ROLE)
        eval_role = iam.Role.from_role_name(self, "EvalR", pilot_config.EVAL_ROLE)
        b = {k: data.buckets[k] for k in data.buckets}
        h_secret = meta.user_secrets["eqh_harvest"]
        a_secret = meta.user_secrets["eqh_assistant"]
        iam.Policy(self, "HarvestPolicy", roles=[harvest], statements=[
            iam.PolicyStatement(actions=["glue:GetDatabase*", "glue:GetTable*", "glue:GetPartition*",
                                         "glue:ListDataQualityResults", "glue:GetDataQualityResult",
                                         "glue:BatchGetDataQualityResult"], resources=["*"]),
            iam.PolicyStatement(actions=["s3:GetObject", "s3:ListBucket"],
                                resources=[x for k in ("raw", "silver", "extracts", "glossary", "dq-results")
                                           for x in (b[k].bucket_arn, b[k].arn_for_objects("*"))]),
            iam.PolicyStatement(actions=["s3:PutObject"], resources=[b["dq-results"].arn_for_objects("profile/*")]),
            iam.PolicyStatement(actions=["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
                                resources=[key.key_arn]),
            iam.PolicyStatement(actions=["redshift-data:ExecuteStatement", "redshift-data:BatchExecuteStatement"],
                                resources=[data.workgroup_arn]),
            iam.PolicyStatement(actions=["redshift-data:DescribeStatement", "redshift-data:GetStatementResult",
                                         "redshift-data:CancelStatement"], resources=["*"],
                                conditions={"StringEquals": {"redshift-data:statement-owner-iam-userid":
                                                             "${aws:userid}"}}),
            iam.PolicyStatement(actions=["redshift-serverless:GetCredentials"], resources=[data.workgroup_arn]),
            iam.PolicyStatement(actions=["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement",
                                         "rds-data:BeginTransaction", "rds-data:CommitTransaction",
                                         "rds-data:RollbackTransaction"], resources=[meta.cluster.cluster_arn]),
            iam.PolicyStatement(actions=["secretsmanager:GetSecretValue"], resources=[h_secret.secret_arn]),
            iam.PolicyStatement(actions=["cloudwatch:PutMetricData"], resources=["*"],
                                conditions={"StringLike": {"cloudwatch:namespace": "EQH/*"}}),
            iam.PolicyStatement(actions=["cloudformation:DescribeStacks"], resources=[
                f"arn:aws:cloudformation:{self.region}:{self.account}:stack/EqhDq*/*"]),
            *bedrock_statements(self.region, self.account, cfg),
        ])
        iam.Policy(self, "EvalPolicy", roles=[eval_role], statements=[
            iam.PolicyStatement(actions=["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement",
                                         "rds-data:BeginTransaction", "rds-data:CommitTransaction",
                                         "rds-data:RollbackTransaction"], resources=[meta.cluster.cluster_arn]),
            iam.PolicyStatement(actions=["secretsmanager:GetSecretValue"], resources=[a_secret.secret_arn]),
            iam.PolicyStatement(actions=["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
                                resources=[key.key_arn]),
            iam.PolicyStatement(actions=["s3:PutObject", "s3:GetObject"],
                                resources=[b["dq-results"].arn_for_objects("eval/*")]),
            iam.PolicyStatement(actions=["bedrock:ApplyGuardrail"], resources=["*"]),
            iam.PolicyStatement(actions=["cloudformation:DescribeStacks"], resources=[
                f"arn:aws:cloudformation:{self.region}:{self.account}:stack/EqhDq*/*"]),
            *bedrock_statements(self.region, self.account, cfg),
        ])

        env = {"AWS_REGION": self.region, "AURORA_CLUSTER_ARN": meta.cluster.cluster_arn,
               "AURORA_SECRET_ARN": h_secret.secret_arn, "AURORA_ASSISTANT_SECRET_ARN": a_secret.secret_arn,
               "AURORA_ADMIN_SECRET_ARN": "unused-in-aws", "RS_WORKGROUP": "eqh-dq",
               "RS_ADMIN_SECRET_ARN": "unused-in-aws", "LLM_ENDPOINT": "mantle"}

        def task(name: str, command: list[str], role, cpu=512, mem=1024) -> ecs.FargateTaskDefinition:
            td = ecs.FargateTaskDefinition(self, f"Task-{name}", family=f"eqh-dq-{name}", cpu=cpu,
                                           memory_limit_mib=mem, task_role=role,
                                           runtime_platform=ecs.RuntimePlatform(
                                               cpu_architecture=ecs.CpuArchitecture.X86_64,
                                               operating_system_family=ecs.OperatingSystemFamily.LINUX))
            td.add_container(name, image=image, command=command, environment=env,
                             logging=ecs.LogDrivers.aws_logs(stream_prefix=name, log_group=self.log_group))
            return td

        self.tasks = {
            "profiler": task("profiler", ["python", "-m", "jobs.profiler.profile"], harvest),
            "daily_sync": task("daily_sync", ["python", "-m", "jobs.daily_sync.sync"], harvest, 1024, 2048),
            "enrich": task("enrich", ["python", "-m", "jobs.enrich.enrich"], harvest),
            "llm_smoke": task("llm_smoke", ["python", "-m", "jobs.common.llm"], harvest, 256, 512),
            "eval": task("eval", ["python", "-m", "eval.run_eval", "--upload"], eval_role, 1024, 2048),
        }

        def run(name: str) -> tasks.EcsRunTask:
            return tasks.EcsRunTask(
                self, f"Run-{name}", cluster=self.cluster, task_definition=self.tasks[name],
                launch_target=tasks.EcsFargateLaunchTarget(platform_version=ecs.FargatePlatformVersion.LATEST),
                integration_pattern=sfn.IntegrationPattern.RUN_JOB, subnets=network.egress_subnets,
                security_groups=[self.task_sg], assign_public_ip=False,
                container_overrides=[tasks.ContainerOverride(
                    container_definition=self.tasks[name].default_container,
                    environment=[tasks.TaskEnvironmentVariable(name="RUN_ID",
                                                               value=sfn.JsonPath.string_at("$$.Execution.Name"))])],
                result_path=sfn.JsonPath.DISCARD, task_timeout=sfn.Timeout.duration(cdk.Duration.hours(1)))

        self.topic = sns.Topic(self, "Alerts", topic_name="eqh-dq-pipeline-alerts", master_key=key)
        for email in cfg["budget"]["alert_emails"]:
            self.topic.add_subscription(subs.EmailSubscription(email))
        fail = sfn.Fail(self, "Failed", cause="daily pipeline step failed")
        notify = tasks.SnsPublish(self, "NotifyFailure", topic=self.topic,
                                  message=sfn.TaskInput.from_text("EQH DQ pilot: daily pipeline failed. See Step "
                                                                  "Functions console for eqh-dq-daily."),
                                  result_path=sfn.JsonPath.DISCARD).next(fail)
        chain = run("profiler").add_catch(notify).next(run("daily_sync").add_catch(notify)).next(
            run("enrich").add_catch(notify))
        self.state_machine = sfn.StateMachine(self, "Daily", state_machine_name="eqh-dq-daily",
                                              definition_body=sfn.DefinitionBody.from_chainable(chain),
                                              timeout=cdk.Duration.hours(3))
        cw.Alarm(self, "PipelineFailedAlarm", alarm_name="eqh-dq-daily-failed",
                 metric=self.state_machine.metric_failed(period=cdk.Duration.hours(1)), threshold=1,
                 evaluation_periods=1, treat_missing_data=cw.TreatMissingData.NOT_BREACHING
                 ).add_alarm_action(cwa.SnsAction(self.topic))

        sched_role = iam.Role(self, "SchedulerRole", assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"))
        self.state_machine.grant_start_execution(sched_role)
        p = cfg["pipeline"]
        self.schedule = scheduler.CfnSchedule(
            self, "DailySchedule", name="eqh-dq-daily", schedule_expression=p["schedule_cron"],
            schedule_expression_timezone=p["schedule_tz"], flexible_time_window={"mode": "OFF"},
            state=self.node.try_get_context("schedule_state") or "ENABLED",
            target={"arn": self.state_machine.state_machine_arn, "roleArn": sched_role.role_arn, "input": "{}"})

        cdk.CfnOutput(self, "ClusterName", value=self.cluster.cluster_name)
        cdk.CfnOutput(self, "StateMachineArn", value=self.state_machine.state_machine_arn)
        cdk.CfnOutput(self, "TaskSubnets", value=",".join(network.vpc.select_subnets(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnet_ids))
        cdk.CfnOutput(self, "TaskSecurityGroup", value=self.task_sg.security_group_id)
        for k, td in self.tasks.items():
            cdk.CfnOutput(self, f"TaskDef{k.replace('_', '').title()}", value=td.family)
