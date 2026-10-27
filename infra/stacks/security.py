"""KMS CMK, workload IAM roles, CloudTrail, Bedrock invocation logging, AWS Budget + budget action."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudtrail as cloudtrail
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import custom_resources as cr
from constructs import Construct

import pilot_config
from pilot_config import ASSISTANT_ROLE, EVAL_ROLE, HARVEST_ROLE, REDSHIFT_ROLE

DATA_BUCKETS = ("raw", "silver", "extracts", "glossary", "dq-results")


class SecurityStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, **kw) -> None:
        super().__init__(scope, cid, **kw)
        self.cfg = cfg

        self.key = kms.Key(self, "Cmk", alias="alias/eqh-dq-assistant", enable_key_rotation=True,
                           removal_policy=cdk.RemovalPolicy.DESTROY, pending_window=cdk.Duration.days(7))
        # Bedrock invocation logs and the pipeline's log groups are encrypted with the CMK.
        self.key.add_to_resource_policy(iam.PolicyStatement(
            principals=[iam.ServicePrincipal(f"logs.{self.region}.amazonaws.com")],
            actions=["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"],
            resources=["*"],
            conditions={"ArnLike": {"kms:EncryptionContext:aws:logs:arn":
                                    f"arn:aws:logs:{self.region}:{self.account}:log-group:*"}}))

        # ---------------------------------------------------------------- workload roles
        # Permissions are attached in the stacks that own the resources; the roles live here so the
        # budget action can target them.
        ecs_tasks = iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        self.harvest_role = iam.Role(self, "HarvestRole", role_name=HARVEST_ROLE, assumed_by=ecs_tasks,
                                     description="profiler / daily_sync / enrich: read-only metadata harvest")
        self.assistant_role = iam.Role(self, "AssistantRole", role_name=ASSISTANT_ROLE, assumed_by=ecs_tasks,
                                       description="assistant service: metadata store + Bedrock only")
        self.eval_role = iam.Role(self, "EvalRole", role_name=EVAL_ROLE, assumed_by=ecs_tasks,
                                  description="eval harness: assistant permissions + eval report upload")
        self.redshift_role = iam.Role(self, "RedshiftRole", role_name=REDSHIFT_ROLE,
                                      assumed_by=iam.CompositePrincipal(
                                          iam.ServicePrincipal("redshift.amazonaws.com"),
                                          iam.ServicePrincipal("redshift-serverless.amazonaws.com")),
                                      description="Redshift COPY + Spectrum (read raw/silver, Glue catalog)")

        self._budget(cfg)
        self._cloudtrail(cfg)
        self._bedrock_logging()

    # ---------------------------------------------------------------- budget + limits
    def _budget(self, cfg: dict) -> None:
        b = cfg["budget"]
        name = "eqh-dq-assistant-monthly"
        subscribers = [{"subscriptionType": "EMAIL", "address": a} for a in b["alert_emails"]]
        notifications = [
            budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    comparison_operator="GREATER_THAN", notification_type="ACTUAL",
                    threshold=pct, threshold_type="PERCENTAGE"),
                subscribers=subscribers)
            for pct in b["alert_thresholds_pct"]
        ]
        notifications.append(budgets.CfnBudget.NotificationWithSubscribersProperty(
            notification=budgets.CfnBudget.NotificationProperty(
                comparison_operator="GREATER_THAN", notification_type="FORECASTED",
                threshold=100, threshold_type="PERCENTAGE"),
            subscribers=subscribers))
        budget = budgets.CfnBudget(self, "Budget", budget=budgets.CfnBudget.BudgetDataProperty(
            budget_name=name, budget_type="COST", time_unit="MONTHLY",
            budget_limit=budgets.CfnBudget.SpendProperty(amount=b["monthly_usd"], unit="USD")),
            notifications_with_subscribers=notifications)

        # "Limit": at 100% ACTUAL, Budgets automatically attaches this deny policy to the workload roles,
        # which stops new Bedrock calls, task launches and Redshift queries made by the pilot.
        deny = iam.ManagedPolicy(self, "BudgetDeny", managed_policy_name="eqh-dq-budget-deny",
                                 description="Attached by AWS Budgets when the pilot budget is exhausted",
                                 statements=[iam.PolicyStatement(effect=iam.Effect.DENY, resources=["*"], actions=[
                                     "bedrock:*", "ecs:RunTask", "states:StartExecution",
                                     "redshift-data:*", "redshift-serverless:GetCredentials"])])
        exec_role = iam.Role(self, "BudgetActionRole", assumed_by=iam.ServicePrincipal("budgets.amazonaws.com"))
        exec_role.add_to_policy(iam.PolicyStatement(
            actions=["iam:AttachRolePolicy", "iam:DetachRolePolicy"],
            resources=[r.role_arn for r in (self.harvest_role, self.assistant_role, self.redshift_role,
                                            self.eval_role)],
            conditions={"ArnEquals": {"iam:PolicyARN": deny.managed_policy_arn}}))
        action = budgets.CfnBudgetsAction(
            self, "BudgetDenyAction", budget_name=name, action_type="APPLY_IAM_POLICY",
            notification_type="ACTUAL", approval_model="AUTOMATIC", execution_role_arn=exec_role.role_arn,
            action_threshold={"type": "PERCENTAGE", "value": b["enforce_deny_at_pct"]},
            definition={"iamActionDefinition": {
                "policyArn": deny.managed_policy_arn,
                "roles": [self.harvest_role.role_name, self.assistant_role.role_name, self.redshift_role.role_name,
                          self.eval_role.role_name]}},
            subscribers=[{"type": "EMAIL", "address": a} for a in b["alert_emails"]])
        action.add_dependency(budget)

    # ---------------------------------------------------------------- audit
    def _cloudtrail(self, cfg: dict) -> None:
        bucket = s3.Bucket(self, "TrailBucket", encryption=s3.BucketEncryption.S3_MANAGED,
                           block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
                           removal_policy=cdk.RemovalPolicy.DESTROY, auto_delete_objects=True,
                           lifecycle_rules=[s3.LifecycleRule(expiration=cdk.Duration.days(90))])
        trail = cloudtrail.Trail(self, "Trail", trail_name="eqh-dq-assistant", bucket=bucket,
                                 is_multi_region_trail=False, include_global_service_events=True)
        # S3 data events on the data buckets only (names are deterministic, see pilot_config.bucket_name).
        for kind in DATA_BUCKETS:
            trail.add_s3_event_selector(
                [cloudtrail.S3EventSelector(bucket=s3.Bucket.from_bucket_name(
                    self, f"Sel{kind}", pilot_config.bucket_name(cfg, kind)))],
                include_management_events=True)

    def _bedrock_logging(self) -> None:
        group = logs.LogGroup(self, "BedrockInvocationLogs", log_group_name="/eqh-dq/bedrock-invocations",
                              retention=logs.RetentionDays.ONE_MONTH, encryption_key=self.key,
                              removal_policy=cdk.RemovalPolicy.DESTROY)
        role = iam.Role(self, "BedrockLoggingRole", assumed_by=iam.ServicePrincipal(
            "bedrock.amazonaws.com", conditions={"StringEquals": {"aws:SourceAccount": self.account}}))
        group.grant_write(role)
        params = {"loggingConfig": {
            "cloudWatchConfig": {"logGroupName": group.log_group_name, "roleArn": role.role_arn},
            "textDataDeliveryEnabled": True, "imageDataDeliveryEnabled": False,
            "embeddingDataDeliveryEnabled": False}}
        cr.AwsCustomResource(
            self, "BedrockLoggingConfig",
            on_create=cr.AwsSdkCall(service="Bedrock", action="putModelInvocationLoggingConfiguration",
                                    parameters=params,
                                    physical_resource_id=cr.PhysicalResourceId.of("eqh-dq-bedrock-logging")),
            on_update=cr.AwsSdkCall(service="Bedrock", action="putModelInvocationLoggingConfiguration",
                                    parameters=params,
                                    physical_resource_id=cr.PhysicalResourceId.of("eqh-dq-bedrock-logging")),
            on_delete=cr.AwsSdkCall(service="Bedrock", action="deleteModelInvocationLoggingConfiguration"),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(actions=["bedrock:PutModelInvocationLoggingConfiguration",
                                             "bedrock:DeleteModelInvocationLoggingConfiguration"],
                                    resources=["*"]),
                iam.PolicyStatement(actions=["iam:PassRole"], resources=[role.role_arn])]),
            install_latest_aws_sdk=False)
        self.bedrock_log_group = group
