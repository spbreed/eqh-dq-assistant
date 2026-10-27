#!/usr/bin/env python3
"""Generate Resources.md: every AWS resource of the pilot (from CloudFormation) with an AWS console link."""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jobs.common import settings  # noqa: E402

S = settings.get()
R, ACCT = S["region"], S["account_id"]
C = f"https://{R}.console.aws.amazon.com"
STACKS = ["EqhDqSecurity", "EqhDqNetwork", "EqhDqImage", "EqhDqDataPlatform", "EqhDqMetadataStore", "EqhDqPipeline",
          "EqhDqAssistant", "EqhDqObservability"]
SKIP = {"AWS::CDK::Metadata", "AWS::IAM::Policy", "AWS::Lambda::Permission", "AWS::EC2::SubnetRouteTableAssociation",
        "AWS::EC2::Route", "AWS::EC2::VPCGatewayAttachment", "AWS::S3::BucketPolicy", "AWS::KMS::Alias",
        "AWS::Cognito::UserPoolUserToGroupAttachment", "AWS::SecretsManager::SecretTargetAttachment",
        "AWS::ApplicationAutoScaling::ScalableTarget", "AWS::EC2::SecurityGroupIngress",
        "AWS::EC2::SecurityGroupEgress", "AWS::SNS::TopicPolicy", "Custom::S3AutoDeleteObjects"}


def link(t: str, pid: str) -> str:
    p = quote(pid, safe="")
    m = {
        "AWS::S3::Bucket": f"https://s3.console.aws.amazon.com/s3/buckets/{pid}?region={R}",
        "AWS::KMS::Key": f"{C}/kms/home?region={R}#/kms/keys/{pid}",
        "AWS::IAM::Role": f"https://console.aws.amazon.com/iam/home#/roles/details/{pid}",
        "AWS::IAM::ManagedPolicy": f"https://console.aws.amazon.com/iam/home#/policies/details/{p}",
        "AWS::CloudTrail::Trail": f"{C}/cloudtrailv2/home?region={R}#/trails/{p}",
        "AWS::Logs::LogGroup": f"{C}/cloudwatch/home?region={R}#logsV2:log-groups/log-group/{quote(p, safe='')}",
        "AWS::Budgets::Budget": "https://console.aws.amazon.com/billing/home#/budgets",
        "AWS::Budgets::BudgetsAction": "https://console.aws.amazon.com/billing/home#/budgets",
        "AWS::EC2::VPC": f"{C}/vpcconsole/home?region={R}#VpcDetails:VpcId={pid}",
        "AWS::EC2::Subnet": f"{C}/vpcconsole/home?region={R}#SubnetDetails:subnetId={pid}",
        "AWS::EC2::NatGateway": f"{C}/vpcconsole/home?region={R}#NatGatewayDetails:natGatewayId={pid}",
        "AWS::EC2::VPCEndpoint": f"{C}/vpcconsole/home?region={R}#EndpointDetails:vpcEndpointId={pid}",
        "AWS::EC2::SecurityGroup": f"{C}/ec2/home?region={R}#SecurityGroup:groupId={pid}",
        "AWS::Glue::Database": f"{C}/glue/home?region={R}#/v2/data-catalog/databases/view/{pid}",
        "AWS::RedshiftServerless::Namespace": f"{C}/redshiftv2/home?region={R}#serverless-namespace-details?namespace={pid}",
        "AWS::RedshiftServerless::Workgroup": f"{C}/redshiftv2/home?region={R}#serverless-workgroup-details?workgroup={pid}",
        "AWS::SecretsManager::Secret": f"{C}/secretsmanager/secret?name={p}&region={R}",
        "AWS::RDS::DBCluster": f"{C}/rds/home?region={R}#database:id={pid};is-cluster=true",
        "AWS::RDS::DBInstance": f"{C}/rds/home?region={R}#database:id={pid};is-cluster=false",
        "AWS::ECR::Repository": f"{C}/ecr/repositories/private/{ACCT}/{pid}?region={R}",
        "AWS::CodeBuild::Project": f"{C}/codesuite/codebuild/{ACCT}/projects/{pid}?region={R}",
        "AWS::ECS::Cluster": f"{C}/ecs/v2/clusters/{pid}?region={R}",
        "AWS::ECS::Service": f"{C}/ecs/v2/clusters/eqh-dq/services/eqh-dq-assistant?region={R}",
        "AWS::ECS::TaskDefinition": f"{C}/ecs/v2/task-definitions/{pid.split('/')[-1].split(':')[0]}?region={R}",
        "AWS::StepFunctions::StateMachine": f"{C}/states/home?region={R}#/statemachines/view/{p}",
        "AWS::Scheduler::Schedule": f"{C}/scheduler/home?region={R}#schedules/default/{pid}",
        "AWS::SNS::Topic": f"{C}/sns/v3/home?region={R}#/topic/{pid}",
        "AWS::CloudWatch::Alarm": f"{C}/cloudwatch/home?region={R}#alarmsV2:alarm/{p}",
        "AWS::CloudWatch::Dashboard": f"{C}/cloudwatch/home?region={R}#dashboards/dashboard/{pid}",
        "AWS::Cognito::UserPool": f"{C}/cognito/v2/idp/user-pools/{pid}/info?region={R}",
        "AWS::Bedrock::Guardrail": f"{C}/bedrock/home?region={R}#/guardrails",
        "AWS::CloudFront::Distribution": f"https://console.aws.amazon.com/cloudfront/v4/home#/distributions/{pid}",
        "AWS::WAFv2::WebACL": f"https://console.aws.amazon.com/wafv2/homev2/web-acls?region=global",
        "AWS::ElasticLoadBalancingV2::LoadBalancer": f"{C}/ec2/home?region={R}#LoadBalancers:",
        "AWS::Lambda::Function": f"{C}/lambda/home?region={R}#/functions/{pid}",
    }
    return m.get(t, f"{C}/cloudformation/home?region={R}")


