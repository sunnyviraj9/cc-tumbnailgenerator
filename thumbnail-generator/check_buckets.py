import boto3
s3 = boto3.client("s3", region_name="us-east-1")
resp = s3.list_buckets()
names = [b["Name"] for b in resp["Buckets"]]
result = "All buckets:\n" + "\n".join(f"  {n}" for n in names)
print(result)
open("C:/tgen/buckets.txt", "w").write(result)
