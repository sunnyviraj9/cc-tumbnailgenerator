# Serverless PDF & Image Thumbnail Generator

A containerised AWS Lambda function that watches an S3 **intake-bucket**, generates
200×200 thumbnails from uploaded images (`.jpg`, `.jpeg`, `.png`) and PDFs (`.pdf`),
and writes the results to an S3 **output-bucket** — all without managing any servers.

---

## Architecture

```
┌─────────────────────┐      s3:ObjectCreated:*      ┌──────────────────────────────┐
│   intake-bucket     │ ──────────────────────────►  │  Lambda (container image)    │
│  (jpg/png/pdf)      │                               │  • Pillow  (image resize)    │
└─────────────────────┘                               │  • pdf2image + Poppler       │
                                                      │    (PDF → PNG render)        │
                                                      └──────────────┬───────────────┘
                                                                     │ PutObject
                                                                     ▼
                                                      ┌─────────────────────────────┐
                                                      │   output-bucket             │
                                                      │  thumb_<original_name>.png  │
                                                      └─────────────────────────────┘
```

---

## Project Structure

```
thumbnail-generator/
├── Dockerfile              # Multi-stage build (Poppler + Python packages)
├── requirements.txt        # Python dependencies
├── deploy.sh               # Full AWS deployment script (ECR + Lambda + S3 trigger)
├── README.md               # This file
├── src/
│   └── lambda_function.py  # Lambda handler — processing logic
├── tests/
│   └── test_local.py       # Offline pytest suite (no AWS needed)
└── sample_files/           # Drop test images/PDFs here for local testing
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Local test runner |
| Docker | 20.10+ | Build container image |
| AWS CLI | v2 | Deploy to AWS |
| Poppler | any | PDF rendering (installed inside Docker; install locally for PDF tests) |
| jq | any | JSON parsing in deploy.sh |

---

## Local Setup & Testing

### 1. Install Python dependencies

```bash
pip install Pillow==10.3.0 pdf2image==1.17.0 pytest
```

### 2. (Optional) Install Poppler locally for PDF tests

**macOS:**
```bash
brew install poppler
```

**Ubuntu / Debian:**
```bash
sudo apt-get install -y poppler-utils
```

**Windows:**
Download the [Windows poppler build](https://github.com/oschwartz10612/poppler-windows/releases)
and add the `bin/` directory to your `PATH`.

### 3. Add sample files

Place a `.jpg`, `.png`, and/or `.pdf` in the `sample_files/` directory.

### 4. Run the test suite

```bash
# From the project root
pytest tests/test_local.py -v
```

Expected output (without Poppler):
```
tests/test_local.py::TestImageThumbnail::test_png_large_landscape_is_resized PASSED
tests/test_local.py::TestImageThumbnail::test_jpeg_is_resized PASSED
...
tests/test_local.py::TestPdfThumbnail::test_pdf_page1_is_rendered_and_resized SKIPPED (Poppler not available)
```

---

## AWS Deployment

### 1. Configure environment variables

Edit the top section of `deploy.sh`:

```bash
AWS_ACCOUNT_ID="123456789012"   # Your 12-digit AWS account ID
AWS_REGION="us-east-1"
AWS_PROFILE="default"           # AWS CLI profile name
```

Or export them as environment variables before running:

```bash
export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=us-east-1
export AWS_PROFILE=my-profile
```

### 2. Run the deployment script

```bash
chmod +x deploy.sh
./deploy.sh
```

The script performs these steps automatically:
1. Creates `intake-bucket` and `output-bucket`
2. Creates an ECR repository
3. Authenticates Docker with ECR
4. Builds and pushes the container image
5. Creates the IAM role and attaches required policies
6. Creates or updates the Lambda function
7. Grants S3 permission to invoke Lambda
8. Configures S3 event notifications for `.jpg`, `.jpeg`, `.png`, `.pdf`

### 3. Test the live deployment

```bash
# Upload a test image
aws s3 cp sample_files/sample.jpg s3://intake-bucket/ --profile default

# Check the output bucket for the thumbnail
aws s3 ls s3://output-bucket/ --profile default
```

---

## IAM Policy Reference

The deployment script creates this IAM role automatically.
If you need to create it manually, use the following policies:

### Trust Policy (for Lambda to assume the role)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Inline Permission Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadFromIntakeBucket",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::intake-bucket/*"
    },
    {
      "Sid": "WriteToOutputBucket",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::output-bucket/*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

> The `AWSLambdaBasicExecutionRole` managed policy is also attached for
> CloudWatch Logs access and is included in the deployment script.

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OUTPUT_BUCKET` | `output-bucket` | Name of the S3 bucket to write thumbnails to |

Set via the Lambda console or in `deploy.sh` under `--environment`.

---

## Thumbnail Behaviour

| Input | Processing | Output |
|-------|-----------|--------|
| `.jpg` / `.jpeg` | Resize proportionally to ≤ 200×200 | `thumb_<name>.png` |
| `.png` | Resize proportionally to ≤ 200×200 | `thumb_<name>.png` |
| `.pdf` | Render page 1 at 150 DPI, then resize to ≤ 200×200 | `thumb_<name>.png` |
| Other | Logged as unsupported, skipped | — |
| Corrupt file | Logged as error, skipped | — |

---

## Monitoring & Debugging

View Lambda logs in CloudWatch:

```bash
aws logs tail /aws/lambda/thumbnail-generator --follow --profile default
```

Or in the AWS Console:
**CloudWatch → Log groups → /aws/lambda/thumbnail-generator**

---

## Cost Estimate (approximate)

| Service | Free Tier | Beyond Free Tier |
|---------|-----------|-----------------|
| Lambda | 1M requests / month | $0.20 per 1M requests |
| S3 | 5 GB storage | $0.023 per GB |
| ECR | 500 MB / month | $0.10 per GB |

For typical development usage this project runs within the AWS Free Tier.

---

## Clean Up

To avoid ongoing charges, delete resources when done:

```bash
# Delete Lambda function
aws lambda delete-function --function-name thumbnail-generator

# Delete ECR repository and all images
aws ecr delete-repository --repository-name thumbnail-generator --force

# Empty and delete S3 buckets
aws s3 rm s3://intake-bucket --recursive
aws s3 rb s3://intake-bucket
aws s3 rm s3://output-bucket --recursive
aws s3 rb s3://output-bucket

# Delete IAM role
aws iam delete-role-policy --role-name thumbnail-generator-role --policy-name ThumbnailGeneratorS3Policy
aws iam detach-role-policy --role-name thumbnail-generator-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name thumbnail-generator-role
```
