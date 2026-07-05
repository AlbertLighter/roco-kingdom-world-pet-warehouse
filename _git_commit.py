import subprocess
import os

os.chdir(r"D:\code\py\ROCO\roco-kingdom-world-pet-warehouse")

# git add -A
r = subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
if r.returncode != 0:
    print("ADD ERROR:", r.stderr)
else:
    print("ADD OK")

# git commit
msg = """放生推荐支持多性格偏好 + 默认保留数改为 3

- 数据库: species_preferences 新增 preferred_nature_ids TEXT 列，keep_count 默认 1→3
- 评分: compute_pet_score 改为接受性格 ID 列表，匹配任一即满分
- 原因分析: 性格不匹配判断改为 not in 列表
- API: get/put species_preferences 收发 preferred_nature_ids 数组
- 前端: 性格选择改为 <select multiple> 支持 Ctrl 多选, 默认保留数 3
- 文档: 同步更新默认值和性格分说明"""

r = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
print("STDOUT:", r.stdout)
print("STDERR:", r.stderr)
print("RC:", r.returncode)
