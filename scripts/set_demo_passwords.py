#!/usr/bin/env python3
"""Set each demo persona's Cognito password from its Secrets Manager secret (eqh-dq/cognito/<user>). Never prints it."""
import json
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jobs.common import settings  # noqa: E402

PERSONAS = ["demo-analyst", "demo-steward", "demo-actuary", "demo-bh-analyst"]
r = settings.get()["region"]
cf, sm, idp = (boto3.client(x, region_name=r) for x in ("cloudformation", "secretsmanager", "cognito-idp"))
outs = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName="EqhDqAssistant")["Stacks"][0]["Outputs"]}
for u in PERSONAS:
    pw = json.loads(sm.get_secret_value(SecretId=f"eqh-dq/cognito/{u}")["SecretString"])["password"]
    idp.admin_set_user_password(UserPoolId=outs["UserPoolId"], Username=u, Password=pw, Permanent=True)
    print(f"{u}: password set from secret eqh-dq/cognito/{u}")
