from __future__ import annotations

from typing import Any

from yuxi.storage.neo4j import (
    get_shared_neo4j_connection,
    neo4j_read,
    neo4j_write,
)
from yuxi.utils import logger

NS_LABEL = "SqlDB"


class SqlDBGraphService:
    """SQL 数据库的 Neo4j 图谱服务。

    维护 Database / Table 节点以及 HAS_TABLE / DEPENDS_ON 关系。
    所有节点挂 SqlDB 标签作为命名空间。
    """

    def __init__(self):
        self._driver = None

    def ensure_driver(self):
        if self._driver is None:
            conn = get_shared_neo4j_connection()
            self._driver = conn.driver
        return self._driver

    def sync_graph(
        self,
        db_id: str,
        db_name: str,
        description: str,
        tables: list[dict[str, Any]],
    ):
        """创建或更新 Database 节点及其 Table 子节点。"""
        driver = self.ensure_driver()
        if driver is None:
            logger.warning("Neo4j not available, skipping graph sync")
            return

        def _write(tx):
            tx.run(
                f"""\
MERGE (d:{NS_LABEL}:Database {{db_id: $db_id}})
SET d.db_name = $db_name, d.description = $description
""",
                db_id=db_id,
                db_name=db_name,
                description=description,
            )
            for t in tables:
                tid = t["table_id"]
                tname = t.get("tablename") or ""
                tdesc = t.get("description") or t.get("total_description") or ""
                tx.run(
                    f"""\
MERGE (t:{NS_LABEL}:Table {{table_id: $table_id}})
SET t.table_name = $table_name, t.description = $description, t.db_id = $db_id
""",
                    table_id=tid,
                    table_name=tname,
                    description=tdesc,
                    db_id=db_id,
                )
                tx.run(
                    f"""\
MATCH (d:{NS_LABEL}:Database {{db_id: $db_id}})
MATCH (t:{NS_LABEL}:Table {{table_id: $table_id}})
MERGE (d)-[:HAS_TABLE]->(t)
""",
                    db_id=db_id,
                    table_id=tid,
                )

        neo4j_write(driver, _write)
        logger.info(f"Synced graph for database {db_id} with {len(tables)} tables")

    def sync_dependencies(self, db_id: str, related_db_ids: list[str]):
        """创建双向 DEPENDS_ON 关系。"""
        if not related_db_ids:
            return
        driver = self.ensure_driver()
        if driver is None:
            return

        def _write(tx):
            for rid in related_db_ids:
                tx.run(
                    f"""\
MATCH (d1:{NS_LABEL}:Database {{db_id: $db_id}})
MATCH (d2:{NS_LABEL}:Database {{db_id: $related_id}})
MERGE (d1)-[:DEPENDS_ON]->(d2)
MERGE (d2)-[:DEPENDS_ON]->(d1)
""",
                    db_id=db_id,
                    related_id=rid,
                )

        neo4j_write(driver, _write)
        logger.info(f"Synced DEPENDS_ON for {db_id} -> {related_db_ids}")

    def remove_graph(self, db_id: str):
        """删除指定数据库的所有图节点。"""
        driver = self.ensure_driver()
        if driver is None:
            return

        def _write(tx):
            tx.run(
                f"""\
MATCH (t:{NS_LABEL}:Table {{db_id: $db_id}})
DETACH DELETE t
""",
                db_id=db_id,
            )
            tx.run(
                f"""\
MATCH (d:{NS_LABEL}:Database {{db_id: $db_id}})
DETACH DELETE d
""",
                db_id=db_id,
            )

        neo4j_write(driver, _write)
        logger.info(f"Removed graph for database {db_id}")

    def clear_all(self):
        """删除所有 SqlDB 标签的节点和关系。"""
        driver = self.ensure_driver()
        if driver is None:
            return

        def _write(tx):
            tx.run(f"MATCH (n:{NS_LABEL}) DETACH DELETE n")

        neo4j_write(driver, _write)
        logger.info("Cleared all SqlDB graph nodes")

    def remove_dependency(self, db_id: str):
        """删除指定数据库的双向 DEPENDS_ON 关系。"""
        driver = self.ensure_driver()
        if driver is None:
            return

        def _write(tx):
            tx.run(
                f"""\
MATCH (d:{NS_LABEL}:Database {{db_id: $db_id}})-[r:DEPENDS_ON]-(:{NS_LABEL}:Database)
DELETE r
""",
                db_id=db_id,
            )

        neo4j_write(driver, _write)
        logger.info(f"Removed DEPENDS_ON for {db_id}")

    def query_tables(self, db_ids: list[str]) -> list[dict[str, Any]]:
        """通过图遍历获取指定数据库的表列表。"""
        driver = self.ensure_driver()
        if driver is None:
            return []
        expr = " or ".join(f'd.db_id = "{d}"' for d in db_ids)
        return neo4j_read(
            driver,
            f"""\
MATCH (d:{NS_LABEL}:Database)-[:HAS_TABLE]->(t:{NS_LABEL}:Table)
WHERE {expr}
RETURN t.table_id AS table_id, t.table_name AS table_name,
       t.description AS description, t.db_id AS db_id
""",
        )

    def fetch_tables_by_db_cluster(self, db_ids: list[str]) -> list[dict[str, Any]]:
        """以带权重的数据库为种子，扩散到 DEPENDS_ON 关联库，返回所有表。"""
        driver = self.ensure_driver()
        if driver is None:
            return []
        expr = " or ".join(f'source.db_id = "{d}"' for d in db_ids)
        return neo4j_read(
            driver,
            f"""\
MATCH (source:{NS_LABEL}:Database)
WHERE {expr}
OPTIONAL MATCH (source)-[:DEPENDS_ON]-(related:{NS_LABEL}:Database)
WITH source, COLLECT(DISTINCT related) AS related_dbs
WITH [source] + related_dbs AS all_dbs
UNWIND all_dbs AS target_db
MATCH (target_db)-[:HAS_TABLE]->(t:{NS_LABEL}:Table)
RETURN DISTINCT t.table_id AS table_id,
       t.table_name AS table_name,
       t.description AS description,
       t.db_id AS db_id,
       target_db.db_name AS db_name
""",
        )

    def query_related_dbs(self, db_id: str) -> dict[str, list[dict[str, Any]]]:
        """查询指定数据库的上下游依赖。"""
        driver = self.ensure_driver()
        if driver is None:
            return {"depends_on": [], "depended_by": []}
        depends_on = neo4j_read(
            driver,
            f"""\
MATCH (d:{NS_LABEL}:Database {{db_id: $db_id}})-[:DEPENDS_ON]->(related:{NS_LABEL}:Database)
RETURN related.db_id AS db_id, related.db_name AS db_name
""",
            db_id=db_id,
        )
        depended_by = neo4j_read(
            driver,
            f"""\
MATCH (d:{NS_LABEL}:Database {{db_id: $db_id}})<-[:DEPENDS_ON]-(dependent:{NS_LABEL}:Database)
RETURN dependent.db_id AS db_id, dependent.db_name AS db_name
""",
            db_id=db_id,
        )
        return {"depends_on": depends_on, "depended_by": depended_by}
