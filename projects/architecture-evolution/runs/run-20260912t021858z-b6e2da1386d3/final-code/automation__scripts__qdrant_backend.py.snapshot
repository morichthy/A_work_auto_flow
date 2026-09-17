"""工作区内 Qdrant local 持久化后端与离线 FastEmbed 编码。

不启动服务器或访问网络。SQLite 管理原文/状态，Qdrant 管理可重建片段向量；
两者通过 source_id + digest + 字符范围对齐，返回时必须再核对当前原件状态。
"""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
import uuid
from importlib.metadata import version


def enabled(cfg):
    return cfg.get("vector_store", {}).get("provider") == "qdrant-local"


@lru_cache(maxsize=2)
def verify_model(model_dir, files):
    """每个进程首次装载校验实际文件，防止损坏/替换模型沿用旧集合身份。"""
    base = Path(model_dir).resolve()
    for relative, expected in files:
        path = (base / relative).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError(f"模型文件缺失或越界：{relative}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError(f"模型校验失败：{relative}；请从已保存副本恢复或重新下载并建立新清单")


@lru_cache(maxsize=2)
def encoder(model_dir, model_name):
    # 安装阶段下载，运行阶段强制离线；没有完整文件则报错而不是自动外连。
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from fastembed import TextEmbedding
    from tokenizers import Tokenizer
    path = Path(model_dir)
    if not (path / "model_optimized.onnx").is_file():
        raise ValueError("本地嵌入模型缺失；运行 services/qdrant/download_model.py 安装")
    tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
    tokenizer.no_truncation()
    model = TextEmbedding(model_name=model_name, specific_model_path=str(path),
                          local_files_only=True, threads=2, providers=["CPUExecutionProvider"])
    return model, tokenizer


class LocalBackend:
    def __init__(self, root, cfg, *, collection_prefix="workspace", encoding_version="passage-query-window-v1", expected_dimensions=None):
        from qdrant_client import QdrantClient, models
        self.models = models
        self.cfg = cfg
        self.root = root
        setting = cfg["embedding"]
        model_dir = (root / setting["path"]).resolve()
        manifest_path = (root / setting.get("manifest", "services/qdrant/model-manifest.json")).resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("model") != setting["model"] or not manifest.get("files"):
            raise ValueError("嵌入配置与模型清单不一致或缺少文件校验信息")
        # 新的记忆表示复用同一离线编码器，但不能与旧全文片段混用集合。
        # 默认参数保持历史身份不变；调用方显式指定 schema/编码版本前缀。
        if expected_dimensions is not None and manifest.get("dimensions") != expected_dimensions:
            raise ValueError(f"嵌入维度不兼容：当前入口要求 {expected_dimensions} 维")
        if not collection_prefix or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in collection_prefix):
            raise ValueError("向量集合前缀必须为小写字母、数字或下划线")
        verify_model(str(model_dir), tuple(sorted(manifest["files"].items())))
        # 编码库升级可能改变池化或归一化；不能在同一集合混用不兼容向量。
        identity = hashlib.sha256(json.dumps({"model": manifest, "fastembed": version("fastembed"),
            "encoding": encoding_version}, sort_keys=True).encode()).hexdigest()[:12]
        self.collection = collection_prefix + "_" + identity
        self.model, self.tokenizer = encoder(str(model_dir), setting["model"])
        storage = (root / cfg["vector_store"].get("path", "services/qdrant/storage")).resolve()
        if not storage.is_relative_to(root.resolve()):
            raise ValueError("Qdrant 数据库必须留在工作区")
        storage.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(storage))
        try:
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(self.collection, vectors_config=models.VectorParams(
                    size=manifest["dimensions"], distance=models.Distance.COSINE))
        except Exception:
            self.client.close()
            raise

    def close(self):
        self.client.close()

    def points_for(self, doc, chunks):
        """按真实 tokenizer 再分窗，防止长中文片段被模型静默截掉后半部。

每窗不超过 360 正文 token，给标题留余量；原文字符偏移仍能展开到页/整份材料。
        """
        from qdrant_client.models import PointStruct
        texts, payloads, ids = [], [], []
        meta = json.loads(doc["meta"])
        for chunk in chunks:
            encoding = self.tokenizer.encode(chunk["body"], add_special_tokens=False)
            offsets = encoding.offsets
            for offset in range(0, len(offsets), 300):
                selected = offsets[offset:offset+360]
                if not selected:
                    continue
                start, end = selected[0][0], selected[-1][1]
                payload = {"source_id": doc["id"], "digest": doc["digest"], "project": meta.get("project", ""),
                           "model_id": self.collection, "chunk_id": chunk["id"],
                           "module_ids": meta.get("module_ids", []), "locator": chunk["locator"],
                           "start": chunk["start"]+start, "end": chunk["start"]+end}
                identity = f"{self.collection}:{doc['id']}:{doc['digest']}:{payload['start']}:{payload['end']}"
                ids.append(str(uuid.uuid5(uuid.NAMESPACE_URL, identity)))
                payloads.append(payload)
                # 标题也限制 token 数，而不是按字符粗估。
                title = self.tokenizer.encode(meta.get("title", "") + " " + " ".join(meta.get("keywords", [])), add_special_tokens=False)
                prefix = self.tokenizer.decode(title.ids[:40])
                texts.append(prefix + "\n" + chunk["body"][start:end])
        vectors = list(self.model.passage_embed(texts, batch_size=16)) if texts else []
        return [PointStruct(id=i, vector=v.tolist(), payload=p) for i, v, p in zip(ids, vectors, payloads)]

    def sync(self, db):
        from qdrant_client import models
        db.execute("CREATE TABLE IF NOT EXISTS qdrant_sync (collection TEXT, source TEXT, signature TEXT, PRIMARY KEY(collection,source))")
        docs = db.execute("SELECT * FROM docs WHERE state='ready'").fetchall()
        active = {d["id"] for d in docs}
        changed, unchanged = 0, 0
        for doc in docs:
            signature = hashlib.sha256((doc["digest"]+doc["meta"]+"window-v1").encode()).hexdigest()
            old = db.execute("SELECT signature FROM qdrant_sync WHERE collection=? AND source=?", (self.collection, doc["id"])).fetchone()
            if old and old[0] == signature:
                # 库被独立清理时可自修复：不能只依赖 SQLite 的成功标记。
                count = self.client.count(self.collection, count_filter=models.Filter(must=[models.FieldCondition(
                    key="source_id", match=models.MatchValue(value=doc["id"]))]), exact=True).count
                if count:
                    unchanged += 1
                    continue
            chunks = db.execute("SELECT * FROM chunks WHERE source_id=? ORDER BY start", (doc["id"],)).fetchall()
            points = self.points_for(doc, chunks)
            self.client.delete(self.collection, points_selector=models.FilterSelector(filter=models.Filter(
                must=[models.FieldCondition(key="source_id", match=models.MatchValue(value=doc["id"]))])), wait=True)
            for offset in range(0, len(points), 64):
                self.client.upsert(self.collection, points[offset:offset+64], wait=True)
            db.execute("INSERT OR REPLACE INTO qdrant_sync VALUES(?,?,?)", (self.collection, doc["id"], signature))
            changed += 1
        removed = 0
        for row in db.execute("SELECT source FROM qdrant_sync WHERE collection=?", (self.collection,)).fetchall():
            if row[0] not in active:
                self.client.delete(self.collection, points_selector=models.FilterSelector(filter=models.Filter(
                    must=[models.FieldCondition(key="source_id", match=models.MatchValue(value=row[0]))])), wait=True)
                db.execute("DELETE FROM qdrant_sync WHERE collection=? AND source=?", (self.collection, row[0]))
                removed += 1
        db.commit()
        return {"updated_sources": changed, "unchanged_sources": unchanged, "removed_sources": removed,
                "collection": self.collection, "points": self.client.count(self.collection, exact=True).count}

    def search(self, query, limit, project=None, module=None):
        from qdrant_client import models
        filters = []
        if project:
            filters.append(models.FieldCondition(key="project", match=models.MatchValue(value=project)))
        if module:
            filters.append(models.FieldCondition(key="module_ids", match=models.MatchValue(value=module)))
        vector = next(self.model.query_embed(query)).tolist()
        return self.client.query_points(self.collection, query=vector, limit=limit,
                                        query_filter=models.Filter(must=filters) if filters else None,
                                        with_payload=True).points


def sync(root, db, cfg):
    if not enabled(cfg):
        return {"enabled": False}
    backend = LocalBackend(root, cfg)
    try:
        return {"enabled": True, **backend.sync(db)}
    finally:
        backend.close()
