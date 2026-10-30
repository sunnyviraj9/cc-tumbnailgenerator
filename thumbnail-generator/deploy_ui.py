"""
Deploys the Flask UI to AWS App Runner.
App Runner builds and hosts the container, gives a public HTTPS URL.
"""
import boto3, subprocess, base64, json, time

REGION   = "us-east-1"
ACCOUNT  = "926827998536"
AWS_CLI  = r"C:\Program Files\Amazon\AWSCLIV2\aws.exe"
ECR_REPO = "thumbnail-generator-ui"
ECR_URI  = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{ECR_REPO}"
UI_DIR   = r"C:\Users\SUNNY VIRAJ\OneDrive - Shri Vile Parle Kelavani Mandal\cc-project\thumbnail-generator\ui"
SERVICE  = "thumbnail-generator-ui"

lines = []

def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def save(extra=""):
    out = "\n".join(lines) + ("\n" + extra if extra else "")
    open("C:/tgen/deploy_ui_result.txt", "w", encoding="utf-8").write(out)

# ── Step 1: Create ECR repo for UI ────────────────────────────────────────
lines.append("=== Step 1: Creating ECR repo for UI ===")
ecr = boto3.client("ecr", region_name=REGION)
try:
    ecr.create_repository(repositoryName=ECR_REPO)
    lines.append(f"ECR repo created: {ECR_REPO}")
except ecr.exceptions.RepositoryAlreadyExistsException:
    lines.append(f"ECR repo already exists: {ECR_REPO}")
save()

# ── Step 2: Build Docker image ────────────────────────────────────────────
lines.append("\n=== Step 2: Building UI Docker image ===")
out, err, rc = run(
    ["docker", "build", "--platform", "linux/amd64",
     "--provenance=false", "-t", f"{ECR_REPO}:latest", "."],
    cwd=UI_DIR
)
if rc == 0:
    lines.append("Docker build OK")
else:
    lines.append(f"Docker build FAILED:\n{err}")
    save(); raise SystemExit(1)
save()

# ── Step 3: Auth + push to ECR ───────────────────────────────────────────
lines.append("\n=== Step 3: Pushing to ECR ===")
out, err, rc = run([AWS_CLI, "ecr", "get-login-password", "--region", REGION])
password = out
_, _, rc2 = run(["docker", "login", "--username", "AWS",
                  "--password-stdin",
                  f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"],
                 cwd=None)
if rc2 != 0:
    # pipe manually
    import subprocess as sp
    login = sp.Popen(
        ["docker", "login", "--username", "AWS", "--password-stdin",
         f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"],
        stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE, text=True
    )
    login.communicate(input=password)

run(["docker", "tag", f"{ECR_REPO}:latest", f"{ECR_URI}:latest"])
out, err, rc = run(["docker", "push", f"{ECR_URI}:latest"])
if "digest" in out.lower() or rc == 0:
    lines.append(f"Pushed: {ECR_URI}:latest")
else:
    lines.append(f"Push output: {out}\n{err}")
save()

# ── Step 4: Create App Runner IAM role ───────────────────────────────────
lines.append("\n=== Step 4: Creating App Runner IAM role ===")
iam = boto3.client("iam")
RUNNER_ROLE = "thumbnail-ui-apprunner-role"

trust = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "build.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
})
try:
    role = iam.create_role(RoleName=RUNNER_ROLE,
                           AssumeRolePolicyDocument=trust)
    role_arn = role["Role"]["Arn"]
    iam.attach_role_policy(
        RoleName=RUNNER_ROLE,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
    )
    lines.append(f"Role created: {role_arn}")
    lines.append("Waiting 15s for role propagation...")
    time.sleep(15)
except iam.exceptions.EntityAlreadyExistsException:
    role_arn = iam.get_role(RoleName=RUNNER_ROLE)["Role"]["Arn"]
    lines.append(f"Role exists: {role_arn}")
save()

# ── Step 5: Create App Runner service ────────────────────────────────────
lines.append("\n=== Step 5: Creating App Runner service ===")
runner = boto3.client("apprunner", region_name=REGION)

# Get the image digest
images = ecr.describe_images(repositoryName=ECR_REPO,
                              imageIds=[{"imageTag":"latest"}])
image_uri = f"{ECR_URI}:latest"

try:
    resp = runner.create_service(
        ServiceName=SERVICE,
        SourceConfiguration={
            "ImageRepository": {
                "ImageIdentifier": image_uri,
                "ImageRepositoryType": "ECR",
                "ImageConfiguration": {
                    "Port": "8080",
                    "RuntimeEnvironmentVariables": {
                        "AWS_DEFAULT_REGION": REGION,
                        "INTAKE_BUCKET": f"intake-bucket-{ACCOUNT}",
                        "OUTPUT_BUCKET": f"output-bucket-{ACCOUNT}",
                    }
                }
            },
            "AuthenticationConfiguration": {"AccessRoleArn": role_arn},
            "AutoDeploymentsEnabled": False
        },
        InstanceConfiguration={"Cpu": "0.25 vCPU", "Memory": "0.5 GB"},
    )
    svc = resp["Service"]
    lines.append(f"App Runner service created!")
    lines.append(f"Status: {svc['Status']}")
    lines.append(f"Service ARN: {svc['ServiceArn']}")
    lines.append(f"\nYour public URL will be:")
    lines.append(f"  https://{svc.get('ServiceUrl','(generating - check console in 2 min)')}")
except runner.exceptions.InvalidRequestException as e:
    if "already exists" in str(e):
        svcs = runner.list_services()
        for s in svcs["ServiceSummaryList"]:
            if s["ServiceName"] == SERVICE:
                lines.append(f"Service already exists!")
                lines.append(f"Public URL: https://{s['ServiceUrl']}")
    else:
        lines.append(f"ERROR: {e}")
save()

print("\n".join(lines))
