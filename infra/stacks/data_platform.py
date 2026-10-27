"""S3 medallion buckets, Glue databases, Redshift Serverless namespace/workgroup, COPY/Spectrum role."""
from __future__ import annotations

import json

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_redshiftserverless as rss
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import custom_resources as cr
from constructs import Construct

import pilot_config
from stacks.security import DATA_BUCKETS

NAMESPACE = "eqh-dq"
WORKGROUP = "eqh-dq"


class DataPlatformStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, network, security, **kw) -> None:
        super().__init__(scope, cid, **kw)
        rcfg = cfg["redshift"]
        key = security.key

        self.buckets: dict[str, s3.Bucket] = {}
        for kind in DATA_BUCKETS:
            self.buckets[kind] = s3.Bucket(
                self, f"Bucket-{kind}", bucket_name=pilot_config.bucket_name(cfg, kind),
                encryption=s3.BucketEncryption.KMS, encryption_key=key, bucket_key_enabled=True,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True, versioned=False,
                removal_policy=cdk.RemovalPolicy.DESTROY, auto_delete_objects=True)

        for db, desc in (("eqh_raw", "Raw payer/HIE/EHR feeds, one table per feed, partitioned by ingest_date"),
                         ("eqh_silver", "Conformed silver entities")):
            glue.CfnDatabase(self, f"Db-{db}", catalog_id=self.account,
                             database_input=glue.CfnDatabase.DatabaseInputProperty(name=db, description=desc))

        # ---------------------------------------------------------------- Redshift Serverless
        rs_role = iam.Role.from_role_name(self, "RsRole", pilot_config.REDSHIFT_ROLE)
        iam.Policy(self, "RedshiftRolePolicy", roles=[rs_role], statements=[
            iam.PolicyStatement(actions=["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
                                resources=[b.bucket_arn for b in self.buckets.values()]
                                + [b.arn_for_objects("*") for b in self.buckets.values()]),
            iam.PolicyStatement(actions=["kms:Decrypt", "kms:DescribeKey"], resources=[key.key_arn]),
            iam.PolicyStatement(actions=["glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables",
                                         "glue:GetPartition", "glue:GetPartitions", "glue:BatchGetPartition"],
                                resources=[f"arn:aws:glue:{self.region}:{self.account}:catalog",
                                           f"arn:aws:glue:{self.region}:{self.account}:database/eqh_*",
                                           f"arn:aws:glue:{self.region}:{self.account}:table/eqh_*/*"]),
        ])

        # Glue Data Quality evaluations (rulesets are created by datagen/glue_dq.py)
        glue_dq_role = iam.Role(self, "GlueDqRole", role_name="eqh-dq-glue-dq-role",
                                assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
                                managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                                    "service-role/AWSGlueServiceRole")])
        self.buckets["silver"].grant_read(glue_dq_role)
        self.buckets["dq-results"].grant_read_write(glue_dq_role)
        key.grant_decrypt(glue_dq_role)

        self.admin_secret = sm.Secret(
            self, "RedshiftAdminSecret", secret_name="eqh-dq/redshift-admin", encryption_key=key,
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "eqh_admin"}), generate_string_key="password",
                exclude_characters="\"'\\/@ `", password_length=32, require_each_included_type=True))

        self.rs_sg = ec2.SecurityGroup(self, "RedshiftSg", vpc=network.vpc, allow_all_outbound=False,
                                       description="Redshift Serverless (Data API only; no inbound needed)")
        # Enhanced VPC routing: COPY/Spectrum reach S3 via the gateway endpoint and Glue/STS via interface
        # endpoints. Isolated subnets have no internet route, so HTTPS egress stays inside AWS.
        self.rs_sg.add_egress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "S3 gateway + VPC endpoints")
        ns = rss.CfnNamespace(
            self, "Namespace", namespace_name=NAMESPACE, db_name=rcfg["database"],
            admin_username="eqh_admin",
            admin_user_password=self.admin_secret.secret_value_from_json("password").unsafe_unwrap(),
            iam_roles=[rs_role.role_arn], default_iam_role_arn=rs_role.role_arn, kms_key_id=key.key_arn,
            log_exports=["userlog", "connectionlog", "useractivitylog"])
        ns.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        wg = rss.CfnWorkgroup(
            self, "Workgroup", workgroup_name=WORKGROUP, namespace_name=NAMESPACE,
            base_capacity=rcfg["base_rpu"], max_capacity=rcfg["max_rpu"], publicly_accessible=False,
            enhanced_vpc_routing=True, subnet_ids=network.vpc.select_subnets(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids,
            security_group_ids=[self.rs_sg.security_group_id],
            config_parameters=[rss.CfnWorkgroup.ConfigParameterProperty(
                parameter_key="enable_user_activity_logging", parameter_value="true")])
        wg.add_dependency(ns)
        wg.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        self.workgroup_arn = wg.attr_workgroup_workgroup_arn

        # Hard usage limit: deactivate the workgroup when monthly RPU-hours are exhausted.
        limit = cr.AwsCustomResource(
            self, "RpuUsageLimit",
            on_create=cr.AwsSdkCall(
                service="RedshiftServerless", action="createUsageLimit",
                parameters={"resourceArn": wg.attr_workgroup_workgroup_arn, "usageType": "serverless-compute",
                            "amount": rcfg["monthly_rpu_hour_limit"], "period": "monthly",
                            "breachAction": "deactivate"},
                physical_resource_id=cr.PhysicalResourceId.from_response("usageLimit.usageLimitId")),
            on_delete=cr.AwsSdkCall(service="RedshiftServerless", action="deleteUsageLimit",
                                    parameters={"usageLimitId": cr.PhysicalResourceIdReference()}),
            policy=cr.AwsCustomResourcePolicy.from_statements([iam.PolicyStatement(
                actions=["redshift-serverless:CreateUsageLimit", "redshift-serverless:DeleteUsageLimit"],
                resources=["*"])]),
            install_latest_aws_sdk=False)
        limit.node.add_dependency(wg)

        cdk.CfnOutput(self, "RedshiftWorkgroup", value=WORKGROUP)
        cdk.CfnOutput(self, "RedshiftAdminSecretArn", value=self.admin_secret.secret_arn)
        for kind, b in self.buckets.items():
            cdk.CfnOutput(self, f"Bucket{kind.replace('-', '')}", value=b.bucket_name)
