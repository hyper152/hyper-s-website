"""兼容旧访问计数 API，统一使用 SQLite 原子计数。"""
from src.storage import get_store


class VisitCounter:
    def __init__(self, save_file=None):
        self.save_file = save_file  # 兼容参数，不再读写旧 JSON

    def count_visit(self):
        return get_store().counter(increment=True)

    def get_total_visits(self):
        return get_store().counter()

    def reset_visits(self):
        get_store().counter(reset=True)


global_counter = None


def init_visit_counter(save_file=None):
    global global_counter
    if global_counter is None:
        global_counter = VisitCounter(save_file)


def count_visit():
    return get_store().counter(increment=True)


def get_total_visits():
    return get_store().counter()


def reset_visits():
    get_store().counter(reset=True)
