"""基于 seekdb 的网站知识库：抽取 HTML、建立向量索引并提供语义检索。"""
import argparse
import os
import re
import threading
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote


COLLECTION_NAME = "site_pages"
_client = None
_collection = None
_lock = threading.RLock()


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.parts = []
        self._in_title = False
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer"):
            self._ignored += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer") and self._ignored:
            self._ignored -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title += (" " if self.title else "") + text
        elif not self._ignored:
            self.parts.append(text)


def _load_seekdb():
    try:
        import pyseekdb
        return pyseekdb
    except ImportError as exc:
        raise RuntimeError("尚未安装 pyseekdb，请执行：pip install -U pyseekdb") from exc


def _create_client(db_path):
    """有 SEEKDB_HOST 时连接服务端，否则使用 Linux 嵌入式模式。"""
    pyseekdb = _load_seekdb()
    host = os.environ.get("SEEKDB_HOST", "").strip()
    database = os.environ.get("SEEKDB_DATABASE", "hyper_site")
    if host:
        return pyseekdb.Client(
            host=host,
            port=int(os.environ.get("SEEKDB_PORT", "2881")),
            user=os.environ.get("SEEKDB_USER", "root"),
            password=os.environ.get("SEEKDB_PASSWORD", ""),
            database=database,
        )
    try:
        return pyseekdb.Client(path=str(db_path), database=database)
    except RuntimeError as exc:
        if "pylibseekdb" in str(exc):
            raise RuntimeError(
                "当前系统不支持 pyseekdb 嵌入式模式，请启动 seekdb Docker，"
                "并设置 SEEKDB_HOST、SEEKDB_PASSWORD 环境变量"
            ) from exc
        raise


def _get_collection(db_path):
    global _client, _collection
    with _lock:
        if _collection is None:
            _client = _create_client(db_path)
            _collection = _client.get_or_create_collection(COLLECTION_NAME)
        return _collection


def _chunks(text, size=700, overlap=100):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    result = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("。", start, end), text.rfind("！", start, end), text.rfind("？", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        result.append(text[start:end])
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return result


def _page_url(relative_path):
    parts = relative_path.as_posix().split("/")
    encoded = "/".join(quote(part) for part in parts)
    if encoded.endswith("/index.html"):
        encoded = encoded[:-10]
    return "/" + encoded


def build_index(site_root, db_path):
    """扫描网站 HTML 并重建 collection，返回页面数和文本块数。"""
    global _collection
    site_root = Path(site_root).resolve()
    candidates = [site_root / "home", site_root / "pages", site_root / "talk"]
    documents, ids, metadatas = [], [], []
    page_count = 0

    for base in candidates:
        if not base.exists():
            continue
        for html_file in sorted(base.rglob("*.html")):
            if html_file.name == "knowledge-search.html":
                continue
            try:
                parser = _TextExtractor()
                parser.feed(html_file.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            relative = html_file.relative_to(site_root)
            title = parser.title or html_file.stem
            chunks = _chunks(" ".join(parser.parts))
            if not chunks:
                continue
            page_count += 1
            for number, chunk in enumerate(chunks):
                ids.append(f"{relative.as_posix()}#{number}")
                documents.append(chunk)
                metadatas.append({"title": title, "url": _page_url(relative), "source": relative.as_posix()})

    client = _create_client(db_path)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(COLLECTION_NAME)
    batch_size = 100
    for start in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[start:start + batch_size],
            documents=documents[start:start + batch_size],
            metadatas=metadatas[start:start + batch_size],
        )
    if ids:
        collection.refresh_index()
    with _lock:
        _collection = collection
    return {"pages": page_count, "chunks": len(ids)}


def search(query, db_path, limit=5):
    query = str(query or "").strip()
    if not query:
        raise ValueError("请输入搜索内容")
    limit = max(1, min(int(limit), 10))
    with _lock:
        result = _get_collection(db_path).query(query_texts=[query], n_results=limit)

    def first(key):
        value = result.get(key, []) if isinstance(result, dict) else []
        return value[0] if value and isinstance(value[0], list) else value

    docs, metadata, distances, result_ids = first("documents"), first("metadatas"), first("distances"), first("ids")
    items = []
    for index, document in enumerate(docs or []):
        meta = metadata[index] if index < len(metadata or []) and metadata[index] else {}
        items.append({
            "id": result_ids[index] if index < len(result_ids or []) else "",
            "title": meta.get("title", "未命名页面"),
            "url": meta.get("url", "#"),
            "source": meta.get("source", ""),
            "content": document,
            "distance": distances[index] if index < len(distances or []) else None,
        })
    return items


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="建立网站 seekdb 知识库")
    parser.add_argument("--site-root", default=str(root))
    parser.add_argument("--db-path", default=str(root / "data" / "seekdb"))
    args = parser.parse_args()
    stats = build_index(args.site_root, args.db_path)
    print(f"知识库建立完成：{stats['pages']} 个页面，{stats['chunks']} 个文本块")
