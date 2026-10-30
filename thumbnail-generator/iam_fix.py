import boto3, json

iam = boto3.client("iam")
ROLE = "thumbnail-generator-role"
INTAKE  = "intake-bucket-926827998536"
OUTPUT  = "output-bucket-926827998536"

policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow", "Action": ["s3:GetObject"],
         "Resource": f"arn:aws:s3:::{INTAKE}/*"},
        {"Effect": "Allow", "Action": ["s3:PutObject"],
         "Resource": f"arn:aws:s3:::{OUTPUT}/*"}
    ]
}

iam.put_role_policy(
    RoleName=ROLE,
    PolicyName="ThumbnailS3Policy",
    PolicyDocument=json.dumps(policy)
)

# Verify
resp = iam.get_role_policy(RoleName=ROLE, PolicyName="ThumbnailS3Policy")
result = "IAM policy updated:\n" + json.dumps(resp["PolicyDocument"], indent=2)
print(result)
open("C:/tgen/iam_result.txt","w").write(result)
