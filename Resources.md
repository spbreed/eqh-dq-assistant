# Resources — EQH DQ Assistant pilot

AWS account `761705103792`, region `us-east-1`. All resources are tagged `project=eqh-dq-assistant`, `env=pilot`, `owner=karthik.ramamurthy@emergertech.com`, `data=synthetic` and are created by the CDK app in `infra/` (regenerate this file with `python scripts/gen_resources.py`). Generated 2026-11-03 18:16 UTC.

## Entry points

| What | Link |
|---|---|
| Assistant (CloudFront, Cognito login) | https://do3jeqzux8by1.cloudfront.net |
| Pitch deck (reveal.js, always the latest on `main`) | https://raw.githack.com/spbreed/eqh-dq-assistant/refs/heads/main/eqh-dq-assistant.html#/1 |
| CloudWatch dashboard | https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards/dashboard/eqh-dq-assistant |
| Step Functions daily pipeline | https://us-east-1.console.aws.amazon.com/states/home?region=us-east-1#/statemachines |
| Budget `eqh-dq-assistant-monthly` ($300) | https://console.aws.amazon.com/billing/home#/budgets |
| Redshift Query Editor v2 (workgroup `eqh-dq`, db `eqh`) | https://us-east-1.console.aws.amazon.com/sqlworkbench/home?region=us-east-1 |
| Aurora metadata store (Data API query editor) | https://us-east-1.console.aws.amazon.com/rds/home?region=us-east-1#query-editor: |
| Glue Data Catalog (`eqh_raw`, `eqh_silver`) | https://us-east-1.console.aws.amazon.com/glue/home?region=us-east-1#/v2/data-catalog/databases |
| Glue Data Quality rulesets | https://us-east-1.console.aws.amazon.com/glue/home?region=us-east-1#/v2/data-catalog/dataquality |
| Bedrock guardrails / model access | https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1#/guardrails |
| Eval report (S3) | https://s3.console.aws.amazon.com/s3/object/eqh-dq-761705103792-dq-results?region=us-east-1&prefix=eval/latest/report.html |
| GitHub repository | https://github.com/spbreed/eqh-dq-assistant |

