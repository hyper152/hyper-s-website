# -*- coding: utf-8 -*-
"""
访问计数模块（异步保存 + 防重复计数）
"""
import json
import os
import time
import threading
from datetime import datetime

class VisitCounter:
    def __init__(self, save_file: str):
        self.save_file = save_file
        self.count = 0
        self.lock = threading.Lock()
        self.save_interval = 30  # 30秒自动保存一次
        self.last_save_time = time.time()
        self._load_count()
        # 启动异步保存线程
        self._start_async_save()

    def _load_count(self):
        """从文件加载计数"""
        try:
            if os.path.exists(self.save_file):
                with open(self.save_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.count = data.get("total_visits", 0)
        except Exception as e:
            print(f"加载访问计数失败：{e}")
            self.count = 0

    def _save_count(self, force: bool = False):
        """保存计数到文件（加锁）"""
        with self.lock:
            now = time.time()
            if not force and (now - self.last_save_time) < self.save_interval:
                return
            try:
                dir_name = os.path.dirname(self.save_file)
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name)
                with open(self.save_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "total_visits": self.count,
                        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }, f, ensure_ascii=False, indent=4)
                self.last_save_time = now
            except Exception as e:
                print(f"保存访问计数失败：{e}")

    def _async_save_count(self, force: bool = False):
        """异步保存（避免阻塞主线程）"""
        threading.Thread(target=self._save_count, args=(force,), daemon=True).start()

    def _start_async_save(self):
        """启动定时保存线程"""
        def auto_save():
            while True:
                time.sleep(self.save_interval)
                self._async_save_count()
        threading.Thread(target=auto_save, daemon=True).start()

    def count_visit(self) -> int:
        """计数+1并返回最新值"""
        with self.lock:
            self.count += 1
            # 触发异步保存（非强制）
            self._async_save_count()
            return self.count

    def get_total_visits(self) -> int:
        """获取当前总访问量"""
        with self.lock:
            return self.count

    def reset_visits(self):
        """重置计数为0"""
        with self.lock:
            self.count = 0
            self._async_save_count(force=True)

# 全局计数器实例
global_counter = None

def init_visit_counter(save_file: str):
    """初始化全局计数器"""
    global global_counter
    if global_counter is None:
        global_counter = VisitCounter(save_file)

def count_visit() -> int:
    """计数+1（全局调用）"""
    if global_counter:
        return global_counter.count_visit()
    return 0

def get_total_visits() -> int:
    """获取总访问量（全局调用）"""
    if global_counter:
        return global_counter.get_total_visits()
    return 0

def reset_visits():
    """重置计数（全局调用）"""
    if global_counter:
        global_counter.reset_visits()