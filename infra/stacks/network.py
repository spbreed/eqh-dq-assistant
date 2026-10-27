"""VPC, subnets, NAT and VPC endpoints."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, **kw) -> None:
        super().__init__(scope, cid, **kw)
        net = cfg["network"]
        # Redshift Serverless requires subnets in 3 AZs; NAT and interface endpoints stay in fewer AZs for cost.
        self.vpc = ec2.Vpc(
            self, "Vpc", vpc_name="eqh-dq-assistant", max_azs=3, nat_gateways=net["nat_gateways"],
            ip_addresses=ec2.IpAddresses.cidr("10.42.0.0/16"),
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="egress", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=22),
                ec2.SubnetConfiguration(name="isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=22),
            ])
        self.vpc.add_gateway_endpoint("S3", service=ec2.GatewayVpcEndpointAwsService.S3)

        azs = self.vpc.availability_zones[: net["endpoint_azs"]]
        self.endpoint_sg = ec2.SecurityGroup(self, "EndpointSg", vpc=self.vpc, allow_all_outbound=False,
                                             description="Interface endpoints: HTTPS from inside the VPC")
        self.endpoint_sg.add_ingress_rule(ec2.Peer.ipv4(self.vpc.vpc_cidr_block), ec2.Port.tcp(443))
        services = {
            "Glue": ec2.InterfaceVpcEndpointAwsService.GLUE,
            "SecretsManager": ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            "Sts": ec2.InterfaceVpcEndpointAwsService.STS,
            "Logs": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            "EcrApi": ec2.InterfaceVpcEndpointAwsService.ECR,
            "EcrDkr": ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            "RedshiftData": ec2.InterfaceVpcEndpointAwsService.REDSHIFT_DATA,
            "RdsData": ec2.InterfaceVpcEndpointAwsService.RDS_DATA,
            "BedrockRuntime": ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
        }
        for name, svc in services.items():
            self.vpc.add_interface_endpoint(
                name, service=svc, private_dns_enabled=True, security_groups=[self.endpoint_sg],
                subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, availability_zones=azs))
        # bedrock-mantle (*.api.aws) is reached through the NAT: see docs/DECISIONS.md (PrivateLink).

        self.egress_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        self.isolated_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)
        cdk.CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