## EqhDqSecurity (28 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqSecurity)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `Budgets::Budget` | Budget | `eqh-dq-assistant-monthly` | [open](https://console.aws.amazon.com/billing/home#/budgets) |
| `Budgets::BudgetsAction` | BudgetDenyAction | `675c2355-fc2d-4435-b200-c24150bcb36e|eqh-dq-assistant-monthly` | [open](https://console.aws.amazon.com/billing/home#/budgets) |
| `CloudTrail::Trail` | Trail022F0CF2 | `eqh-dq-assistant` | [open](https://us-east-1.console.aws.amazon.com/cloudtrailv2/home?region=us-east-1#/trails/eqh-dq-assistant) |
| `IAM::ManagedPolicy` | BudgetDeny38812154 | `arn:aws:iam::761705103792:policy/eqh-dq-budget-deny` | [open](https://console.aws.amazon.com/iam/home#/policies/details/arn%3Aaws%3Aiam%3A%3A761705103792%3Apolicy%2Feqh-dq-budget-deny) |
| `IAM::Role` | AWS679f53fac002430cb0da5b7982bd2287ServiceRoleC1EA0FF2 | `EqhDqSecurity-AWS679f53fac002430cb0da5b7982bd2287Se-A0bMEMZZHnjX` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqSecurity-AWS679f53fac002430cb0da5b7982bd2287Se-A0bMEMZZHnjX) |
| `IAM::Role` | AssistantRoleBF5D8EEC | `eqh-dq-assistant-task-role` | [open](https://console.aws.amazon.com/iam/home#/roles/details/eqh-dq-assistant-task-role) |
| `IAM::Role` | BedrockLoggingRole71F633EF | `EqhDqSecurity-BedrockLoggingRole71F633EF-EqQ4qqavAh6N` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqSecurity-BedrockLoggingRole71F633EF-EqQ4qqavAh6N) |
| `IAM::Role` | BudgetActionRoleA473BB3A | `EqhDqSecurity-BudgetActionRoleA473BB3A-kBk9H7iwDocC` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqSecurity-BudgetActionRoleA473BB3A-kBk9H7iwDocC) |
| `IAM::Role` | CustomS3AutoDeleteObjectsCustomResourceProviderRole3B1BD092 | `EqhDqSecurity-CustomS3AutoDeleteObjectsCustomResour-JesspIj0SykF` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqSecurity-CustomS3AutoDeleteObjectsCustomResour-JesspIj0SykF) |
| `IAM::Role` | EvalRole3F02F524 | `eqh-dq-eval-task-role` | [open](https://console.aws.amazon.com/iam/home#/roles/details/eqh-dq-eval-task-role) |
| `IAM::Role` | HarvestRole8C369678 | `eqh-dq-harvest-task-role` | [open](https://console.aws.amazon.com/iam/home#/roles/details/eqh-dq-harvest-task-role) |
| `IAM::Role` | RedshiftRoleD1BA0605 | `eqh-dq-redshift-role` | [open](https://console.aws.amazon.com/iam/home#/roles/details/eqh-dq-redshift-role) |
| `KMS::Key` | Cmk0E70AD9C | `65757bb9-365d-4293-9246-6a40b4087011` | [open](https://us-east-1.console.aws.amazon.com/kms/home?region=us-east-1#/kms/keys/65757bb9-365d-4293-9246-6a40b4087011) |
| `Lambda::Function` | AWS679f53fac002430cb0da5b7982bd22872D164C4C | `EqhDqSecurity-AWS679f53fac002430cb0da5b7982bd22872-pJgEgksdEL4l` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqSecurity-AWS679f53fac002430cb0da5b7982bd22872-pJgEgksdEL4l) |
| `Lambda::Function` | CustomS3AutoDeleteObjectsCustomResourceProviderHandler9D90184F | `EqhDqSecurity-CustomS3AutoDeleteObjectsCustomResou-PrhInblrsEr6` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqSecurity-CustomS3AutoDeleteObjectsCustomResou-PrhInblrsEr6) |
| `Logs::LogGroup` | BedrockInvocationLogs9E813CF7 | `/eqh-dq/bedrock-invocations` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%252Feqh-dq%252Fbedrock-invocations) |
| `S3::Bucket` | BackupBucket26B8E51C | `eqh-dq-761705103792-backup` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-backup?region=us-east-1) |
| `S3::Bucket` | TrailBucketA831CE63 | `eqhdqsecurity-trailbucketa831ce63-etdarc0nxnkt` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqhdqsecurity-trailbucketa831ce63-etdarc0nxnkt?region=us-east-1) |
| `Custom::AWS` | BedrockLoggingConfigD41391FD | `eqh-dq-bedrock-logging` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |

**Outputs:** `BackupBucketName` = `eqh-dq-761705103792-backup`

