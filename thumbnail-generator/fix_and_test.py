import boto3, subprocess, time, json, datetime

AWS = r"C:\Program Files\Amazon\AWSCLIV2\aws.exe"
REGION = "us-east-1"
ACCOUNT = "926827998536"
INTAKE  = f"intake-bucket-{ACCOUNT}"
OUTPUT  = f"output-bucket-{ACCOUNT}"
ROLE    = "thumbnail-generator-role"
FUNC    = "thumbnail-generator"

lines = []

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

# ── Step 1: Fix IAM policy ─────────────────────────────────────────────────
lines.append("=== Step 1: Updating IAM policy ===")
policy = json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {"Effect":"Allow","Action":["s3:GetObject"],
         "Resource": f"arn:aws:s3:::{INTAKE}/*"},
        {"Effect":"Allow","Action":["s3:PutObject"],
         "Resource": f"arn:aws:s3:::{OUTPUT}/*"}
    ]
})
out, err, rc = run([AWS, "iam", "put-role-policy",
    "--role-name", ROLE,
    "--policy-name", "ThumbnailS3Policy",
    "--policy-document", policy])
if rc == 0:
    lines.append("IAM policy updated OK")
else:
    lines.append(f"IAM policy ERROR: {err}")

# ── Step 2: Wait for Lambda to be ready ────────────────────────────────────
lines.append("\n=== Step 2: Waiting for Lambda to be active ===")
out, err, rc = run([AWS, "lambda", "wait", "function-updated",
    "--function-name", FUNC, "--region", REGION])
lines.append("Lambda active" if rc == 0 else f"Wait error: {err}")

# ── Step 3: Upload test file ────────────────────────────────────────────────
lines.append("\n=== Step 3: Uploading test image ===")
test_key = f"test_{int(time.time())}.jpg"
out, err, rc = run([AWS, "s3", "cp", r"C:\tgen\sample.jpg",
    f"s3://{INTAKE}/{test_key}"])
if rc == 0:
    lines.append(f"Uploaded: s3://{INTAKE}/{test_key}")
else:
    lines.append(f"Upload ERROR: {err}")

# ── Step 4: Wait for Lambda to process ─────────────────────────────────────
lines.append("\n=== Step 4: Waiting 20s for Lambda to process ===")
time.sleep(20)

# ── Step 5: Check output bucket ────────────────────────────────────────────
lines.append("\n=== Step 5: Checking output bucket ===")
out, err, rc = run([AWS, "s3", "ls", f"s3://{OUTPUT}/"])
if out:
    lines.append("Output bucket contents:")
    lines.append(out)
else:
    lines.append("Output bucket is EMPTY — Lambda may have errored")
    lines.append(f"ls stderr: {err}")

# ── Step 6: Get latest Lambda logs ─────────────────────────────────────────
lines.append("\n=== Step 6: Latest Lambda logs ===")
out, err, rc = run([AWS, "logs", "tail",
    f"/aws/lambda/{FUNC}",
    "--region", REGION,
    "--since", "2m"])
if out:
    lines.append(out[-3000:])
else:
    lines.append(f"No logs yet: {err}")

result = "\n".join(lines)
print(result)
open("C:/tgen/test_result.txt", "w", encoding="utf-8").write(result)
