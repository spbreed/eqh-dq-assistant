"""Container image built inside AWS: ECR repo + ECR Public pull-through cache + CodeBuild.

The repo source is uploaded as a CDK S3 asset; scripts/build_image.sh starts the CodeBuild project and tags the
image with the asset hash, which the Pipeline/Assistant stacks consume via the `image_tag` context value.
(Building in AWS avoids anonymous registry rate limits and keeps registry credentials off developer machines.)
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_codebuild as cb
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3_assets as s3a
from constructs import Construct

import pilot_config

REPO = "eqh-dq-assistant"


class ImageStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: dict, **kw) -> None:
        super().__init__(scope, cid, **kw)
        self.repo = ecr.Repository(self, "Repo", repository_name=REPO, image_scan_on_push=True,
                                   removal_policy=cdk.RemovalPolicy.DESTROY, empty_on_delete=True,
                                   lifecycle_rules=[ecr.LifecycleRule(max_image_count=10)])
        ecr.CfnPullThroughCacheRule(self, "EcrPublicCache", ecr_repository_prefix="ecr-public",
                                    upstream_registry_url="public.ecr.aws")
        src = s3a.Asset(self, "Source", path=str(pilot_config.ROOT), exclude=[
            ".venv", "build", "infra/cdk.out", "**/__pycache__", ".git", "*.parquet", "eval/results"])
        base = f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/ecr-public/docker/library/python:3.12-slim"
        project = cb.Project(
            self, "Build", project_name="eqh-dq-image-build",
            source=cb.Source.s3(bucket=src.bucket, path=src.s3_object_key),
            environment=cb.BuildEnvironment(build_image=cb.LinuxBuildImage.STANDARD_7_0, privileged=True,
                                            compute_type=cb.ComputeType.SMALL),
            environment_variables={"REPO_URI": cb.BuildEnvironmentVariable(value=self.repo.repository_uri),
                                   "BASE_IMAGE": cb.BuildEnvironmentVariable(value=base),
                                   "IMAGE_TAG": cb.BuildEnvironmentVariable(value=src.asset_hash[:16])},
            build_spec=cb.BuildSpec.from_object({"version": "0.2", "phases": {
                "pre_build": {"commands": [
                    "aws ecr get-login-password | docker login --username AWS --password-stdin ${REPO_URI%%/*}"]},
                "build": {"commands": [
                    "docker build --build-arg BASE_IMAGE=$BASE_IMAGE -t $REPO_URI:$IMAGE_TAG .",
                    "docker push $REPO_URI:$IMAGE_TAG"]}}}),
            timeout=cdk.Duration.minutes(30))
        self.repo.grant_pull_push(project)
        project.add_to_role_policy(iam.PolicyStatement(
            actions=["ecr:BatchImportUpstreamImage", "ecr:CreateRepository", "ecr:BatchGetImage",
                     "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"],
            resources=[f"arn:aws:ecr:{self.region}:{self.account}:repository/ecr-public/*"]))
        project.add_to_role_policy(iam.PolicyStatement(actions=["ecr:GetAuthorizationToken"], resources=["*"]))
        cdk.CfnOutput(self, "ImageTag", value=src.asset_hash[:16])
        cdk.CfnOutput(self, "RepoUri", value=self.repo.repository_uri)
        cdk.CfnOutput(self, "BuildProject", value=project.project_name)
