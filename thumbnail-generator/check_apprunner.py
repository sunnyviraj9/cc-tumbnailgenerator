import boto3

runner = boto3.client("apprunner", region_name="us-east-1")
svcs = runner.list_services()["ServiceSummaryList"]

lines = []
for s in svcs:
    if "thumbnail" in s["ServiceName"]:
        lines.append(f"Service : {s['ServiceName']}")
        lines.append(f"Status  : {s['Status']}")
        lines.append(f"URL     : https://{s['ServiceUrl']}")

result = "\n".join(lines)
print(result)
open("C:/tgen/apprunner_status.txt", "w").write(result)
