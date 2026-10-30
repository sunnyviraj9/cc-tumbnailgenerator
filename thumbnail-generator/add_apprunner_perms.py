import boto3, json

iam = boto3.client("iam")

# Attach App Runner full access to the user
iam.attach_user_policy(
    UserName="sunnyvirajm",
    PolicyArn="arn:aws:iam::aws:policy/AWSAppRunnerFullAccess"
)
print("AWSAppRunnerFullAccess attached to sunnyvirajm")

# Also attach IAM role pass permission needed by App Runner
policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": "iam:PassRole",
        "Resource": "arn:aws:iam::926827998536:role/thumbnail-ui-apprunner-role"
    }]
}
iam.put_user_policy(
    UserName="sunnyvirajm",
    PolicyName="AppRunnerPassRole",
    PolicyDocument=json.dumps(policy)
)
print("PassRole policy attached")
open("C:/tgen/perms_result.txt","w").write("DONE")
