#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh
# Builds the Docker image, pushes it to AWS ECR, creates/updates the Lambda
# function, and configures the S3 trigger on the intake-bucket.
#
# Prerequisites:
#   - AWS CLI v2 configured with a profile that has the required IAM permissions
#   - Docker Desktop (or Docker Engine) running
#   - jq installed (for parsing AWS CLI JSON output)
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration — edit these values before running ─────────────────────────
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-123456789012}"   # Your 12-digit AWS account ID
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"

ECR_REPO_NAME="thumbnail-generator"
LAMBDA_FUNCTION_NAME="thumbnail-generator"
LAMBDA_ROLE_NAME="thumbnail-generator-role"

INTAKE_BUCKET="intake-bucket"
OUTPUT_BUCKET="output-bucket"

IMAGE_TAG="latest"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}"

# ── Helper ────────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 – Create S3 buckets (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
log "Creating S3 buckets (if they do not exist)..."

# us-east-1 does not accept a LocationConstraint — other regions require it.
if [ "${AWS_REGION}" = "us-east-1" ]; then
    aws s3api create-bucket \
        --bucket "${INTAKE_BUCKET}" \
        --region "${AWS_REGION}" \
        --profile "${AWS_PROFILE}" 2>/dev/null || true

    aws s3api create-bucket \
        --bucket "${OUTPUT_BUCKET}" \
        --region "${AWS_REGION}" \
        --profile "${AWS_PROFILE}" 2>/dev/null || true
else
    aws s3api create-bucket \
        --bucket "${INTAKE_BUCKET}" \
        --region "${AWS_REGION}" \
        --create-bucket-configuration LocationConstraint="${AWS_REGION}" \
        --profile "${AWS_PROFILE}" 2>/dev/null || true

    aws s3api create-bucket \
        --bucket "${OUTPUT_BUCKET}" \
        --region "${AWS_REGION}" \
        --create-bucket-configuration LocationConstraint="${AWS_REGION}" \
        --profile "${AWS_PROFILE}" 2>/dev/null || true
fi

log "S3 buckets ready: ${INTAKE_BUCKET}, ${OUTPUT_BUCKET}"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 – Create ECR repository (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
log "Ensuring ECR repository '${ECR_REPO_NAME}' exists..."
aws ecr describe-repositories \
    --repository-names "${ECR_REPO_NAME}" \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE}" > /dev/null 2>&1 || \
aws ecr create-repository \
    --repository-name "${ECR_REPO_NAME}" \
    --region "${AWS_REGION}" \
    --image-scanning-configuration scanOnPush=true \
    --profile "${AWS_PROFILE}"

log "ECR repository ready: ${ECR_URI}"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 – Authenticate Docker with ECR
# ─────────────────────────────────────────────────────────────────────────────
log "Authenticating Docker with ECR..."
aws ecr get-login-password \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE}" | \
docker login \
    --username AWS \
    --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 – Build and push Docker image
# ─────────────────────────────────────────────────────────────────────────────
log "Building Docker image..."
docker build \
    --platform linux/amd64 \
    -t "${ECR_REPO_NAME}:${IMAGE_TAG}" \
    -f Dockerfile \
    .