## EqhDqNetwork (50 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqNetwork)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `EC2::EIP` | VpcpublicSubnet1EIP411541E6 | `100.63.147.202` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::InternetGateway` | VpcIGWD7BA715C | `igw-07f7682884dd4cd24` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::NatGateway` | VpcpublicSubnet1NATGatewayA036E8A6 | `nat-02ce20252a88b362b` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#NatGatewayDetails:natGatewayId=nat-02ce20252a88b362b) |
| `EC2::RouteTable` | VpcegressSubnet1RouteTable5DEFB688 | `rtb-0ee0f6101e45a06af` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcegressSubnet2RouteTableBE1FD567 | `rtb-00e1f2d320bc2c865` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcegressSubnet3RouteTableC7EA8815 | `rtb-0a396405c03a6f8dc` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcisolatedSubnet1RouteTableE442650B | `rtb-02caf26fee1600763` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcisolatedSubnet2RouteTable334F9764 | `rtb-01236e1839db47c81` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcisolatedSubnet3RouteTableA2F6BBC0 | `rtb-0dd49d9b6e9d5cdf6` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcpublicSubnet1RouteTable15C15F8E | `rtb-0ee0ac8af94e71780` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcpublicSubnet2RouteTableC5A6DF77 | `rtb-07dce294cc2010137` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcpublicSubnet3RouteTable80517A9C | `rtb-0449acb412c69b8fc` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::SecurityGroup` | EndpointSg9223A863 | `sg-06bcdf6ea7639cf28` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-06bcdf6ea7639cf28) |
| `EC2::Subnet` | VpcegressSubnet1SubnetEDDDB236 | `subnet-0e80f722a21df9bd3` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0e80f722a21df9bd3) |
| `EC2::Subnet` | VpcegressSubnet2Subnet8217687B | `subnet-03bbe7f3c5b6f039d` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-03bbe7f3c5b6f039d) |
| `EC2::Subnet` | VpcegressSubnet3SubnetC2D14874 | `subnet-0c5fef3ace0301679` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0c5fef3ace0301679) |
| `EC2::Subnet` | VpcisolatedSubnet1SubnetE62B1B9B | `subnet-0ee7830a9f44360c4` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0ee7830a9f44360c4) |
| `EC2::Subnet` | VpcisolatedSubnet2Subnet39217055 | `subnet-06bc23244ee4de517` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-06bc23244ee4de517) |
| `EC2::Subnet` | VpcisolatedSubnet3Subnet44F2537D | `subnet-0994c1840ea45869d` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0994c1840ea45869d) |
| `EC2::Subnet` | VpcpublicSubnet1Subnet2BB74ED7 | `subnet-0609a85d338dbd634` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0609a85d338dbd634) |
| `EC2::Subnet` | VpcpublicSubnet2SubnetE34B022A | `subnet-035277700401aa4de` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-035277700401aa4de) |
| `EC2::Subnet` | VpcpublicSubnet3SubnetDFEF064A | `subnet-0df6a399e42d18d7c` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0df6a399e42d18d7c) |
| `EC2::VPC` | Vpc8378EB38 | `vpc-0c6a26f1be7c8c803` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#VpcDetails:VpcId=vpc-0c6a26f1be7c8c803) |
| `EC2::VPCEndpoint` | VpcBedrockRuntime1FB16359 | `vpce-0a3cfa3314b3006bd` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0a3cfa3314b3006bd) |
| `EC2::VPCEndpoint` | VpcEcrApi2DC95EDF | `vpce-030e334491dc726fa` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-030e334491dc726fa) |
| `EC2::VPCEndpoint` | VpcEcrDkr1989671C | `vpce-085586b052d38e9b1` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-085586b052d38e9b1) |
| `EC2::VPCEndpoint` | VpcGlue5BD04435 | `vpce-0ebe5c25df58a0c1e` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0ebe5c25df58a0c1e) |
| `EC2::VPCEndpoint` | VpcLogsE1759C4E | `vpce-035aea288807457d2` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-035aea288807457d2) |
| `EC2::VPCEndpoint` | VpcRdsDataBF569208 | `vpce-003c72da4fbf04e3e` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-003c72da4fbf04e3e) |
| `EC2::VPCEndpoint` | VpcRedshiftData55181CAD | `vpce-0172003736f0b9590` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0172003736f0b9590) |
| `EC2::VPCEndpoint` | VpcS3A5408339 | `vpce-0e2998aaf90276791` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0e2998aaf90276791) |
| `EC2::VPCEndpoint` | VpcSecretsManagerC91B0406 | `vpce-00b7ecd89a538582c` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-00b7ecd89a538582c) |
| `EC2::VPCEndpoint` | VpcSts9684971E | `vpce-0c3fa58267bbbfef4` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0c3fa58267bbbfef4) |

**Outputs:** `VpcId` = `vpc-0c6a26f1be7c8c803`

## EqhDqImage (6 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqImage)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `CodeBuild::Project` | Build45A36621 | `eqh-dq-image-build` | [open](https://us-east-1.console.aws.amazon.com/codesuite/codebuild/761705103792/projects/eqh-dq-image-build?region=us-east-1) |
| `ECR::PullThroughCacheRule` | EcrPublicCache | `ecr-public` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `ECR::Repository` | Repo02AC86CF | `eqh-dq-assistant` | [open](https://us-east-1.console.aws.amazon.com/ecr/repositories/private/761705103792/eqh-dq-assistant?region=us-east-1) |
| `IAM::Role` | BuildRoleB7C66CB2 | `EqhDqImage-BuildRoleB7C66CB2-JagLpvb44kUn` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqImage-BuildRoleB7C66CB2-JagLpvb44kUn) |

**Outputs:** `BuildProject` = `eqh-dq-image-build`; `ImageTag` = `94b974ca0df79b90`; `RepoUri` = `761705103792.dkr.ecr.us-east-1.amazonaws.com/eqh-dq-assistant`

## EqhDqDataPlatform (31 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqDataPlatform)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `EC2::SecurityGroup` | RedshiftSgF054C53D | `sg-0a7524157c9c55c64` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-0a7524157c9c55c64) |
| `Glue::Database` | Dbeqhraw | `eqh_raw` | [open](https://us-east-1.console.aws.amazon.com/glue/home?region=us-east-1#/v2/data-catalog/databases/view/eqh_raw) |
| `Glue::Database` | Dbeqhsilver | `eqh_silver` | [open](https://us-east-1.console.aws.amazon.com/glue/home?region=us-east-1#/v2/data-catalog/databases/view/eqh_silver) |
| `IAM::Role` | AWS679f53fac002430cb0da5b7982bd2287ServiceRoleC1EA0FF2 | `EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd22-7c813JKNovUK` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd22-7c813JKNovUK) |
| `IAM::Role` | CustomS3AutoDeleteObjectsCustomResourceProviderRole3B1BD092 | `EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomRe-cCE98YArWOCR` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomRe-cCE98YArWOCR) |
| `IAM::Role` | GlueDqRoleE6242040 | `eqh-dq-glue-dq-role` | [open](https://console.aws.amazon.com/iam/home#/roles/details/eqh-dq-glue-dq-role) |
| `Lambda::Function` | AWS679f53fac002430cb0da5b7982bd22872D164C4C | `EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd2-puzusXKR6pNi` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd2-puzusXKR6pNi) |
| `Lambda::Function` | CustomS3AutoDeleteObjectsCustomResourceProviderHandler9D90184F | `EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomR-Gquf3LZxHWp1` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomR-Gquf3LZxHWp1) |
| `RedshiftServerless::Namespace` | Namespace | `eqh-dq` | [open](https://us-east-1.console.aws.amazon.com/redshiftv2/home?region=us-east-1#serverless-namespace-details?namespace=eqh-dq) |
| `RedshiftServerless::Workgroup` | Workgroup | `eqh-dq` | [open](https://us-east-1.console.aws.amazon.com/redshiftv2/home?region=us-east-1#serverless-workgroup-details?workgroup=eqh-dq) |
| `S3::Bucket` | BucketdqresultsCC59304D | `eqh-dq-761705103792-dq-results` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-dq-results?region=us-east-1) |
| `S3::Bucket` | BucketextractsF6DAB5E5 | `eqh-dq-761705103792-extracts` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-extracts?region=us-east-1) |
| `S3::Bucket` | Bucketglossary830C36D3 | `eqh-dq-761705103792-glossary` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-glossary?region=us-east-1) |
| `S3::Bucket` | Bucketraw90B7F08C | `eqh-dq-761705103792-raw` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-raw?region=us-east-1) |
| `S3::Bucket` | Bucketsilver08DF8D82 | `eqh-dq-761705103792-silver` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-silver?region=us-east-1) |
| `SecretsManager::Secret` | RedshiftAdminSecret3A34154B | `arn:aws:secretsmanager:us-east…t:eqh-dq/redshift-admin-h2DOqp` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fredshift-admin-h2DOqp&region=us-east-1) |
| `Custom::AWS` | RpuUsageLimit0D42DFF2 | `47345087-9594-4fca-9729-c99cc17d9deb` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |

**Outputs:** `Bucketdqresults` = `eqh-dq-761705103792-dq-results`; `Bucketextracts` = `eqh-dq-761705103792-extracts`; `Bucketglossary` = `eqh-dq-761705103792-glossary`; `Bucketraw` = `eqh-dq-761705103792-raw`; `Bucketsilver` = `eqh-dq-761705103792-silver`; `RedshiftAdminSecretArn` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/redshift-admin-h2DOqp`; `RedshiftWorkgroup` = `eqh-dq`

