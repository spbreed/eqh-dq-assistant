#!/usr/bin/env python3
import aws_cdk as cdk

import pilot_config
from stacks.assistant import AssistantStack
from stacks.data_platform import DataPlatformStack
from stacks.image import ImageStack
from stacks.metadata_store import MetadataStoreStack
from stacks.network import NetworkStack
from stacks.observability import ObservabilityStack
from stacks.pipeline import PipelineStack
from stacks.security import SecurityStack

cfg = pilot_config.load()
app = cdk.App()
env = cdk.Environment(account=cfg["account_id"], region=cfg["region"])

for k, v in {"project": cfg["project"], "env": cfg["env"], "owner": cfg["owner"], "data": "synthetic"}.items():
    cdk.Tags.of(app).add(k, v)

p = "EqhDq"
security = SecurityStack(app, f"{p}Security", cfg=cfg, env=env)
network = NetworkStack(app, f"{p}Network", cfg=cfg, env=env)
ImageStack(app, f"{p}Image", cfg=cfg, env=env)
data = DataPlatformStack(app, f"{p}DataPlatform", cfg=cfg, network=network, security=security, env=env)
meta = MetadataStoreStack(app, f"{p}MetadataStore", cfg=cfg, network=network, security=security, env=env)
pipeline = PipelineStack(app, f"{p}Pipeline", cfg=cfg, network=network, security=security, data=data, meta=meta,
                         env=env)
assistant = AssistantStack(app, f"{p}Assistant", cfg=cfg, network=network, security=security, meta=meta, env=env)
ObservabilityStack(app, f"{p}Observability", cfg=cfg, pipeline=pipeline, assistant=assistant, env=env)

app.synth()
