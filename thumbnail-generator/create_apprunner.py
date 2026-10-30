import boto3, json, time

REGION  = "us-east-1"
ACCOUNT = "926827998536"
ECR_URI = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/thumbnail-generator-ui:latest"
SERVICE = "thumbnail-generator-ui"
ROLE    = "thumbnail-ui-apprunner-role"

lines = []

def save():
    open("C:/tgen/apprunner_result.txt", "w", encoding="utf-8").write("\n".join(lines))

# ── Step 1: Create IAM role for App Runner to pull from ECR ───────────────
iam = boto3.client("iam")
trust = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "build.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
})
try:
    r = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=trust)
    role_arn = r["Role"]["Arn"]
    iam.attach_role_policy(
        RoleName=ROLE,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
    )
    lines.append(f"IAM role created: {role_arn}")
    lines.append("Waiting 15s for role propagation...")
    save(); time.sleep(15)
except iam.exceptions.EntityAlreadyExistsException:
    role_arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
    lines.append(f"IAM role exists: {role_arn}")
save()

# ── Step 2: Create App Runner service ─────────────────────────────────────
runner = boto3.client("apprunner", region_name=REGION)

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
                    }
                }
            },
            "AuthenticationConfiguration": {"AccessRoleArn": role_arn},
            "AutoDeploymentsEnabled": False
        },
        InstanceConfiguration={"Cpu": "0.25 vCPU", "Memory": "0.5 GB"},
    )
    svc = resp["Service"]
    lines.append(f"\nApp Runner service CREATED!")
    lines.append(f"Status  : {svc['Status']}")
    lines.append(f"Service : {svc['ServiceArn']}")
    lines.append(f"URL     : https://{svc['ServiceUrl']}")
    lines.append(f"\nNOTE: It takes 2-3 minutes to become fully running.")
    lines.append(f"Your public URL: https://{svc['ServiceUrl']}")

except runner.exceptions.InvalidRequestException as e:
    if "already exists" in str(e):
        svcs = runner.list_services()["ServiceSummaryList"]
        for s in svcs:
            if s["ServiceName"] == SERVICE:
                lines.append(f"Service already exists!")
                lines.append(f"Public URL: https://{s['ServiceUrl']}")
    else:
        lines.append(f"ERROR creating service: {e}")
except Exception as e:
    lines.append(f"UNEXPECTED ERROR: {e}")

save()
print("\n".join(lines))
