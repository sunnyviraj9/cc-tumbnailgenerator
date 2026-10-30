import boto3, datetime
from botocore.exceptions import ClientError

REGION = "us-east-1"
ACCOUNT = "926827998536"
BUCKETS = [
    f"intake-bucket-{ACCOUNT}",
    f"output-bucket-{ACCOUNT}",
]

s3 = boto3.client("s3", region_name=REGION)
lines = [f"Run at: {datetime.datetime.now()}"]

for bucket in BUCKETS:
    try:
        s3.create_bucket(Bucket=bucket)
        lines.append(f"CREATED  s3://{bucket}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            lines.append(f"EXISTS   s3://{bucket}")
        else:
            lines.append(f"ERROR    s3://{bucket} — {code}: {e}")

lines.append("\nBucket names to use:")
for b in BUCKETS:
    lines.append(f"  {b}")

out = "\n".join(lines)
print(out)
open("C:/tgen/bucket_results.txt", "w").write(out)
