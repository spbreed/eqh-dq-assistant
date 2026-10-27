# Resources — EQH DQ Assistant pilot

AWS account `761705103792`, region `us-east-1`. All resources are tagged `project=eqh-dq-assistant`, `env=pilot`, `owner=karthik.ramamurthy@emergertech.com`, `data=synthetic` and are created by the CDK app in `infra/` (regenerate this file with `python scripts/gen_resources.py`). Generated 2026-10-27 21:46 UTC.

## Entry points

| What | Link |
|---|---|
| Assistant (CloudFront, Cognito login) | https://d16or4k2hjq489.cloudfront.net |
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

## EqhDqSecurity (25 CloudFormation resources)

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
| `S3::Bucket` | TrailBucketA831CE63 | `eqhdqsecurity-trailbucketa831ce63-etdarc0nxnkt` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqhdqsecurity-trailbucketa831ce63-etdarc0nxnkt?region=us-east-1) |
| `Custom::AWS` | BedrockLoggingConfigD41391FD | `eqh-dq-bedrock-logging` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |

**Outputs:** 

## EqhDqNetwork (50 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqNetwork)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `EC2::EIP` | VpcpublicSubnet1EIP411541E6 | `54.146.214.36` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::InternetGateway` | VpcIGWD7BA715C | `igw-0b02d57e9491885aa` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::NatGateway` | VpcpublicSubnet1NATGatewayA036E8A6 | `nat-0b5e3cfa3983c2c77` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#NatGatewayDetails:natGatewayId=nat-0b5e3cfa3983c2c77) |
| `EC2::RouteTable` | VpcegressSubnet1RouteTable5DEFB688 | `rtb-0e58083782f624ec4` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcegressSubnet2RouteTableBE1FD567 | `rtb-0ecf1f67b672875b5` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcegressSubnet3RouteTableC7EA8815 | `rtb-07e96549b2967fa2f` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcisolatedSubnet1RouteTableE442650B | `rtb-00d29029d538fc506` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcisolatedSubnet2RouteTable334F9764 | `rtb-0703aba7127fba678` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcisolatedSubnet3RouteTableA2F6BBC0 | `rtb-04d10bc357cb29d28` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcpublicSubnet1RouteTable15C15F8E | `rtb-003919a8900c9d6b2` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcpublicSubnet2RouteTableC5A6DF77 | `rtb-06633b1d6f68a2599` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::RouteTable` | VpcpublicSubnet3RouteTable80517A9C | `rtb-004205b6ea59dd2b5` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::SecurityGroup` | EndpointSg9223A863 | `sg-09fed0406f004d16f` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-09fed0406f004d16f) |
| `EC2::Subnet` | VpcegressSubnet1SubnetEDDDB236 | `subnet-02bbaccababe04b7f` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-02bbaccababe04b7f) |
| `EC2::Subnet` | VpcegressSubnet2Subnet8217687B | `subnet-0b7994f28b8848edf` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0b7994f28b8848edf) |
| `EC2::Subnet` | VpcegressSubnet3SubnetC2D14874 | `subnet-0425f5f16fa052ab5` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0425f5f16fa052ab5) |
| `EC2::Subnet` | VpcisolatedSubnet1SubnetE62B1B9B | `subnet-0d2035e818a36a5f8` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0d2035e818a36a5f8) |
| `EC2::Subnet` | VpcisolatedSubnet2Subnet39217055 | `subnet-098d612a4ed5d5567` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-098d612a4ed5d5567) |
| `EC2::Subnet` | VpcisolatedSubnet3Subnet44F2537D | `subnet-0fcd29eb57c05a7c9` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0fcd29eb57c05a7c9) |
| `EC2::Subnet` | VpcpublicSubnet1Subnet2BB74ED7 | `subnet-051ba59f29ac3c1e9` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-051ba59f29ac3c1e9) |
| `EC2::Subnet` | VpcpublicSubnet2SubnetE34B022A | `subnet-003d341704259c294` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-003d341704259c294) |
| `EC2::Subnet` | VpcpublicSubnet3SubnetDFEF064A | `subnet-0753d5499cd904a43` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#SubnetDetails:subnetId=subnet-0753d5499cd904a43) |
| `EC2::VPC` | Vpc8378EB38 | `vpc-0d1c0b9db6cb3d54b` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#VpcDetails:VpcId=vpc-0d1c0b9db6cb3d54b) |
| `EC2::VPCEndpoint` | VpcBedrockRuntime1FB16359 | `vpce-025e31c2244e9af06` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-025e31c2244e9af06) |
| `EC2::VPCEndpoint` | VpcEcrApi2DC95EDF | `vpce-0aeb3013735b64cca` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0aeb3013735b64cca) |
| `EC2::VPCEndpoint` | VpcEcrDkr1989671C | `vpce-088d8cdb53e788474` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-088d8cdb53e788474) |
| `EC2::VPCEndpoint` | VpcGlue5BD04435 | `vpce-099490ce277833038` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-099490ce277833038) |
| `EC2::VPCEndpoint` | VpcLogsE1759C4E | `vpce-04103946e7aa78d39` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-04103946e7aa78d39) |
| `EC2::VPCEndpoint` | VpcRdsDataBF569208 | `vpce-0251fce2f8f04c7e3` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0251fce2f8f04c7e3) |
| `EC2::VPCEndpoint` | VpcRedshiftData55181CAD | `vpce-0861eecd38565875d` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0861eecd38565875d) |
| `EC2::VPCEndpoint` | VpcS3A5408339 | `vpce-0de2dc1cdd80dbcdb` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-0de2dc1cdd80dbcdb) |
| `EC2::VPCEndpoint` | VpcSecretsManagerC91B0406 | `vpce-033730c3f83b9ab09` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-033730c3f83b9ab09) |
| `EC2::VPCEndpoint` | VpcSts9684971E | `vpce-06706242b9e0e8f91` | [open](https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#EndpointDetails:vpcEndpointId=vpce-06706242b9e0e8f91) |

**Outputs:** `VpcId` = `vpc-0d1c0b9db6cb3d54b`

## EqhDqImage (6 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqImage)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `CodeBuild::Project` | Build45A36621 | `eqh-dq-image-build` | [open](https://us-east-1.console.aws.amazon.com/codesuite/codebuild/761705103792/projects/eqh-dq-image-build?region=us-east-1) |
| `ECR::PullThroughCacheRule` | EcrPublicCache | `ecr-public` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `ECR::Repository` | Repo02AC86CF | `eqh-dq-assistant` | [open](https://us-east-1.console.aws.amazon.com/ecr/repositories/private/761705103792/eqh-dq-assistant?region=us-east-1) |
| `IAM::Role` | BuildRoleB7C66CB2 | `EqhDqImage-BuildRoleB7C66CB2-XM9HmLgaukwf` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqImage-BuildRoleB7C66CB2-XM9HmLgaukwf) |

**Outputs:** `BuildProject` = `eqh-dq-image-build`; `ImageTag` = `4f4901e21155e17e`; `RepoUri` = `761705103792.dkr.ecr.us-east-1.amazonaws.com/eqh-dq-assistant`

## EqhDqDataPlatform (31 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqDataPlatform)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `EC2::SecurityGroup` | RedshiftSgF054C53D | `sg-0f0d976a60ddff674` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-0f0d976a60ddff674) |
| `Glue::Database` | Dbeqhraw | `eqh_raw` | [open](https://us-east-1.console.aws.amazon.com/glue/home?region=us-east-1#/v2/data-catalog/databases/view/eqh_raw) |
| `Glue::Database` | Dbeqhsilver | `eqh_silver` | [open](https://us-east-1.console.aws.amazon.com/glue/home?region=us-east-1#/v2/data-catalog/databases/view/eqh_silver) |
| `IAM::Role` | AWS679f53fac002430cb0da5b7982bd2287ServiceRoleC1EA0FF2 | `EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd22-G9BgU2oAbqbU` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd22-G9BgU2oAbqbU) |
| `IAM::Role` | CustomS3AutoDeleteObjectsCustomResourceProviderRole3B1BD092 | `EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomRe-zOd2tN2Fs41Z` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomRe-zOd2tN2Fs41Z) |
| `IAM::Role` | GlueDqRoleE6242040 | `eqh-dq-glue-dq-role` | [open](https://console.aws.amazon.com/iam/home#/roles/details/eqh-dq-glue-dq-role) |
| `Lambda::Function` | AWS679f53fac002430cb0da5b7982bd22872D164C4C | `EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd2-33usBsDBBxGn` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqDataPlatform-AWS679f53fac002430cb0da5b7982bd2-33usBsDBBxGn) |
| `Lambda::Function` | CustomS3AutoDeleteObjectsCustomResourceProviderHandler9D90184F | `EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomR-bazixLgnS0BJ` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqDataPlatform-CustomS3AutoDeleteObjectsCustomR-bazixLgnS0BJ) |
| `RedshiftServerless::Namespace` | Namespace | `eqh-dq` | [open](https://us-east-1.console.aws.amazon.com/redshiftv2/home?region=us-east-1#serverless-namespace-details?namespace=eqh-dq) |
| `RedshiftServerless::Workgroup` | Workgroup | `eqh-dq` | [open](https://us-east-1.console.aws.amazon.com/redshiftv2/home?region=us-east-1#serverless-workgroup-details?workgroup=eqh-dq) |
| `S3::Bucket` | BucketdqresultsCC59304D | `eqh-dq-761705103792-dq-results` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-dq-results?region=us-east-1) |
| `S3::Bucket` | BucketextractsF6DAB5E5 | `eqh-dq-761705103792-extracts` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-extracts?region=us-east-1) |
| `S3::Bucket` | Bucketglossary830C36D3 | `eqh-dq-761705103792-glossary` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-glossary?region=us-east-1) |
| `S3::Bucket` | Bucketraw90B7F08C | `eqh-dq-761705103792-raw` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-raw?region=us-east-1) |
| `S3::Bucket` | Bucketsilver08DF8D82 | `eqh-dq-761705103792-silver` | [open](https://s3.console.aws.amazon.com/s3/buckets/eqh-dq-761705103792-silver?region=us-east-1) |
| `SecretsManager::Secret` | RedshiftAdminSecret3A34154B | `arn:aws:secretsmanager:us-east…t:eqh-dq/redshift-admin-YgYleO` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fredshift-admin-YgYleO&region=us-east-1) |
| `Custom::AWS` | RpuUsageLimit0D42DFF2 | `203bd336-d4a2-4822-85e1-948c8252884d` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |

