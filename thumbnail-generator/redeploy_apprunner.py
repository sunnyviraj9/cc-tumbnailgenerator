import boto3, json, time

REGION  = "us-east-1"
ACCOUNT = "926827998536"
SERVICE = "thumbnail-generator-ui"
ECR_URI = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/thumbnail-generator-ui:latest"
INTAKE  = f"intake-bucket-{ACCOUNT}"
OUTPUT  = f"output-bucket-{ACCOUNT}"
ACCESS_ROLE  = "thumbnail-ui-apprunner-role"
INSTANCE_ROLE = "thumbnail-ui-instance-role"

iam    = boto3.client("iam")
runner = boto3.client("apprunner", region_name=REGION)

lines = []

access_role_arn   = iam.get_role(RoleName=ACCESS_ROLE)["Role"]["Arn"]
instance_role_arn = iam.get_role(RoleName=INSTANCE_ROLE)["Role"]["Arn"]
lines.append(f"Access role   : {access_role_arn}")
lines.append(f"Instance role : {instance_role_arn}")

# Delete existing failed service
svcs = runner.list_services()["ServiceSummaryList"]
svc_arn = next((s["ServiceArn"] for s in svcs if s["ServiceName"] == SERVICE), None)
if svc_arn:
    lines.append(f"Deleting existing service: {svc_arn}")
    runner.delete_service(ServiceArn=svc_arn)
    # Poll until deleted
    for _ in range(20):
        time.sleep(10)
        try:
            svcs2 = runner.list_services()["ServiceSummaryList"]
            if not any(s["ServiceName"] == SERVICE for s in svcs2):
                lines.append("Service deleted.")
                break
        except Exception:
            break
else:
    lines.append("No existing service to delete.")

# Create fresh service
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
lines.append(f"\nService created! Status: {svc['Status']}")
lines.append(f"Public URL: https://{svc['ServiceUrl']}")

result = "\n".join(lines)
print(result)
open("C:/tgen/redeploy_result.txt", "w", encoding="utf-8").write(result)
