import boto3
runner = boto3.client("apprunner", region_name="us-east-1")
svcs = runner.list_services()["ServiceSummaryList"]
result = []
for s in svcs:
    if "thumbnail-generator-ui" in s["ServiceName"]:
        try:
            runner.delete_service(ServiceArn=s["ServiceArn"])
            result.append(f"DELETE_REQUESTED: {s['ServiceArn']} status_was={s['Status']}")
        except Exception as e:
            result.append(f"DELETE_ERROR: {e}")
if not result:
    result.append("NO_SERVICE_FOUND")
out = "\n".join(result)
print(out)
open("C:/tgen/delete_result.txt","w").write(out)
