from unittest.mock import AsyncMock, MagicMock, patch

from yuxi.sql_database.manager import SqlDataBaseManager


def _make_manager(vector_terms: list[dict] | None = None,
                  term_results: list[dict] | None = None,
                  sql_results: list[dict] | None = None,
                  host_ports: list[tuple[str, int]] | None = None) -> SqlDataBaseManager:
    """创建一个 SqlDataBaseManager 实例，所有外部依赖均为 AsyncMock。"""
    manager = object.__new__(SqlDataBaseManager)
    manager.vector_store = AsyncMock()
    manager.term_vector_store = AsyncMock()
    manager.sql_example_vector_store = AsyncMock()
    manager.graph_service = None
    manager.active_db_ids = None

    manager.vector_store.search = AsyncMock(return_value=vector_terms or [])
    manager.term_vector_store.search = AsyncMock(return_value=term_results or [])
    manager.term_vector_store.initialize_collection = AsyncMock()
    manager.sql_example_vector_store.search = AsyncMock(return_value=sql_results or [])
    manager.sql_example_vector_store.initialize_collection = AsyncMock()

    manager._resolve_unique_host_ports = AsyncMock(return_value=host_ports or [])

    return manager


FakeTable = {"table_id": "1", "db_id": "db1", "db_name": "test_db",
             "table_name": "users", "is_choose": True,
             "content": "user table", "score": 0.9}
FakeTerm = {"id": "10", "word": "客户", "description": "customer",
            "other_words": ["client"], "score": 0.85}
FakeSql = {"id": "20", "sql": "SELECT * FROM users",
           "description": "query all users", "score": 0.8}