log "Tagging and pushing image to ECR..."
docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}"
docker push "${ECR_URI}"
log "Image pushed: ${ECR_URI}"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 – Create IAM role for Lambda (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
log "Ensuring IAM role '${LAMBDA_ROLE_NAME}' exists..."

TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "lambda.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}'

ROLE_ARN=$(aws iam get-role \
    --role-name "${LAMBDA_ROLE_NAME}" \
    --profile "${AWS_PROFILE}" \
    --query 'Role.Arn' \
    --output text 2>/dev/null) || true

if [ -z "${ROLE_ARN}" ]; then
    ROLE_ARN=$(aws iam create-role \
        --role-name "${LAMBDA_ROLE_NAME}" \
        --assume-role-policy-document "${TRUST_POLICY}" \
        --profile "${AWS_PROFILE}" \
        --query 'Role.Arn' \
        --output text)
    log "IAM role created: ${ROLE_ARN}"

    # Attach AWS-managed policies.
    aws iam attach-role-policy \
        --role-name "${LAMBDA_ROLE_NAME}" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
        --profile "${AWS_PROFILE}"

    # Attach inline policy for S3 read/write.
    S3_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::${INTAKE_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::${OUTPUT_BUCKET}/*"
    }
  ]
}
EOF
)
    aws iam put-role-policy \
        --role-name "${LAMBDA_ROLE_NAME}" \
        --policy-name "ThumbnailGeneratorS3Policy" \
        --policy-document "${S3_POLICY}" \
        --profile "${AWS_PROFILE}"

    log "IAM policies attached. Waiting 15 s for role propagation..."
    sleep 15
else
    log "IAM role already exists: ${ROLE_ARN}"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 – Create or update the Lambda function
# ─────────────────────────────────────────────────────────────────────────────
EXISTING_LAMBDA=$(aws lambda get-function \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE}" \
    --query 'Configuration.FunctionName' \
    --output text 2>/dev/null) || true

if [ -z "${EXISTING_LAMBDA}" ]; then
    log "Creating Lambda function '${LAMBDA_FUNCTION_NAME}'..."
    aws lambda create-function \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --package-type Image \
        --code ImageUri="${ECR_URI}" \
        --role "${ROLE_ARN}" \
        --timeout 60 \
        --memory-size 512 \
        --environment "Variables={OUTPUT_BUCKET=${OUTPUT_BUCKET}}" \
        --region "${AWS_REGION}" \
        --profile "${AWS_PROFILE}"
    log "Lambda function created."
else
    log "Updating Lambda function code to latest image..."
    aws lambda update-function-code \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --image-uri "${ECR_URI}" \
        --region "${AWS_REGION}" \
        --profile "${AWS_PROFILE}"
    log "Lambda function code updated."
fi

# Wait until the update is complete before adding the trigger.
log "Waiting for Lambda function to become active..."
aws lambda wait function-updated \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE}"

LAMBDA_ARN=$(aws lambda get-function \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE}" \
    --query 'Configuration.FunctionArn' \
    --output text)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 – Grant S3 permission to invoke Lambda
# ─────────────────────────────────────────────────────────────────────────────
log "Granting S3 permission to invoke Lambda..."
aws lambda add-permission \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --statement-id "S3InvokePermission" \
    --action "lambda:InvokeFunction" \
    --principal "s3.amazonaws.com" \
    --source-arn "arn:aws:s3:::${INTAKE_BUCKET}" \
    --source-account "${AWS_ACCOUNT_ID}" \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE}" 2>/dev/null || \
    log "  (permission already exists — skipped)"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 – Configure S3 event notification on intake-bucket
# ─────────────────────────────────────────────────────────────────────────────
log "Configuring S3 event notification on '${INTAKE_BUCKET}'..."

NOTIFICATION_CONFIG=$(cat <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "${LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            { "Name": "suffix", "Value": ".jpg" },
            { "Name": "suffix", "Value": ".jpeg" },
            { "Name": "suffix", "Value": ".png" },
            { "Name": "suffix", "Value": ".pdf" }
          ]
        }
      }
    }
  ]
}
EOF
)

# NOTE: S3 does not support multiple suffix filters in a single configuration
# block — each extension needs its own LambdaFunctionConfiguration entry.
# The config above is illustrative; see README.md for the production-ready
# multi-filter JSON.

NOTIFICATION_CONFIG_MULTI=$(cat <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "TriggerOnJpg",
      "LambdaFunctionArn": "${LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": { "Key": { "FilterRules": [{ "Name": "suffix", "Value": ".jpg" }] } }
    },
    {
      "Id": "TriggerOnJpeg",
      "LambdaFunctionArn": "${LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": { "Key": { "FilterRules": [{ "Name": "suffix", "Value": ".jpeg" }] } }
    },
    {
      "Id": "TriggerOnPng",
      "LambdaFunctionArn": "${LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": { "Key": { "FilterRules": [{ "Name": "suffix", "Value": ".png" }] } }
    },
    {
      "Id": "TriggerOnPdf",
      "LambdaFunctionArn": "${LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": { "Key": { "FilterRules": [{ "Name": "suffix", "Value": ".pdf" }] } }
    }
  ]
}
EOF
)

aws s3api put-bucket-notification-configuration \
    --bucket "${INTAKE_BUCKET}" \
    --notification-configuration "${NOTIFICATION_CONFIG_MULTI}" \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE}"

log "S3 trigger configured."

# ─────────────────────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────────────────────
log "──────────────────────────────────────────────────────────────"
log " Deployment complete!"
log "  Lambda : ${LAMBDA_ARN}"
log "  Intake : s3://${INTAKE_BUCKET}"
log "  Output : s3://${OUTPUT_BUCKET}"
log "──────────────────────────────────────────────────────────────"
log "Test by uploading a file:"
log "  aws s3 cp sample_files/sample.jpg s3://${INTAKE_BUCKET}/ --profile ${AWS_PROFILE}"
log "Then check the output bucket:"
log "  aws s3 ls s3://${OUTPUT_BUCKET}/ --profile ${AWS_PROFILE}"