**Outputs:** `Bucketdqresults` = `eqh-dq-761705103792-dq-results`; `Bucketextracts` = `eqh-dq-761705103792-extracts`; `Bucketglossary` = `eqh-dq-761705103792-glossary`; `Bucketraw` = `eqh-dq-761705103792-raw`; `Bucketsilver` = `eqh-dq-761705103792-silver`; `RedshiftAdminSecretArn` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/redshift-admin-YgYleO`; `RedshiftWorkgroup` = `eqh-dq`

## EqhDqMetadataStore (11 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqMetadataStore)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `EC2::SecurityGroup` | AuroraSgFE0A4948 | `sg-0f9b3c19d86368433` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-0f9b3c19d86368433) |
| `RDS::DBCluster` | ClusterEB0386A7 | `eqh-dq-metadata` | [open](https://us-east-1.console.aws.amazon.com/rds/home?region=us-east-1#database:id=eqh-dq-metadata;is-cluster=true) |
| `RDS::DBInstance` | Clusterwriter2D9E9F4C | `eqhdqmetadatastore-clusterwriter2d9e9f4c-8knnezlepfko` | [open](https://us-east-1.console.aws.amazon.com/rds/home?region=us-east-1#database:id=eqhdqmetadatastore-clusterwriter2d9e9f4c-8knnezlepfko;is-cluster=false) |
| `RDS::DBSubnetGroup` | ClusterSubnetsDCFA5CB7 | `eqhdqmetadatastore-clustersubnetsdcfa5cb7-elpbp0w1cgsp` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `SecretsManager::Secret` | EqhDqMetadataStoreClusterSecretE9FBF3B53fdaad7efa858a3daf9490cf0a702aeb | `arn:aws:secretsmanager:us-east…ret:eqh-dq/aurora-admin-1lK1nz` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Faurora-admin-1lK1nz&region=us-east-1) |
| `SecretsManager::Secret` | SecreteqhassistantC118E909 | `arn:aws:secretsmanager:us-east…dq/aurora-eqh_assistant-fRmu2X` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Faurora-eqh_assistant-fRmu2X&region=us-east-1) |
| `SecretsManager::Secret` | SecreteqhharvestB333218F | `arn:aws:secretsmanager:us-east…h-dq/aurora-eqh_harvest-wx0roN` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Faurora-eqh_harvest-wx0roN&region=us-east-1) |

**Outputs:** `ClusterArn` = `arn:aws:rds:us-east-1:761705103792:cluster:eqh-dq-metadata`; `SecretArn` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/aurora-admin-1lK1nz`; `SecretArnAssistant` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/aurora-eqh_assistant-fRmu2X`; `SecretArnHarvest` = `arn:aws:secretsmanager:us-east-1:761705103792:secret:eqh-dq/aurora-eqh_harvest-wx0roN`

## EqhDqPipeline (31 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqPipeline)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `CloudWatch::Alarm` | PipelineFailedAlarm321C49A8 | `eqh-dq-daily-failed` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#alarmsV2:alarm/eqh-dq-daily-failed) |
| `EC2::SecurityGroup` | TaskSgFD7B04A0 | `sg-07ef5a61892e55a75` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-07ef5a61892e55a75) |
| `ECS::Cluster` | ClusterEB0386A7 | `eqh-dq` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/eqh-dq?region=us-east-1) |
| `ECS::TaskDefinition` | TaskdailysyncBD897841 | `arn:aws:ecs:us-east-1:76170510…definition/eqh-dq-daily_sync:3` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-daily_sync?region=us-east-1) |
| `ECS::TaskDefinition` | TaskenrichD86C02A0 | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-enrich:3` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-enrich?region=us-east-1) |
| `ECS::TaskDefinition` | TaskevalA93B9A31 | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-eval:3` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-eval?region=us-east-1) |
| `ECS::TaskDefinition` | TaskllmsmokeCAB2C006 | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-llm_smoke:3` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-llm_smoke?region=us-east-1) |
| `ECS::TaskDefinition` | Taskprofiler2C026845 | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-profiler:3` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-profiler?region=us-east-1) |
| `IAM::Role` | DailyRole83FCF59B | `EqhDqPipeline-DailyRole83FCF59B-KRhBMPYCFm4r` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-DailyRole83FCF59B-KRhBMPYCFm4r) |
| `IAM::Role` | SchedulerRole59E73443 | `EqhDqPipeline-SchedulerRole59E73443-uHOf3KHB78T0` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-SchedulerRole59E73443-uHOf3KHB78T0) |
| `IAM::Role` | TaskdailysyncExecutionRole84CD4462 | `EqhDqPipeline-TaskdailysyncExecutionRole84CD4462-nheSufC45D9J` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskdailysyncExecutionRole84CD4462-nheSufC45D9J) |
| `IAM::Role` | TaskenrichExecutionRole4F9F3451 | `EqhDqPipeline-TaskenrichExecutionRole4F9F3451-4E7TgXBYnsCh` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskenrichExecutionRole4F9F3451-4E7TgXBYnsCh) |
| `IAM::Role` | TaskevalExecutionRole0C1C78BB | `EqhDqPipeline-TaskevalExecutionRole0C1C78BB-ZlFoG7aM5QXd` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskevalExecutionRole0C1C78BB-ZlFoG7aM5QXd) |
| `IAM::Role` | TaskllmsmokeExecutionRoleC4466DA6 | `EqhDqPipeline-TaskllmsmokeExecutionRoleC4466DA6-hzq96W6CaRAI` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskllmsmokeExecutionRoleC4466DA6-hzq96W6CaRAI) |
| `IAM::Role` | TaskprofilerExecutionRoleEBAEF2AB | `EqhDqPipeline-TaskprofilerExecutionRoleEBAEF2AB-IqwEiL5T7RS8` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqPipeline-TaskprofilerExecutionRoleEBAEF2AB-IqwEiL5T7RS8) |
| `Logs::LogGroup` | Logs6819BB44 | `/eqh-dq/pipeline` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%252Feqh-dq%252Fpipeline) |
| `SNS::Subscription` | AlertsRCemergertechcom67CEA448 | `arn:aws:sns:us-east-1:76170510…8b-9fda-4681-84b1-22e8f747b5e9` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `SNS::Subscription` | Alertskarthikramamurthyemergertechcom510BBD7B | `arn:aws:sns:us-east-1:76170510…5e-750f-4212-aa7c-ca17a0a0e029` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `SNS::Topic` | Alerts91F83244 | `arn:aws:sns:us-east-1:761705103792:eqh-dq-pipeline-alerts` | [open](https://us-east-1.console.aws.amazon.com/sns/v3/home?region=us-east-1#/topic/arn:aws:sns:us-east-1:761705103792:eqh-dq-pipeline-alerts) |
| `Scheduler::Schedule` | DailySchedule | `eqh-dq-daily` | [open](https://us-east-1.console.aws.amazon.com/scheduler/home?region=us-east-1#schedules/default/eqh-dq-daily) |
| `StepFunctions::StateMachine` | DailyF2158A89 | `arn:aws:states:us-east-1:761705103792:stateMachine:eqh-dq-daily` | [open](https://us-east-1.console.aws.amazon.com/states/home?region=us-east-1#/statemachines/view/arn%3Aaws%3Astates%3Aus-east-1%3A761705103792%3AstateMachine%3Aeqh-dq-daily) |

**Outputs:** `ClusterName` = `eqh-dq`; `StateMachineArn` = `arn:aws:states:us-east-1:761705103792:stateMachine:eqh-dq-daily`; `TaskDefDailysync` = `eqh-dq-daily_sync`; `TaskDefEnrich` = `eqh-dq-enrich`; `TaskDefEval` = `eqh-dq-eval`; `TaskDefLlmsmoke` = `eqh-dq-llm_smoke`; `TaskDefProfiler` = `eqh-dq-profiler`; `TaskSecurityGroup` = `sg-07ef5a61892e55a75`; `TaskSubnets` = `subnet-02bbaccababe04b7f,subnet-0b7994f28b8848edf,subnet-0425f5f16fa052ab5`

## EqhDqAssistant (53 CloudFormation resources)

[CloudFormation stack](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/stackinfo?stackId=EqhDqAssistant)

| Type | Logical ID | Physical ID | Console |
|---|---|---|---|
| `Bedrock::Guardrail` | Guardrail | `arn:aws:bedrock:us-east-1:761705103792:guardrail/jkpxf4avlmx4` | [open](https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1#/guardrails) |
| `Bedrock::GuardrailVersion` | GuardrailVersion | `jkpxf4avlmx4|1` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `CloudFront::Distribution` | Cdn9963B1AD | `E662PAQAR1ZCR` | [open](https://console.aws.amazon.com/cloudfront/v4/home#/distributions/E662PAQAR1ZCR) |
| `Cognito::UserPool` | Users0A0EEA89 | `us-east-1_Lh0KbrQZJ` | [open](https://us-east-1.console.aws.amazon.com/cognito/v2/idp/user-pools/us-east-1_Lh0KbrQZJ/info?region=us-east-1) |
| `Cognito::UserPoolClient` | UsersWebA39D1A70 | `2rfe5gr1b83ahkum553s06giqq` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolDomain` | UsersDomainC6632324 | `eqh-dq-761705103792` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Gactuarial | `actuarial` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Ganalyst | `analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Grestrictedbh | `restricted_bh` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolGroup` | Gsteward | `steward` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemoactuary | `demo-actuary` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemoanalyst | `demo-analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemobhanalyst | `demo-bh-analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Cognito::UserPoolUser` | Udemosteward | `demo-steward` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `EC2::SecurityGroup` | AlbSg1155C1BE | `sg-08290f5b84f05c17f` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-08290f5b84f05c17f) |
| `EC2::SecurityGroup` | SvcSgFDC59615 | `sg-0aab214fed3cb6e54` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroup:groupId=sg-0aab214fed3cb6e54) |
| `ECS::Service` | ServiceD69D759B | `arn:aws:ecs:us-east-1:761705103792:service/eqh-dq/eqh-dq-assistant` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/eqh-dq/services/eqh-dq-assistant?region=us-east-1) |
| `ECS::TaskDefinition` | Task79114B6B | `arn:aws:ecs:us-east-1:761705103792:task-definition/eqh-dq-assistant:3` | [open](https://us-east-1.console.aws.amazon.com/ecs/v2/task-definitions/eqh-dq-assistant?region=us-east-1) |
| `ElasticLoadBalancingV2::Listener` | AlbHttp7966E42E | `arn:aws:elasticloadbalancing:u…f44cce7086310/7f169bf9ce835dc4` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `ElasticLoadBalancingV2::LoadBalancer` | Alb16C2F182 | `arn:aws:elasticloadbalancing:u…-87dhhki1yvtq/9f6f44cce7086310` | [open](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#LoadBalancers:) |
| `ElasticLoadBalancingV2::TargetGroup` | AlbHttpAppGroupAC6A8101 | `arn:aws:elasticloadbalancing:u…-4GYFT5KNPKRD/c782df86a229eb37` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `IAM::Role` | AWS679f53fac002430cb0da5b7982bd2287ServiceRoleC1EA0FF2 | `EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287S-CtLtGIGGOzV1` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287S-CtLtGIGGOzV1) |
| `IAM::Role` | TaskExecutionRoleEF964934 | `EqhDqAssistant-TaskExecutionRoleEF964934-gQTKKRV6lj18` | [open](https://console.aws.amazon.com/iam/home#/roles/details/EqhDqAssistant-TaskExecutionRoleEF964934-gQTKKRV6lj18) |
| `Lambda::Function` | AWS679f53fac002430cb0da5b7982bd22872D164C4C | `EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287-AnT2EUlmK3lK` | [open](https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/EqhDqAssistant-AWS679f53fac002430cb0da5b7982bd2287-AnT2EUlmK3lK) |
| `Logs::LogGroup` | Logs6819BB44 | `/eqh-dq/assistant` | [open](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%252Feqh-dq%252Fassistant) |
| `SecretsManager::Secret` | OriginVerifyED6A82E8 | `arn:aws:secretsmanager:us-east…et:eqh-dq/origin-verify-lGhKfO` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Forigin-verify-lGhKfO&region=us-east-1) |
| `SecretsManager::Secret` | PwddemoactuaryCB6EDFE3 | `arn:aws:secretsmanager:us-east…dq/cognito/demo-actuary-E7U49Z` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-actuary-E7U49Z&region=us-east-1) |
| `SecretsManager::Secret` | PwddemoanalystFEFDA8BD | `arn:aws:secretsmanager:us-east…dq/cognito/demo-analyst-YGqj9P` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-analyst-YGqj9P&region=us-east-1) |
| `SecretsManager::Secret` | PwddemobhanalystA64D7B3F | `arn:aws:secretsmanager:us-east…cognito/demo-bh-analyst-rZ1wmU` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-bh-analyst-rZ1wmU&region=us-east-1) |
| `SecretsManager::Secret` | PwddemostewardAAA53D7B | `arn:aws:secretsmanager:us-east…dq/cognito/demo-steward-U9a9W0` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fcognito%2Fdemo-steward-U9a9W0&region=us-east-1) |
| `SecretsManager::Secret` | SessionSecretC41FBD23 | `arn:aws:secretsmanager:us-east…t:eqh-dq/session-secret-ZORSLP` | [open](https://us-east-1.console.aws.amazon.com/secretsmanager/secret?name=arn%3Aaws%3Asecretsmanager%3Aus-east-1%3A761705103792%3Asecret%3Aeqh-dq%2Fsession-secret-ZORSLP&region=us-east-1) |
| `WAFv2::WebACL` | Waf | `eqh-dq-assistant|cf8c19d2-492f-4a81-83d6-fd1695efef5e|CLOUDFRONT` | [open](https://console.aws.amazon.com/wafv2/homev2/web-acls?region=global) |
| `Custom::AWS` | CfPrefixListDC6ACBA1 | `cf-origin-prefix` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Custom::AWS` | SetPwddemoactuaryF06EEE1C | `pwd-demo-actuary` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Custom::AWS` | SetPwddemoanalyst172D6395 | `pwd-demo-analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Custom::AWS` | SetPwddemobhanalystD5782166 | `pwd-demo-bh-analyst` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |
| `Custom::AWS` | SetPwddemosteward9E6F3701 | `pwd-demo-steward` | [open](https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1) |

**Outputs:** `AlbArn` = `arn:aws:elasticloadbalancing:us-east-1:761705103792:loadbalancer/app/EqhDqA-Alb16-87dhhki1yvtq/9f6f44cce7086310`; `OutGuardrailId` = `jkpxf4avlmx4`; `OutGuardrailVersion` = `1`; `Url` = `https://d16or4k2hjq489.cloudfront.net`; `UserPoolId` = `us-east-1_Lh0KbrQZJ`

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