class TestSearchTables:
    """SqlDataBaseManager.search_tables 单元测试。"""

    async def test_search_tables_basic(self):
        manager = _make_manager(vector_terms=[FakeTable])
        result = await manager.search_tables("test query")

        assert "tables" in result
        assert "terms" in result
        assert "sqls" in result
        assert len(result["tables"]) == 1
        assert result["tables"][0]["table_id"] == "1"
        # search_terms=False 时不应搜索 term/sql 存储
        manager.term_vector_store.search.assert_not_called()
        manager.sql_example_vector_store.search.assert_not_called()

    async def test_search_tables_with_terms(self):
        manager = _make_manager(vector_terms=[FakeTable], term_results=[FakeTerm],
                                host_ports=[("192.168.1.1", 3306)])
        result = await manager.search_tables("test query", search_terms=True)

        assert len(result["tables"]) == 1
        assert len(result["terms"]) == 1
        assert len(result["sqls"]) == 0
        assert result["terms"][0]["word"] == "客户"
        # 应使用 host_ports 过滤
        manager.term_vector_store.search.assert_called_once_with(
            query="test query", datasource_host="192.168.1.1", datasource_port=3306,
        )

    async def test_search_tables_with_terms_and_sqls(self):
        manager = _make_manager(vector_terms=[FakeTable], term_results=[FakeTerm],
                                sql_results=[FakeSql], host_ports=[("192.168.1.1", 3306)])
        result = await manager.search_tables("test query", search_terms=True, search_sqls=True)

        assert len(result["tables"]) == 1
        assert len(result["terms"]) == 1
        assert len(result["sqls"]) == 1
        assert result["sqls"][0]["sql"] == "SELECT * FROM users"

    async def test_search_tables_no_db_ids_searches_all_terms(self):
        """db_ids=None 且 host_ports 为空时，terms/sqls 应全局搜索（不传 host/port）。"""
        manager = _make_manager(vector_terms=[FakeTable], term_results=[FakeTerm],
                                host_ports=[])
        result = await manager.search_tables("test query", search_terms=True)

        assert len(result["terms"]) == 1
        manager.term_vector_store.search.assert_called_once_with(query="test query")

    async def test_search_tables_uses_active_db_ids(self):
        """当 db_ids=None 但 active_db_ids 有值时，应自动使用 active_db_ids。"""
        manager = _make_manager(vector_terms=[FakeTable], term_results=[FakeTerm],
                                host_ports=[("10.0.0.1", 5432)])
        manager.active_db_ids = ["db1", "db2"]

        result = await manager.search_tables("test query", search_terms=True)

        assert len(result["tables"]) == 1
        assert len(result["terms"]) == 1
        # 确认 vector_store.search 被传入 active_db_ids
        manager.vector_store.search.assert_called_once()
        call_kwargs = manager.vector_store.search.call_args[1]
        assert call_kwargs["db_ids"] == ["db1", "db2"]
        # 确认 host/port 解析也使用了 active_db_ids
        manager._resolve_unique_host_ports.assert_called_once_with(["db1", "db2"])

    async def test_search_tables_explicit_db_ids_overrides_active(self):
        """显式传入 db_ids 应覆盖 active_db_ids。"""
        manager = _make_manager(vector_terms=[FakeTable], host_ports=[])
        manager.active_db_ids = ["default_db"]

        result = await manager.search_tables("test query", db_ids=["explicit_db"])

        assert len(result["tables"]) == 1
        call_kwargs = manager.vector_store.search.call_args[1]
        assert call_kwargs["db_ids"] == ["explicit_db"]

    async def test_search_tables_no_vector_store(self):
        """vector_store 为 None 时返回空结果，不抛异常。"""
        manager = object.__new__(SqlDataBaseManager)
        manager.vector_store = None
        manager.term_vector_store = None
        manager.sql_example_vector_store = None
        manager.graph_service = None
        manager.active_db_ids = None

        result = await manager.search_tables("test query")
        assert result == {"tables": [], "terms": [], "sqls": []}

    async def test_search_tables_term_search_failure_is_graceful(self):
        """term_vector_store.search 失败时不应中断，terms 保持空列表。"""
        manager = _make_manager(vector_terms=[FakeTable], host_ports=[("h", 1)])
        manager.term_vector_store.search = AsyncMock(side_effect=Exception("milvus down"))
        manager.term_vector_store.initialize_collection = AsyncMock()

        result = await manager.search_tables("test query", search_terms=True)

        assert len(result["tables"]) == 1
        assert result["terms"] == []

    async def test_search_tables_top_k_limits_tables(self):
        """top_k 应正确截断 tables 列表。"""
        manager = _make_manager(vector_terms=[FakeTable, {**FakeTable, "table_id": "2", "score": 0.8}])
        result = await manager.search_tables("test query", top_k=1)

        assert len(result["tables"]) == 1

    async def test_set_active_db_ids(self):
        """set_active_db_ids 应正确保存/清空。"""
        manager = object.__new__(SqlDataBaseManager)
        manager.set_active_db_ids(["db_a", "db_b"])
        assert manager.active_db_ids == ["db_a", "db_b"]

        manager.set_active_db_ids(None)
        assert manager.active_db_ids is None

    async def test_resolve_unique_host_ports(self):
        """_resolve_unique_host_ports 应去重并返回唯一的 (host, port) 对。"""
        manager = object.__new__(SqlDataBaseManager)
        fake_db_1 = MagicMock(connect_info={"host": "10.0.0.1", "port": 3306})
        fake_db_2 = MagicMock(connect_info={"host": "10.0.0.2", "port": 3306})
        fake_db_dup = MagicMock(connect_info={"host": "10.0.0.1", "port": 3306})

        with patch("yuxi.repositories.sql_database_repository.SqlDatabaseRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_by_id = AsyncMock(side_effect=[fake_db_1, fake_db_2, fake_db_dup])
            pairs = await manager._resolve_unique_host_ports(["id1", "id2", "id3"])

        assert len(pairs) == 2
        assert ("10.0.0.1", 3306) in pairs
        assert ("10.0.0.2", 3306) in pairs
