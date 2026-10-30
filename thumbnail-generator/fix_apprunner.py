import boto3, json, time

REGION  = "us-east-1"
ACCOUNT = "926827998536"
SERVICE = "thumbnail-generator-ui"
ECR_URI = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/thumbnail-generator-ui:latest"
INTAKE  = f"intake-bucket-{ACCOUNT}"
OUTPUT  = f"output-bucket-{ACCOUNT}"

lines = []

def save():
    open("C:/tgen/fix_apprunner_result.txt", "w", encoding="utf-8").write("\n".join(lines))

iam     = boto3.client("iam")
runner  = boto3.client("apprunner", region_name=REGION)

# ── Step 1: Create instance role for the running container ────────────────
INSTANCE_ROLE = "thumbnail-ui-instance-role"
lines.append("=== Step 1: Creating App Runner instance role ===")

trust = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
})

s3_policy = json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{INTAKE}", f"arn:aws:s3:::{INTAKE}/*",
                      f"arn:aws:s3:::{OUTPUT}", f"arn:aws:s3:::{OUTPUT}/*"]},
        {"Effect": "Allow", "Action": "s3:ListAllMyBuckets",
         "Resource": "*"}
    ]
})

try:
    r = iam.create_role(RoleName=INSTANCE_ROLE, AssumeRolePolicyDocument=trust)
    instance_role_arn = r["Role"]["Arn"]
    iam.put_role_policy(RoleName=INSTANCE_ROLE,
                        PolicyName="S3Access",
                        PolicyDocument=s3_policy)
    lines.append(f"Instance role created: {instance_role_arn}")
    lines.append("Waiting 10s for propagation...")
    save(); time.sleep(10)
except iam.exceptions.EntityAlreadyExistsException:
    instance_role_arn = iam.get_role(RoleName=INSTANCE_ROLE)["Role"]["Arn"]
    # Update the policy
    iam.put_role_policy(RoleName=INSTANCE_ROLE,
                        PolicyName="S3Access",
                        PolicyDocument=s3_policy)
    lines.append(f"Instance role exists, policy updated: {instance_role_arn}")
save()

# ── Step 2: Get access role ARN ───────────────────────────────────────────
access_role_arn = iam.get_role(
    RoleName="thumbnail-ui-apprunner-role")["Role"]["Arn"]

# ── Step 3: Delete the failed service ────────────────────────────────────
lines.append("\n=== Step 2: Deleting failed service ===")
svcs = runner.list_services()["ServiceSummaryList"]
svc_arn = next((s["ServiceArn"] for s in svcs
                if s["ServiceName"] == SERVICE), None)
if svc_arn:
    runner.delete_service(ServiceArn=svc_arn)
    lines.append(f"Deleted: {svc_arn}")
    lines.append("Waiting 30s for deletion...")
    save(); time.sleep(30)
else:
    lines.append("No existing service found")
save()

# ── Step 4: Re-create with instance role ─────────────────────────────────
lines.append("\n=== Step 3: Creating App Runner service with instance role ===")
try:
    resp = runner.create_service(
        ServiceName=SERVICE,
        SourceConfiguration={
            "ImageRepository": {
                "ImageIdentifier": ECR_URI,
                "ImageRepositoryType": "ECR",
                "ImageConfiguration": {
                    "Port": "8080",
                    "RuntimeEnvironmentVariables": {
                        "AWS_DEFAULT_REGION": REGION,
                        "INTAKE_BUCKET": INTAKE,
                        "OUTPUT_BUCKET": OUTPUT,
                    }
                }
            },
            "AuthenticationConfiguration": {"AccessRoleArn": access_role_arn},
            "AutoDeploymentsEnabled": False
        },
        InstanceConfiguration={
            "Cpu": "0.25 vCPU",
            "Memory": "0.5 GB",
            "InstanceRoleArn": instance_role_arn
        },
    )
    svc = resp["Service"]
    lines.append(f"Service created! Status: {svc['Status']}")
    lines.append(f"\nYour public URL: https://{svc['ServiceUrl']}")
    lines.append("(Will be live in ~3-5 minutes)")
except Exception as e:
    lines.append(f"ERROR: {e}")

save()
print("\n".join(lines))
