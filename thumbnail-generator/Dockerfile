# ──────────────────────────────────────────────────────────────────────────────
# Lambda-compatible container image
# Uses the official AWS Lambda Python 3.10 base (AL2, amd64)
# ──────────────────────────────────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.10

# Install Poppler (PDF rendering engine)
RUN yum install -y poppler-utils && yum clean all

# Copy pre-downloaded wheels and install — no network access needed
COPY packages/ /tmp/packages/
COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir \
        --no-index \
        --find-links /tmp/packages/ \
        -r /tmp/requirements.txt \
        --target /var/task/

# Copy Lambda handler
COPY src/lambda_function.py /var/task/lambda_function.py

CMD ["lambda_function.handler"]
