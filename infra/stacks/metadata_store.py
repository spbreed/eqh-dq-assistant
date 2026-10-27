"""Aurora PostgreSQL Serverless v2 + pgvector, accessed through the RDS Data API."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from constructs import Construct



def engine_version(v: str) -> rds.AuroraPostgresEngineVersion:
    return getattr(rds.AuroraPostgresEngineVersion, "VER_" + v.replace(".", "_"))


class MetadataStoreStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, network, security, **kw) -> None:
        super().__init__(scope, cid, **kw)
        a = cfg["aurora"]
        sg = ec2.SecurityGroup(self, "AuroraSg", vpc=network.vpc, allow_all_outbound=False,
                               description="Aurora metadata store (Data API only; no inbound rules)")
        self.cluster = rds.DatabaseCluster(
            self, "Cluster", cluster_identifier="eqh-dq-metadata",
            engine=rds.DatabaseClusterEngine.aurora_postgres(version=engine_version(a["engine_version"])),
            credentials=rds.Credentials.from_generated_secret("eqh_admin", secret_name="eqh-dq/aurora-admin",
                                                              encryption_key=security.key),
            default_database_name="eqh_meta",
            writer=rds.ClusterInstance.serverless_v2("writer", publicly_accessible=False),
            serverless_v2_min_capacity=a["min_acu"], serverless_v2_max_capacity=a["max_acu"],
            vpc=network.vpc, vpc_subnets=network.isolated_subnets, security_groups=[sg],
            storage_encrypted=True, storage_encryption_key=security.key, enable_data_api=True,
            iam_authentication=True, deletion_protection=False,
            backup=rds.BackupProps(retention=cdk.Duration.days(1)),
            removal_policy=cdk.RemovalPolicy.DESTROY)
        self.secret = self.cluster.secret
        # Least-privilege DB users (roles + grants are created by metadata_store/migrate.py):
        #   eqh_harvest   -> pipeline jobs: read/write metadata tables, no DDL
        #   eqh_assistant -> assistant: SELECT everywhere; writes only steward review fields + review_action
        self.user_secrets = {}
        for user in ("eqh_harvest", "eqh_assistant"):
            s = rds.DatabaseSecret(self, f"Secret-{user}", username=user, secret_name=f"eqh-dq/aurora-{user}",
                                   encryption_key=security.key, master_secret=self.secret,
                                   exclude_characters="\"'\\/@ `%")
            s.attach(self.cluster)
            self.user_secrets[user] = s
            cdk.CfnOutput(self, f"SecretArn{user.split('_')[1].title()}", value=s.secret_arn)
        cdk.CfnOutput(self, "ClusterArn", value=self.cluster.cluster_arn)
        cdk.CfnOutput(self, "SecretArn", value=self.secret.secret_arn)