## EqhDqMetadataStore (13 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqMetadataStore)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `EC2::SecurityGroup` | AuroraSgFE0A4948 | `sg-0e24c10ac5aa6da6f` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-0e24c10ac5aa6da6f) |
| `RDS::DBCluster` | ClusterEB0386A7 | `eqh-dq-metadata` | [open](https://us-east-1.console.aws.amazon.com/rds/home?region=us-east-1#database:id=eqh-dq-metadata;is-cluster=true) |
| `RDS::DBInstance` | Clusterwriter2D9E9F4C | `eqhdqmetadatastore-clusterwriter2d9e9f4c-16698atqwumy` | [open](https://us-east-1.console.aws.amazon.com/rds/home?region=us-east-1#database:id=eqhdqmetadatastore-clusterwriter2d9e9f4c-16698atqwumy;is-cluster=false) |
| `RDS::DBSubnetGroup` | ClusterSubnetsDCFA5CB7 | `eqhdqmetadatastore-clustersubnetsdcfa5cb7-knykkocc6umh` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `SecretsManager::Secret` | AdminSecretB9452750 | `arn:aws:secretsmanager:us-east…ret:eqh-dq/aurora-admin-D7GAQ0` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Faurora-admin-D7GAQ0&region=us-east-1) |
| `SecretsManager::Secret` | ClusterSecret6368BD0F | `arn:aws:secretsmanager:us-east…et6368BD0F-c9JnA5hkweHu-rZgLFZ` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3AClusterSecret6368BD0F-c9JnA5hkweHu-rZgLFZ&region=us-east-1) |
| `SecretsManager::Secret` | SecreteqhassistantC118E909 | `arn:aws:secretsmanager:us-east…dq/aurora-eqh_assistant-TmjReX` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Faurora-eqh_assistant-TmjReX&region=us-east-1) |
| `SecretsManager::Secret` | SecreteqhharvestB333218F | `arn:aws:secretsmanager:us-east…h-dq/aurora-eqh_harvest-quTYbv` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Faurora-eqh_harvest-quTYbv&region=us-east-1) |

