import boto3, time, datetime

REGION = "us-east-1"
INTAKE = "intake-bucket-926827998536"
OUTPUT = "output-bucket-926827998536"
FUNC   = "thumbnail-generator"

s3   = boto3.client("s3", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)

lines = []

# Upload fresh test file
test_key = f"test_{int(time.time())}.jpg"
s3.upload_file(r"C:\tgen\sample.jpg", INTAKE, test_key)
lines.append(f"Uploaded: s3://{INTAKE}/{test_key}")
lines.append("Waiting 25s for Lambda...")
time.sleep(25)

# Check output bucket
resp = s3.list_objects_v2(Bucket=OUTPUT)
contents = resp.get("Contents", [])
if contents:
    lines.append(f"\nSUCCESS! Output bucket has {len(contents)} file(s):")
    for obj in contents:
        lines.append(f"  {obj['Key']}  ({obj['Size']} bytes)")
else:
    lines.append("\nOutput bucket still empty — checking logs...")

# Get recent Lambda logs
try:
    log_group = f"/aws/lambda/{FUNC}"
    streams = logs.describe_log_streams(
        logGroupName=log_group,
        orderBy="LastEventTime",
        descending=True,
        limit=1
    )
    if streams["logStreams"]:
        stream = streams["logStreams"][0]["logStreamName"]
        events = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream,
            limit=30
        )
        lines.append(f"\nLatest log stream: {stream}")
        for e in events["events"]:
            lines.append(e["message"].rstrip())
except Exception as ex:
    lines.append(f"Could not fetch logs: {ex}")

result = "\n".join(lines)
print(result)
open("C:/tgen/test_result.txt", "w", encoding="utf-8").write(result)
