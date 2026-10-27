"""Assistant service: Fargate + ALB (CloudFront-only) + CloudFront (HTTPS) + WAF allowlist + Cognito + Guardrail."""
from __future__ import annotations

import json

import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_wafv2 as waf
from aws_cdk import custom_resources as cr
from constructs import Construct

import pilot_config
from stacks.image import REPO
from stacks.pipeline import bedrock_statements

GROUPS = ["analyst", "steward", "actuarial", "restricted_bh"]
PERSONAS = {"demo-analyst": ["analyst"], "demo-steward": ["analyst", "steward"],
            "demo-actuary": ["actuarial"], "demo-bh-analyst": ["analyst", "restricted_bh"]}


class AssistantStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, network, security, meta, **kw) -> None:
        super().__init__(scope, cid, **kw)
        # imported by ARN so grants land on role policies (no cross-stack key-policy cycle)
        key = kms.Key.from_key_arn(self, "Cmk", security.key.key_arn)
        a = cfg["assistant"]
        tag = self.node.try_get_context("image_tag") or "latest"
        image = ecs.ContainerImage.from_ecr_repository(ecr.Repository.from_repository_name(self, "Repo", REPO), tag)

        # ---------------------------------------------------------------- guardrail
        guard = bedrock.CfnGuardrail(
            self, "Guardrail", name="eqh-dq-assistant",
            blocked_input_messaging="This assistant is read-only and can't help with that request.",
            blocked_outputs_messaging="The response was withheld by the assistant's safety policy.",
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(topics_config=[
                bedrock.CfnGuardrail.TopicConfigProperty(
                    name="modify-data-schemas-pipelines", type="DENY",
                    definition="Requests to change, delete, insert, fix, reload or deduplicate data, or to alter "
                               "schemas, catalog entries, comments, permissions or data pipelines.",
                    examples=["Delete the duplicate claims for me", "Drop the legacy_pmpm_2023 table",
                              "Update the comment on core.member", "Rerun the PAYER_LA1 load",
                              "Grant me access to the SDoH table"])]),
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[bedrock.CfnGuardrail.PiiEntityConfigProperty(type=t, action="ANONYMIZE")
                                     for t in ("US_SOCIAL_SECURITY_NUMBER", "EMAIL", "PHONE",
                                               "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER", "CREDIT_DEBIT_CARD_NUMBER")]),
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(filters_config=[
                bedrock.CfnGuardrail.ContentFilterConfigProperty(type="PROMPT_ATTACK", input_strength="HIGH",
                                                                 output_strength="NONE")]))
        guard_v = bedrock.CfnGuardrailVersion(self, "GuardrailVersion", guardrail_identifier=guard.attr_guardrail_id,
                                              description="pilot")

        # ---------------------------------------------------------------- Cognito
        pool = cognito.UserPool(self, "Users", user_pool_name="eqh-dq-assistant", self_sign_up_enabled=False,
                                sign_in_aliases=cognito.SignInAliases(username=True, email=True),
                                password_policy=cognito.PasswordPolicy(min_length=14),
                                mfa=cognito.Mfa.OPTIONAL, mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=False),
                                advanced_security_mode=None, removal_policy=cdk.RemovalPolicy.DESTROY)
        for g in GROUPS:
            cognito.CfnUserPoolGroup(self, f"G-{g}", user_pool_id=pool.user_pool_id, group_name=g)
        domain = pool.add_domain("Domain", cognito_domain=cognito.CognitoDomainOptions(
            domain_prefix=f"eqh-dq-{self.account}"))

        # ---------------------------------------------------------------- ALB + service
        alb_sg = ec2.SecurityGroup(self, "AlbSg", vpc=network.vpc, description="ALB: CloudFront origin-facing only")
        cf_prefix = cr.AwsCustomResource(
            self, "CfPrefixList",
            on_create=cr.AwsSdkCall(service="EC2", action="describeManagedPrefixLists",
                                    parameters={"Filters": [{"Name": "prefix-list-name",
                                                             "Values": ["com.amazonaws.global.cloudfront.origin-facing"]}]},
                                    physical_resource_id=cr.PhysicalResourceId.of("cf-origin-prefix"),
                                    output_paths=["PrefixLists.0.PrefixListId"]),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            install_latest_aws_sdk=False).get_response_field("PrefixLists.0.PrefixListId")
        alb_sg.add_ingress_rule(ec2.Peer.prefix_list(cf_prefix), ec2.Port.tcp(80), "CloudFront only")
        alb = elbv2.ApplicationLoadBalancer(self, "Alb", vpc=network.vpc, internet_facing=True, security_group=alb_sg,
                                            idle_timeout=cdk.Duration.seconds(180), drop_invalid_header_fields=True)
        origin_secret = sm.Secret(self, "OriginVerify", secret_name="eqh-dq/origin-verify", encryption_key=key,
                                  generate_secret_string=sm.SecretStringGenerator(exclude_punctuation=True,
                                                                                  password_length=40))
        session_secret = sm.Secret(self, "SessionSecret", secret_name="eqh-dq/session-secret",
                                   encryption_key=key,
                                   generate_secret_string=sm.SecretStringGenerator(exclude_punctuation=True,
                                                                                   password_length=48))

        # CloudFront in front of the ALB: HTTPS with the default certificate, no caching (SSE streaming).
        acl = self._waf(a["allowed_cidrs"])
        dist = cf.Distribution(
            self, "Cdn", comment="eqh-dq-assistant (prototype)", web_acl_id=acl.attr_arn,
            default_behavior=cf.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    alb, protocol_policy=cf.OriginProtocolPolicy.HTTP_ONLY, read_timeout=cdk.Duration.seconds(120),
                    custom_headers={"X-Origin-Verify": origin_secret.secret_value.unsafe_unwrap()}),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL, cache_policy=cf.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER))
        public_url = f"https://{dist.distribution_domain_name}"

        client = pool.add_client("Web", generate_secret=False, auth_flows=cognito.AuthFlow(user_srp=True),
                                 o_auth=cognito.OAuthSettings(
                                     flows=cognito.OAuthFlows(authorization_code_grant=True),
                                     scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL,
                                             cognito.OAuthScope.PROFILE],
                                     callback_urls=[f"{public_url}/auth/callback"], logout_urls=[f"{public_url}/"]),
                                 prevent_user_existence_errors=True,
                                 id_token_validity=cdk.Duration.hours(1), access_token_validity=cdk.Duration.hours(1))

        role = iam.Role.from_role_name(self, "TaskRole", pilot_config.ASSISTANT_ROLE)
        a_secret = meta.user_secrets["eqh_assistant"]
        iam.Policy(self, "AssistantPolicy", roles=[role], statements=[
            iam.PolicyStatement(actions=["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement",
                                         "rds-data:BeginTransaction", "rds-data:CommitTransaction",
                                         "rds-data:RollbackTransaction"], resources=[meta.cluster.cluster_arn]),
            iam.PolicyStatement(actions=["secretsmanager:GetSecretValue"], resources=[a_secret.secret_arn]),
            iam.PolicyStatement(actions=["kms:Decrypt", "kms:DescribeKey"], resources=[key.key_arn]),
            iam.PolicyStatement(actions=["bedrock:ApplyGuardrail"], resources=[guard.attr_guardrail_arn]),
            *bedrock_statements(self.region, self.account, cfg),
        ])
        cluster = ecs.Cluster.from_cluster_attributes(self, "Cluster", cluster_name="eqh-dq", vpc=network.vpc)
        td = ecs.FargateTaskDefinition(self, "Task", family="eqh-dq-assistant", cpu=a["cpu"],
                                       memory_limit_mib=a["memory"], task_role=role)
        log_group = logs.LogGroup(self, "Logs", log_group_name="/eqh-dq/assistant", encryption_key=key,
                                  retention=logs.RetentionDays.ONE_MONTH, removal_policy=cdk.RemovalPolicy.DESTROY)
        td.add_container("app", image=image, port_mappings=[ecs.PortMapping(container_port=8080)],
                         logging=ecs.LogDrivers.aws_logs(stream_prefix="assistant", log_group=log_group),
                         environment={"AWS_REGION": self.region, "AURORA_CLUSTER_ARN": meta.cluster.cluster_arn,
                                      "AURORA_ASSISTANT_SECRET_ARN": a_secret.secret_arn,
                                      "AURORA_SECRET_ARN": "unused", "AURORA_ADMIN_SECRET_ARN": "unused",
                                      "RS_ADMIN_SECRET_ARN": "unused", "LLM_ENDPOINT": "mantle",
                                      "GUARDRAIL_ID": guard.attr_guardrail_id,
                                      "GUARDRAIL_VERSION": guard_v.attr_version,
                                      "COGNITO_DOMAIN": domain.base_url(), "COGNITO_CLIENT_ID": client.user_pool_client_id,
                                      "COGNITO_USER_POOL_ID": pool.user_pool_id, "PUBLIC_URL": public_url},
                         secrets={"ORIGIN_VERIFY_SECRET": ecs.Secret.from_secrets_manager(origin_secret),
                                  "SESSION_SECRET": ecs.Secret.from_secrets_manager(session_secret)})
        # CDK doesn't add KMS grants for an imported key: the execution role decrypts the two secrets explicitly
        td.add_to_execution_role_policy(iam.PolicyStatement(
            actions=["kms:Decrypt"], resources=[security.key.key_arn],
            conditions={"StringEquals": {"kms:ViaService": f"secretsmanager.{self.region}.amazonaws.com"}}))
        svc_sg = ec2.SecurityGroup(self, "SvcSg", vpc=network.vpc, description="assistant tasks")
        svc_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8080), "from ALB")
        self.service = ecs.FargateService(self, "Service", service_name="eqh-dq-assistant", cluster=cluster,
                                          task_definition=td, desired_count=1, security_groups=[svc_sg],
                                          vpc_subnets=network.egress_subnets, assign_public_ip=False,
                                          circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
                                          min_healthy_percent=0, max_healthy_percent=200)
        listener = alb.add_listener("Http", port=80, open=False)
        listener.add_targets("App", port=8080, protocol=elbv2.ApplicationProtocol.HTTP, targets=[self.service],
                             health_check=elbv2.HealthCheck(path="/health", healthy_http_codes="200"),
                             deregistration_delay=cdk.Duration.seconds(10))
        self.alb = alb

        # Demo personas: passwords generated into Secrets Manager (never printed).
        for name, groups in PERSONAS.items():
            sec = sm.Secret(self, f"Pwd-{name}", secret_name=f"eqh-dq/cognito/{name}", encryption_key=key,
                            generate_secret_string=sm.SecretStringGenerator(
                                secret_string_template=json.dumps({"username": name}), generate_string_key="password",
                                password_length=20, exclude_characters="\"'\\/@ `"))
            u = cognito.CfnUserPoolUser(self, f"U-{name}", user_pool_id=pool.user_pool_id, username=name,
                                        message_action="SUPPRESS")
            for g in groups:
                att = cognito.CfnUserPoolUserToGroupAttachment(self, f"A-{name}-{g}", user_pool_id=pool.user_pool_id,
                                                               username=name, group_name=g)
                att.add_dependency(u)
            # password is set from the secret by scripts/set_demo_passwords.py (CloudFormation does not resolve
            # Secrets Manager dynamic references inside custom-resource properties)

        cdk.CfnOutput(self, "Url", value=public_url)
        cdk.CfnOutput(self, "UserPoolId", value=pool.user_pool_id)
        cdk.CfnOutput(self, "OutGuardrailId", value=guard.attr_guardrail_id)
        cdk.CfnOutput(self, "OutGuardrailVersion", value=guard_v.attr_version)
        cdk.CfnOutput(self, "AlbArn", value=alb.load_balancer_arn)

    def _waf(self, cidrs: list[str]) -> waf.CfnWebACL:
        rules = [waf.CfnWebACL.RuleProperty(
            name="rate-limit", priority=0, action=waf.CfnWebACL.RuleActionProperty(block={}),
            statement=waf.CfnWebACL.StatementProperty(rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                limit=600, aggregate_key_type="IP")),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True, metric_name="eqh-dq-rate", sampled_requests_enabled=True)),
            waf.CfnWebACL.RuleProperty(
                name="aws-common", priority=1, override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                statement=waf.CfnWebACL.StatementProperty(managed_rule_group_statement=
                    waf.CfnWebACL.ManagedRuleGroupStatementProperty(vendor_name="AWS",
                                                                    name="AWSManagedRulesCommonRuleSet",
                                                                    excluded_rules=[waf.CfnWebACL.ExcludedRuleProperty(
                                                                        name="SizeRestrictions_BODY")])),
                visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True, metric_name="eqh-dq-common", sampled_requests_enabled=True))]
        default_allow = "0.0.0.0/0" in cidrs
        if not default_allow:
            ipset = waf.CfnIPSet(self, "AllowList", scope="CLOUDFRONT", ip_address_version="IPV4", addresses=cidrs)
            rules.append(waf.CfnWebACL.RuleProperty(
                name="ip-allowlist", priority=2, action=waf.CfnWebACL.RuleActionProperty(allow={}),
                statement=waf.CfnWebACL.StatementProperty(ip_set_reference_statement=
                                                          waf.CfnWebACL.IPSetReferenceStatementProperty(arn=ipset.attr_arn)),
                visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True, metric_name="eqh-dq-allow", sampled_requests_enabled=True)))
        return waf.CfnWebACL(
            self, "Waf", scope="CLOUDFRONT", name="eqh-dq-assistant",
            default_action=waf.CfnWebACL.DefaultActionProperty(**({"allow": {}} if default_allow else {"block": {}})),
            rules=rules, visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True, metric_name="eqh-dq-waf", sampled_requests_enabled=True))
