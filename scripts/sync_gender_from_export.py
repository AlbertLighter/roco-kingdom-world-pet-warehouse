"""
从 data/ 目录的 RKMS 抓包导出 JSON 中读取 ZoneGetPetInfoByPageRsp 响应，
将宠物的 gender 写入 warehouse.db 的 pet_instances 表。

匹配规则：ZoneGetPetInfoByPageRsp.pet_info.pet_data[].gid == pet_instances.serial_num

用法：
  python scripts/sync_gender_from_export.py          # 独立运行
  python scripts/sync_gender_from_export.py data/my_export.json  # 指定文件

作为模块导入：
  from scripts.sync_gender_from_export import sync_gender_from_export
  result = sync_gender_from_export(progress_callback=my_cb)
"""

import json
import os
import sqlite3
import glob

# Resolve paths relative to project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_PROJECT_ROOT, "warehouse.db")
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")


def _find_export_files():
    """扫描 data/ 目录下所有 JSON 文件，返回文件路径列表。"""
    pattern = os.path.join(_DATA_DIR, "*.json")
    return sorted(glob.glob(pattern))


def _scan_file_for_gender(filepath, progress_callback=None):
    """
    从单个 JSON 文件中提取所有 ZoneGetPetInfoByPageRsp 的 gid → gender 映射。
    返回: {gid: gender, ...}
    """
    if progress_callback:
        progress_callback(f"正在解析 {os.path.basename(filepath)}...", 0, 0)

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    gid_gender = {}
    total_rsp = 0
    total_pets = 0

    for entry in data:
        if entry.get("opcode_name") == "ZoneGetPetInfoByPageRsp" and entry.get("decoded"):
            total_rsp += 1
            pet_data = entry["decoded"].get("pet_info", {}).get("pet_data", [])
            for pet in pet_data:
                gid = pet.get("gid")
                gender = pet.get("gender")
                if gid is not None and gender is not None:
                    gid_gender[gid] = gender
                    total_pets += 1

    if progress_callback:
        progress_callback(
            f"解析完成：{total_rsp} 条响应，{len(gid_gender)} 个唯一 gid", 0, 0
        )

    return gid_gender


def sync_gender_from_export(filepath=None, progress_callback=None):
    """
    从 RKMS 导出文件中提取 gender 并更新数据库。

    参数:
        filepath: 指定 JSON 文件路径。若为 None，自动扫描 data/ 目录。
        progress_callback: 进度回调函数(message, current, total)

    返回:
        {"updated": int, "matched": int, "total_in_db": int, "source": str}
    """
    def report(message, current=0, total=0):
        if progress_callback:
            progress_callback(message, current, total)
        else:
            print(message)

    # 1. 确定源文件
    if filepath:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")
        source_files = [filepath]
    else:
        source_files = _find_export_files()
        if not source_files:
            raise FileNotFoundError(
                f"data/ 目录下未找到 JSON 文件（搜索路径: {_DATA_DIR}）"
            )

    report(f"找到 {len(source_files)} 个 JSON 文件", 0, 0)

    # 2. 解析所有文件，合并 gid→gender 映射
    all_gid_gender = {}
    for sf in source_files:
        gid_map = _scan_file_for_gender(sf, progress_callback)
        all_gid_gender.update(gid_map)

    if not all_gid_gender:
        report("⚠ 未从导出数据中找到任何 ZoneGetPetInfoByPageRsp 响应", 0, 0)
        return {"updated": 0, "matched": 0, "total_in_db": 0, "source": ";".join(source_files)}

    report(f"共解析到 {len(all_gid_gender)} 个唯一 gid", 0, len(all_gid_gender))

    # 3. 连接数据库，执行更新
    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()

    # 统计数据库中匹配的 serial_num
    gid_list = list(all_gid_gender.keys())
    placeholders = ",".join("?" * len(gid_list))
    cursor.execute(
        f"SELECT COUNT(*) FROM pet_instances WHERE serial_num IN ({placeholders})",
        gid_list,
    )
    matched = cursor.fetchone()[0]
    report(f"数据库匹配: {matched}/{len(all_gid_gender)} 个 gid", 0, matched)

    # 按 serial_num 排序逐条更新
    cursor.execute("SELECT serial_num, gender FROM pet_instances ORDER BY serial_num")
    rows = cursor.fetchall()
    total = len(rows)
    updated = 0
    checked = 0

    for serial_num, old_gender in rows:
        if serial_num in all_gid_gender:
            new_gender = all_gid_gender[serial_num]
            if old_gender != new_gender:
                cursor.execute(
                    "UPDATE pet_instances SET gender = ? WHERE serial_num = ?",
                    (new_gender, serial_num),
                )
                updated += 1
            checked += 1
            if checked % 100 == 0:
                report(f"处理中... {checked}/{total}", checked, total)

    conn.commit()
    conn.close()

    source_name = os.path.basename(source_files[0]) if len(source_files) == 1 else f"{len(source_files)} 个文件"
    report(f"完成！更新 {updated} 条记录（匹配 {matched}/{total}）", total, total)

    return {
        "updated": updated,
        "matched": matched,
        "total_in_db": total,
        "source": source_name,
    }


if __name__ == "__main__":
    import sys
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    result = sync_gender_from_export(filepath)
    print(f"\n结果: 更新 {result['updated']} 条（匹配 {result['matched']} 条）")
