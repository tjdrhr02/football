# infra/terraform — Free-tier RDS PostgreSQL (pgvector)

Provisions a single **free-tier** RDS PostgreSQL 16 instance for the Football
Tactical Intelligence Platform (Day 3). pgvector is enabled by the app schema
(`db/schema/02_analytics.sql`).

## What gets created
- `aws_db_instance` `football-rds` — `db.t4g.micro`, 20 GB gp2, Single-AZ, public
- `aws_security_group` — inbound **5432 from your IP only**
- `aws_db_subnet_group` — over the account's **default VPC** subnets

## Prerequisites
- `aws configure` done (region `ap-northeast-2`), `aws sts get-caller-identity` works
- `terraform` and `psql`/`pg_dump` installed

## Usage
```bash
# 1. Secrets (gitignored)
cp terraform.tfvars.example terraform.tfvars   # set db_password
# my_ip is filled automatically below

# 2. Provision
MY_IP="$(curl -s ifconfig.me)/32"
terraform init
terraform plan  -var="my_ip=$MY_IP"
terraform apply -var="my_ip=$MY_IP"   # ~5-10 min

# 3. Endpoint
terraform output -raw db_address
```

If apply errors on `engine_version` being unavailable:
```bash
aws rds describe-db-engine-versions --engine postgres \
  --query 'DBEngineVersions[].EngineVersion' --output text
```
then set a listed 16.x via `-var="engine_version=16.x"`.

## Cost guardrails (all within AWS Free Tier)
| Setting | Value | Why |
|---|---|---|
| instance_class | db.t4g.micro | free 750h/month (keep to **one** instance) |
| storage | 20 GB gp2, autoscale **off** | free tier cap, no surprise growth charges |
| multi_az | false | Multi-AZ is paid |
| performance_insights / enhanced monitoring | off | avoid CloudWatch charges |
| backup_retention | 1 day | tiny DB, within free 20 GB backup |

⚠️ RDS free tier = **12 months** from account creation. Keep **only one** RDS
instance running. Inbound transfer (pg_restore) is free.

## Tear down (stop all charges)
```bash
terraform destroy -var="my_ip=$MY_IP"
```
Safe to destroy when not in use — re-apply + re-restore the dump takes ~5 min.
