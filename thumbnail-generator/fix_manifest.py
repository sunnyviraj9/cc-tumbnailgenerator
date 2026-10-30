import boto3, json, base64, urllib.request, urllib.error, traceback, subprocess, sys

REGION   = "us-east-1"
ACCOUNT  = "926827998536"
REPO     = "thumbnail-generator"
TAG      = "latest"
REGISTRY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"
OUT      = "C:/tgen/fix_result.txt"

lines = []

def get_ecr_token():
    """Get ECR Bearer token via AWS CLI v2 (most reliable method)."""
    result = subprocess.run(
        [r"C:\Program Files\Amazon\AWSCLIV2\aws.exe",
         "ecr", "get-login-password", "--region", REGION],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("get-login-password failed: " + result.stderr)
    return result.stdout.strip()

def ecr_request(password, path, method="GET", data=None, accept=None, content_type=None):
    """Make an authenticated ECR registry API request."""
    # ECR uses HTTP Basic auth for registry API (user=AWS, pass=token)
    creds = base64.b64encode(f"AWS:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {creds}"}
    if accept:
        headers["Accept"] = accept
    if content_type:
        headers["Content-Type"] = content_type
    url = f"https://{REGISTRY}{path}"
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    return urllib.request.urlopen(req)

def run():
    password = get_ecr_token()
    lines.append("Auth OK")

    # Fetch OCI index
    with ecr_request(password,
                     f"/v2/{REPO}/manifests/{TAG}",
                     accept="application/vnd.oci.image.index.v1+json") as r:
        index_bytes = r.read()
    index = json.loads(index_bytes)
    lines.append("Index mediaType: " + index.get("mediaType", "NOT SET"))
    lines.append("Manifests in index: " + str(len(index.get("manifests", []))))

    # Find linux/amd64 child (skip attestation)
    amd64 = next(
        (m for m in index.get("manifests", [])
         if m.get("platform", {}).get("architecture") == "amd64"
         and "attestation" not in m.get("mediaType", "")),
        None
    )
    if not amd64:
        lines.append("ERROR: no linux/amd64 child found in index")
        return

    child_digest = amd64["digest"]
    lines.append("amd64 child digest: " + child_digest)

    # Fetch child Docker v2 manifest
    with ecr_request(password,
                     f"/v2/{REPO}/manifests/{child_digest}",
                     accept="application/vnd.docker.distribution.manifest.v2+json") as r:
        child_bytes = r.read()
    child = json.loads(child_bytes)
    lines.append("Child mediaType: " + child.get("mediaType", "NOT SET"))

    # PUT the child manifest as 'latest' tag
    try:
        with ecr_request(password,
                         f"/v2/{REPO}/manifests/{TAG}",
                         method="PUT",
                         data=child_bytes,
                         content_type="application/vnd.docker.distribution.manifest.v2+json") as r:
            new_digest = r.headers.get("Docker-Content-Digest", "check ECR")
            lines.append("SUCCESS — latest now points to Docker v2 manifest")
            lines.append("New digest: " + new_digest)
    except urllib.error.HTTPError as e:
        lines.append(f"PUT failed {e.code}: " + e.read().decode())

try:
    run()
except Exception:
    lines.append("EXCEPTION:\n" + traceback.format_exc())

result = "\n".join(lines)
print(result)
open(OUT, "w", encoding="utf-8").write(result)
