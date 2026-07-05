import subprocess
result = subprocess.run(["git", "status"], capture_output=True, text=True, cwd=r"D:\code\py\ROCO\roco-kingdom-world-pet-warehouse")
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("RC:", result.returncode)
