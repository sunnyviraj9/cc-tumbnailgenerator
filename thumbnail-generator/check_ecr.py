import boto3, json, sys

ecr = boto3.client("ecr", region_name="us-east-1")
lines = []

# Get the manifest to see if it's OCI index or plain Docker manifest
resp = ecr.batch_get_image(
    repositoryName="thumbnail-generator",
    imageIds=[{"imageTag": "latest"}],
    acceptedMediaTypes=[
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.oci.image.index.v1+json",
    ]
)

for img in resp["images"]:
    manifest = json.loads(img["imageManifest"])
    lines.append("Media type: " + manifest.get("mediaType", "NOT SET (OCI index)"))
    lines.append("Schema version: " + str(manifest.get("schemaVersion")))
    lines.append("Manifests count: " + str(len(manifest.get("manifests", []))))

out = "\n".join(lines)
print(out)
open("C:/tgen/ecr_result.txt", "w").write(out)
