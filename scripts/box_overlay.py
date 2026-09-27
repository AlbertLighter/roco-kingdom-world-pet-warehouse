"""置顶半透明对照窗：一页一个盒子，方便对着游戏放生。"""

from __future__ import annotations

import json
import sys
import urllib.request
import tkinter as tk

API = "http://127.0.0.1:8000"


def fetch_json(path: str):
    with urllib.request.urlopen(API + path, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def release_serials() -> set[int]:
    try:
        data = fetch_json("/api/release_recommendations?page=1&page_size=5000")
    except Exception:
        return set()
    serials = set()
    for group in data.get("species_groups") or []:
        for serial in group.get("recommended_serials") or []:
            serials.add(int(serial))
    return serials


class Overlay:
    def __init__(self, start_page: int) -> None:
        self.page = max(1, start_page)
        self.release_ids = release_serials()
        self.root = tk.Tk()
        self.root.title("盒子对照")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.86)
        self.root.configure(bg="#1b2430")
        self.root.geometry("560x460")
        self._drag_x = 0
        self._drag_y = 0
        bar = tk.Frame(self.root, bg="#14202b")
        bar.pack(fill="x")
        bar.bind("<Button-1>", self._drag_start)
        bar.bind("<B1-Motion>", self._drag_move)
        self.title = tk.Label(bar, text="盒子对照", fg="#e8fff6", bg="#14202b", font=("Microsoft YaHei UI", 11, "bold"))
        self.title.pack(side="left", padx=10, pady=6)
        self.title.bind("<Button-1>", self._drag_start)
        self.title.bind("<B1-Motion>", self._drag_move)
        tk.Button(bar, text="关闭", command=self.root.destroy, bg="#3a4658", fg="white", relief="flat").pack(side="right", padx=8, pady=4)
        nav = tk.Frame(self.root, bg="#1b2430")
        nav.pack(fill="x", padx=8, pady=6)
        tk.Button(nav, text="上一盒", command=self.prev_box, bg="#0e6655", fg="white", relief="flat").pack(side="left")
        tk.Button(nav, text="下一盒", command=self.next_box, bg="#0e6655", fg="white", relief="flat").pack(side="left", padx=6)
        tk.Button(nav, text="刷新", command=self.reload, bg="#3a4658", fg="white", relief="flat").pack(side="left")
        self.summary = tk.Label(nav, text="", fg="#d5efe8", bg="#1b2430", font=("Microsoft YaHei UI", 9))
        self.summary.pack(side="left", padx=8)
        self.grid = tk.Frame(self.root, bg="#1b2430")
        self.grid.pack(fill="both", expand=True, padx=8, pady=4)
        self.cells = []
        for row in range(5):
            for col in range(6):
                cell = tk.Label(
                    self.grid,
                    text="",
                    width=12,
                    height=2,
                    bg="#243044",
                    fg="white",
                    font=("Microsoft YaHei UI", 8),
                    justify="center",
                    relief="flat",
                )
                cell.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
                self.cells.append(cell)
        for col in range(6):
            self.grid.columnconfigure(col, weight=1)
        self.load()
        self.root.mainloop()

    def _drag_start(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event) -> None:
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def prev_box(self) -> None:
        if self.page > 1:
            self.page -= 1
            self.load()

    def next_box(self) -> None:
        self.page += 1
        self.load()

    def reload(self) -> None:
        self.release_ids = release_serials()
        self.load()

    def load(self) -> None:
        try:
            data = fetch_json(f"/api/pets?sort=box&page={self.page}&pageSize=30&hide_world_team=false")
        except Exception as exc:
            self.summary.config(text=f"读取失败：{exc}")
            return
        if data.get("mode") != "box" or not data.get("box_count"):
            self.summary.config(text="还没有盒子位置")
            return
        self.page = int(data.get("page") or self.page)
        slots = data.get("data") or []
        release_count = 0
        for index, cell in enumerate(self.cells):
            pet = slots[index] if index < len(slots) else None
            if not pet:
                cell.config(text=f"{index + 1}\n空", bg="#2a3344", fg="#8ea0b5")
                continue
            name = pet.get("name") or pet.get("base_name") or "未知"
            level = pet.get("level") or "-"
            serial = int(pet.get("serial_num") or 0)
            marks = []
            bg = "#243044"
            if serial in self.release_ids and not pet.get("world_team"):
                marks.append("放生")
                bg = "#7a2e2e"
                release_count += 1
            if pet.get("world_team"):
                marks.append(f"队{pet['world_team']}")
                bg = "#0e6655"
            suffix = " ".join(marks)
            cell.config(text=f"{index + 1} {name}\nLv.{level} {suffix}", bg=bg, fg="white")
        self.summary.config(
            text=f"盒子 {data.get('box_id')} · 第 {self.page}/{data.get('box_count')} 盒 · 建议放生 {release_count}"
        )
        self.title.config(text=f"盒子 {data.get('box_id')}")


def main() -> None:
    start_page = 1
    if len(sys.argv) > 1:
        try:
            start_page = int(sys.argv[1])
        except ValueError:
            start_page = 1
    Overlay(start_page)


if __name__ == "__main__":
    main()