def main() -> None:
    cf = boto3.client("cloudformation", region_name=R)
    out = [f"# Resources — EQH DQ Assistant pilot\n",
           f"AWS account `{ACCT}`, region `{R}`. All resources are tagged `project=eqh-dq-assistant`, `env=pilot`, "
           f"`owner={S.get('owner', 'karthik.ramamurthy@emergertech.com')}`, `data=synthetic` and are created by the CDK app in "
           f"`infra/` (regenerate this file with `python scripts/gen_resources.py`). Generated "
           f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}.\n"]
    outs = {}
    for st in STACKS:
        try:
            d = cf.describe_stacks(StackName=st)["Stacks"][0]
            outs[st] = {o["OutputKey"]: o["OutputValue"] for o in d.get("Outputs", [])}
        except Exception:  # noqa: BLE001
            outs[st] = None
    url = (outs.get("EqhDqAssistant") or {}).get("Url", "")
    out.append("## Entry points\n")
    out.append("| What | Link |\n|---|---|")
    out += [f"| Assistant (CloudFront, Cognito login) | {url} |",
            f"| CloudWatch dashboard | {C}/cloudwatch/home?region={R}#dashboards/dashboard/eqh-dq-assistant |",
            f"| Step Functions daily pipeline | {C}/states/home?region={R}#/statemachines |",
            f"| Budget `eqh-dq-assistant-monthly` ($300) | https://console.aws.amazon.com/billing/home#/budgets |",
            f"| Redshift Query Editor v2 (workgroup `eqh-dq`, db `eqh`) | {C}/sqlworkbench/home?region={R} |",
            f"| Aurora metadata store (Data API query editor) | {C}/rds/home?region={R}#query-editor: |",
            f"| Glue Data Catalog (`eqh_raw`, `eqh_silver`) | {C}/glue/home?region={R}#/v2/data-catalog/databases |",
            f"| Glue Data Quality rulesets | {C}/glue/home?region={R}#/v2/data-catalog/dataquality |",
            f"| Bedrock guardrails / model access | {C}/bedrock/home?region={R}#/guardrails |",
            f"| Eval report (S3) | https://s3.console.aws.amazon.com/s3/object/{S['bucket_dq']}?region={R}&prefix=eval/latest/report.html |",
            f"| GitHub repository | https://github.com/spbreed/eqh-dq-assistant |", ""]
    for st in STACKS:
        if outs.get(st) is None:
            continue
        res = [r for p in cf.get_paginator("list_stack_resources").paginate(StackName=st)
               for r in p["StackResourceSummaries"]]
        groups = defaultdict(list)
        for r in res:
            if r["ResourceType"] in SKIP or r["ResourceType"].startswith("Custom::") and "AWS" not in r["ResourceType"]:
                continue
            groups[r["ResourceType"]].append(r)
        out.append(f"## {st} ({len(res)} CloudFormation resources)\n")
        out.append(f"[CloudFormation stack]({C}/cloudformation/home?region={R}#/stacks/stackinfo?stackId={quote(st)})\n")
        out.append("| Type | Logical ID | Physical ID | Console |\n|---|---|---|---|")
        for t in sorted(groups):
            for r in sorted(groups[t], key=lambda x: x["LogicalResourceId"]):
                pid = r.get("PhysicalResourceId", "")
                short = pid if len(pid) < 70 else pid[:30] + "…" + pid[-30:]
                out.append(f"| `{t.replace('AWS::', '')}` | {r['LogicalResourceId']} | `{short}` | [open]({link(t, pid)}) |")
        if outs[st]:
            out.append("\n**Outputs:** " + "; ".join(f"`{k}` = `{v}`" for k, v in sorted(outs[st].items())
                                                    if not k.startswith("ExportsOutput")))
        out.append("")
    out.append("## Created outside CloudFormation (data / catalog objects)\n")
    out.append("| Object | Where | Created by |\n|---|---|---|")
    out += [f"| 47 raw feed tables + 19 silver tables, daily partitions | Glue `eqh_raw`, `eqh_silver` | `datagen/catalog.py` |",
            f"| 7 Glue DQ rulesets `eqh_silver_*` | Glue Data Quality | `datagen/glue_dq.py` |",
            f"| Schemas `core`, `careempower`, `vbc_mart`, `outbound`, external `spectrum_silver`; datashares `eqh_actuarial_share`, `eqh_finance_share`; consumer users | Redshift `eqh` | `sql/redshift/*.sql`, `datagen/load.py` |",
            f"| Metadata store schema + roles `eqh_harvest`, `eqh_assistant` | Aurora `eqh_meta` | `metadata_store/migrate.py` |",
            f"| Bedrock model-invocation logging config | Bedrock account setting | `EqhDqSecurity` custom resource |",
            f"| Marketplace agreements for GPT‑5.6 Terra/Luna/Sol | AWS Marketplace | accepted 2026-10-27 (see docs/DECISIONS.md D‑01) |",
            f"| CDK bootstrap stack `CDKToolkit` | CloudFormation | `cdk bootstrap` (kept by `make destroy`) |", ""]
    open(os.path.join(os.path.dirname(__file__), "..", "Resources.md"), "w").write("\n".join(out))
    print("wrote Resources.md")


if __name__ == "__main__":
    main()
