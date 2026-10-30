"""
Runs the test suite and writes a human-readable summary to test_results.txt
so results survive the terminal buffer limit.
"""
import subprocess, sys, pathlib

out_file = pathlib.Path("C:/tgen/test_results.txt")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_local.py",
     "--tb=short", "-rsa", "-v", "--no-header"],
    capture_output=True, text=True, cwd="C:/tgen"
)

output = result.stdout + result.stderr
out_file.write_text(output, encoding="utf-8")
print(output[-4000:])   # print last 4000 chars (fits in one tool response)
print("Exit code:", result.returncode)
