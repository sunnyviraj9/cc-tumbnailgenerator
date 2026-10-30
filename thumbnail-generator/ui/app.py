"""
ui/app.py
─────────
Local Flask web UI for the Serverless Thumbnail Generator.
- Upload images/PDFs to intake-bucket-926827998536
- Polls output-bucket-926827998536 and displays thumbnails
"""

import os, time, boto3, threading
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import io

app = Flask(__name__)

REGION         = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
INTAKE_BUCKET  = os.environ.get("INTAKE_BUCKET", "intake-bucket-926827998536")
OUTPUT_BUCKET  = os.environ.get("OUTPUT_BUCKET", "output-bucket-926827998536")
ALLOWED_EXTS = {"jpg", "jpeg", "png", "pdf"}

s3 = boto3.client("s3", region_name=REGION)

def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS

@app.route("/")
def index():
    return render_template("index.html",
                           intake=INTAKE_BUCKET,
                           output=OUTPUT_BUCKET)

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file selected"}), 400
    f = request.files["file"]
    if f.filename == "" or not allowed(f.filename):
        return jsonify({"error": "Unsupported file type. Use jpg, jpeg, png or pdf."}), 400

    key = secure_filename(f.filename)
    s3.upload_fileobj(f, INTAKE_BUCKET, key)
    return jsonify({"success": True, "key": key,
                    "message": f"Uploaded {key} — thumbnail will appear in ~10 seconds"})

@app.route("/thumbnails")
def thumbnails():
    """List all objects in the output bucket."""
    try:
        resp = s3.list_objects_v2(Bucket=OUTPUT_BUCKET)
        items = []
        for obj in resp.get("Contents", []):
            items.append({
                "key":  obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S UTC")
            })
        items.sort(key=lambda x: x["last_modified"], reverse=True)
        return jsonify(items)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/thumbnail/<path:key>")
def get_thumbnail(key):
    """Proxy the thumbnail image from S3 so browser can display it."""
    buf = io.BytesIO()
    s3.download_fileobj(OUTPUT_BUCKET, key, buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/png",
                     download_name=key.split("/")[-1])

if __name__ == "__main__":
    print("\n  Thumbnail Generator UI")
    print(f"  Intake  : s3://{INTAKE_BUCKET}")
    print(f"  Output  : s3://{OUTPUT_BUCKET}")
    print(f"\n  Open your browser at: http://localhost:5000\n")
    app.run(debug=False, port=5000)