**Outputs:** `ClusterArn` = `arn:aws:rds:us-east-1:761705103792:cluster:eqh-dq-metadata`; `SecretArn` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/aurora-admin-D7GAQ0`; `SecretArnAssistant` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/aurora-eqh_assistant-TmjReX`; `SecretArnHarvest` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/aurora-eqh_harvest-quTYbv`

## EqhDqPipeline (31 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqPipeline)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `CloudWatch::Alarm` | PipelineFailedAlarm321C49A8 | `eqh-dq-daily-failed` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#alarmsV2:alarm/eqh-dq-daily-failed) |
| `EC2::SecurityGroup` | TaskSgFD7B04A0 | `sg-05a1ee41f3b812d42` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-05a1ee41f3b812d42) |
| `ECS::Cluster` | ClusterEB0386A7 | `eqh-dq` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/eqh-dq?region=us-east-1) |
| `ECS::TaskDefinition` | TaskdailysyncBD897841 | `arn:aws:ecs:us-east-1:76170510…efinition/eqh-dq-daily_sync:10` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-daily_sync?region=us-east-1) |
| `ECS::TaskDefinition` | TaskenrichD86C02A0 | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-enrich:10` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-enrich?region=us-east-1) |
| `ECS::TaskDefinition` | TaskevalA93B9A31 | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-eval:10` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-eval?region=us-east-1) |
| `ECS::TaskDefinition` | TaskllmsmokeCAB2C006 | `arn:aws:ecs:us-east-1:76170510…definition/eqh-dq-llm_smoke:10` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-llm_smoke?region=us-east-1) |
| `ECS::TaskDefinition` | Taskprofiler2C026845 | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-profiler:10` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-profiler?region=us-east-1) |
| `IAM::Role` | DailyRole83FCF59B | `EqhDqPipeline-DailyRole83FCF59B-ElnrIUS4G0Zh` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-DailyRole83FCF59B-ElnrIUS4G0Zh) |
| `IAM::Role` | SchedulerRole59E73443 | `EqhDqPipeline-SchedulerRole59E73443-N7JMWKwMyEOh` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-SchedulerRole59E73443-N7JMWKwMyEOh) |
| `IAM::Role` | TaskdailysyncExecutionRole84CD4462 | `EqhDqPipeline-TaskdailysyncExecutionRole84CD4462-pKXla3lOFAEF` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskdailysyncExecutionRole84CD4462-pKXla3lOFAEF) |
| `IAM::Role` | TaskenrichExecutionRole4F9F3451 | `EqhDqPipeline-TaskenrichExecutionRole4F9F3451-Bn9Fi4Dhc2wl` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskenrichExecutionRole4F9F3451-Bn9Fi4Dhc2wl) |
| `IAM::Role` | TaskevalExecutionRole0C1C78BB | `EqhDqPipeline-TaskevalExecutionRole0C1C78BB-wcnFegweFkkC` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskevalExecutionRole0C1C78BB-wcnFegweFkkC) |
| `IAM::Role` | TaskllmsmokeExecutionRoleC4466DA6 | `EqhDqPipeline-TaskllmsmokeExecutionRoleC4466DA6-uDboN6DiXSht` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskllmsmokeExecutionRoleC4466DA6-uDboN6DiXSht) |
| `IAM::Role` | TaskprofilerExecutionRoleEBAEF2AB | `EqhDqPipeline-TaskprofilerExecutionRoleEBAEF2AB-TtgCTt3aGnZm` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskprofilerExecutionRoleEBAEF2AB-TtgCTt3aGnZm) |
| `Logs::LogGroup` | Logs6819BB44 | `/eqh-dq/pipeline` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%252Feqh-dq%252Fpipeline) |
| `SNS::Subscription` | AlertsRCemergertechcom67CEA448 | `arn:aws:sns:us-east-1:76170510…ef-2a71-4ae4-81ba-7ee6c5d00e20` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `SNS::Subscription` | Alertskarthikramamurthyemergertechcom510BBD7B | `arn:aws:sns:us-east-1:76170510…b6-b906-4fd9-a7e6-0507669b0b3f` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `SNS::Topic` | Alerts91F83244 | `arn:aws:sns:us-east-1:761705103792:eqh-dq-pipeline-alerts` | [open](https://us-east-1.console.aws.amazon.com/sns/v3/home?region=us-east-1#/topic/arn:aws:sns:us-east-1:761705103792:eqh-dq-pipeline-alerts) |
| `Scheduler::Schedule` | DailySchedule | `eqh-dq-daily` | [open](https://us-east-1.console.aws.amazon.com/scheduler/home?region=us-east-1#schedules/default/eqh-dq-daily) |
| `StepFunctions::StateMachine` | DailyF2158A89 | `arn:aws:states:us-east-1:761705103792:stateMachine:eqh-dq-daily` | [open](https://us-east-1.console.aws.amazon.com/states/home?region=us-east-1#/statemachines/view/arn%3Aaws%3Astates%3Aus-east-1%3A761705103792%3AstateMachine%3Aeqh-dq-daily) |

**Outputs:** `ClusterName` = `eqh-dq`; `StateMachineArn` = `arn:aws:states:us-east-1:761705103792:stateMachine:eqh-dq-daily`; `TaskDefDailysync` = `eqh-dq-daily_sync`; `TaskDefEnrich` = `eqh-dq-enrich`; `TaskDefEval` = `eqh-dq-eval`; `TaskDefLlmsmoke` = `eqh-dq-llm_smoke`; `TaskDefProfiler` = `eqh-dq-profiler`; `TaskSecurityGroup` = `sg-05a1ee41f3b812d42`; `TaskSubnets` = `subnet-0e80f722a21df9bd3,subnet-03bbe7f3c5b6f039d,subnet-0c5fef3ace0301679`

## EqhDqAssistant (45 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqAssistant)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `Bedrock::Guardrail` | Guardrail | `arn:aws:bedrock:us-east-1:761705103792:guardrail/qsswy7q520ik` | [open](https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1#/guardrails) |
| `Bedrock::GuardrailVersion` | GuardrailVersion | `qsswy7q520ik|1` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `CloudFront::Distribution` | Cdn9963B1AD | `E1HJH97567DOTX` | [open](https://console.aws.amazon.com/cloudfront/v4/home#/distributions/E1HJH97567DOTX) |
| `Cognito::UserPool` | Users0A0EEA89 | `us-east-1_Bv5uz5UKl` | [open](https://us-east-1.console.aws.amazon.com/cognito/v2/idp/user-pools/us-east-1_Bv5uz5UKl/info?region=us-east-1) |
| `Cognito::UserPoolClient` | UsersWebA39D1A70 | `2u7d9t0brs31tpa2oo6mqg19f8` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolDomain` | UsersDomainC6632324 | `eqh-dq-761705103792` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Gactuarial | `actuarial` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Ganalyst | `analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Grestrictedbh | `restricted_bh` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Gsteward | `steward` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemoactuary | `demo-actuary` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemoanalyst | `demo-analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemobhanalyst | `demo-bh-analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemosteward | `demo-steward` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::SecurityGroup` | AlbSg1155C1BE | `sg-0ba35bfcdf2924966` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-0ba35bfcdf2924966) |
| `EC2::SecurityGroup` | SvcSgFDC59615 | `sg-0fbfe4ad33cbc8e56` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-0fbfe4ad33cbc8e56) |
| `ECS::Service` | ServiceD69D759B | `arn:aws:ecs:us-east-1:761705103792:service/eqh-dq/eqh-dq-assistant` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/eqh-dq/services/eqh-dq-assistant?region=us-east-1) |
| `ECS::TaskDefinition` | Task79114B6B | `arn:aws:ecs:us-east-1:76170510…definition/eqh-dq-assistant:10` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-assistant?region=us-east-1) |
| `ElasticLoadBalancingV2::Listener` | AlbHttp7966E42E | `arn:aws:elasticloadbalancing:u…b997a95d3cc7b/cc39d0b403a8f642` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `ElasticLoadBalancingV2::LoadBalancer` | Alb16C2F182 | `arn:aws:elasticloadbalancing:u…-JJIMs6NjGTBf/ce3b997a95d3cc7b` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#LoadBalancers:) |
| `ElasticLoadBalancingV2::TargetGroup` | AlbHttpAppGroupAC6A8101 | `arn:aws:elasticloadbalancing:u…-HEN7QHLC4WWW/08ce5d997787d335` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `IAM::Role` | AWS679f53fac002430cb0da5b7982bd2287ServiceRoleC1EA0FF2 | `EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287S-mjmXHIr7mZNA` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287S-mjmXHIr7mZNA) |
| `IAM::Role` | TaskExecutionRoleEF964934 | `EqhDqAssistant-TaskExecutionRoleEF964934-XuoUr79AWxDR` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqAssistant-TaskExecutionRoleEF964934-XuoUr79AWxDR) |
| `Lambda::Function` | AWS679f53fac002430cb0da5b7982bd22872D164C4C | `EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287-KJo4KKHyauc6` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287-KJo4KKHyauc6) |
| `Logs::LogGroup` | Logs6819BB44 | `/eqh-dq/assistant` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%252Feqh-dq%252Fassistant) |
| `SecretsManager::Secret` | OriginVerifyED6A82E8 | `arn:aws:secretsmanager:us-east…et:eqh-dq/origin-verify-5QeYax` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Forigin-verify-5QeYax&region=us-east-1) |
| `SecretsManager::Secret` | PwddemoactuaryCB6EDFE3 | `arn:aws:secretsmanager:us-east…dq/cognito/demo-actuary-jcYf6c` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-actuary-jcYf6c&region=us-east-1) |
| `SecretsManager::Secret` | PwddemoanalystFEFDA8BD | `arn:aws:secretsmanager:us-east…dq/cognito/demo-analyst-CYO565` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-analyst-CYO565&region=us-east-1) |
| `SecretsManager::Secret` | PwddemobhanalystA64D7B3F | `arn:aws:secretsmanager:us-east…cognito/demo-bh-analyst-YSABTy` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-bh-analyst-YSABTy&region=us-east-1) |
| `SecretsManager::Secret` | PwddemostewardAAA53D7B | `arn:aws:secretsmanager:us-east…dq/cognito/demo-steward-EpXKMf` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-steward-EpXKMf&region=us-east-1) |
| `SecretsManager::Secret` | SessionSecretC41FBD23 | `arn:aws:secretsmanager:us-east…t:eqh-dq/session-secret-Mdm8Rd` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fsession-secret-Mdm8Rd&region=us-east-1) |
| `WAFv2::WebACL` | Waf | `eqh-dq-assistant|d1ecd116-e42b-4af7-9e98-00681df6f175|CLOUDFRONT` | [open](https://console.aws.amazon.com/wafv2/homev2/web-acls?region=global) |
| `Custom::AWS` | CfPrefixListDC6ACBA1 | `cf-origin-prefix` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |

**Outputs:** `AlbArn` = `arn:aws:elasticloadbalancing:us-east-1:761705103792:loadbalancer/app/EqhDqA-Alb16-JJIMs6NjGTBf/ce3b997a95d3cc7b`; `OutGuardrailId` = `qsswy7q520ik`; `OutGuardrailVersion` = `1`; `Url` = `https://do3jeqzux8by1.cloudfront.net`; `UserPoolId` = `us-east-1_Bv5uz5UKl`

## EqhDqObservability (3 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqObservability)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `CloudWatch::Dashboard` | DashCCD7F836 | `eqh-dq-assistant` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards/dashboard/eqh-dq-assistant) |
| `Logs::MetricFilter` | LatencyFilter544CD537 | `LatencyFilter544CD537-tritGqrlX0gU` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |

## Created outside CloudFormation (data / catalog objects)

| Object | Where | Created by |
|---|---|---|
| 47 raw feed tables + 19 silver tables, daily partitions | Glue `eqh_raw`, `eqh_silver` | `datagen/catalog.py` |
| 7 Glue DQ rulesets `eqh_silver_*` | Glue Data Quality | `datagen/glue_dq.py` |
| Schemas `core`, `careempower`, `vbc_mart`, `outbound`, external `spectrum_silver`; datashares `eqh_actuarial_share`, `eqh_finance_share`; consumer users | Redshift `eqh` | `sql/redshift/*.sql`, `datagen/load.py` |
| Metadata store schema + roles `eqh_harvest`, `eqh_assistant` | Aurora `eqh_meta` | `metadata_store/migrate.py` |
| Bedrock model-invocation logging config | Bedrock account setting | `EqhDqSecurity` custom resource |
| Marketplace agreements for GPT‑5.6 Terra/Luna/Sol | AWS Marketplace | accepted 2026-10-27 (see docs/DECISIONS.md D‑01) |
| CDK bootstrap stack `CDKToolkit` | CloudFormation | `cdk bootstrap` (kept by `make destroy`) |
