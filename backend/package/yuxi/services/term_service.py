from yuxi.sql_database.vector_store import TermVectorStore
from yuxi.storage.postgres.models_terminology import Terminology, TerminologyInfo
from yuxi.repositories.terminology_repository import TerminologyRepository
from yuxi.utils import logger


class TermService:
    def __init__(self, vector_store: TermVectorStore | None = None):
        self.terminology_repository = TerminologyRepository()
        self.vector_store = vector_store

    async def get_all_terminology(self) -> dict[int, TerminologyInfo]:
        all_terms = await self.terminology_repository.get_all()
        res: dict[int, TerminologyInfo] = {}
        for term in all_terms:
            if term.pid is None:
                res[term.id] = TerminologyInfo(**term.__dict__)

        for term in all_terms:
            if term.pid is not None:
                res[term.pid].other_words.append(term.word)
        return res

    async def get_terminologies_by_host_port(self, host: str, port: int) -> dict[int, TerminologyInfo]:
        all_terms = await self.terminology_repository.get_by_host_port(host=host, port=port)
        res: dict[int, TerminologyInfo] = {}
        for term in all_terms:
            if term.pid is None:
                res[term.id] = TerminologyInfo(**term.__dict__)

        for term in all_terms:
            if term.pid is not None:
                res[term.pid].other_words.append(term.word)
        return res

    async def enable_terminology(self, id: int, enabled: bool) -> TerminologyInfo:
        term = await self.terminology_repository.enable_terminology(id, enabled)
        children = await self.terminology_repository.get_children_by_pid(id)
        for child in children:
            await self.enable_terminology(child.id, enabled)

        res = TerminologyInfo(**term.__dict__)

        for child in children:
            if child.pid is not None:
                res.other_words.append(child.word)

        if self.vector_store is not None:
            try:
                await self.vector_store.index_term(
                    term_id=term.id,
                    word=term.word,
                    description=term.description or "",
                    other_words=res.other_words,
                    specific_ds=term.specific_ds,
                    datasource_host=term.datasource_host,
                    datasource_port=term.datasource_port,
                    enabled=enabled,
                )
            except Exception as exc:
                logger.warning(f"Failed to sync term {term.id} enable status to Milvus: {exc}")

        return res

    async def create_terminology(self, terminology: TerminologyInfo) -> TerminologyInfo:
        word = terminology.word
        description = terminology.description
        specific_ds = terminology.specific_ds
        datasource_host = terminology.datasource_host
        datasource_port = terminology.datasource_port
        enabled = terminology.enabled
        create_time = terminology.create_time

        term = await self.terminology_repository.create(
            {
                "word": word,
                "description": description,
                "specific_ds": specific_ds,
                "datasource_host": datasource_host,
                "datasource_port": datasource_port,
                "enabled": enabled,
                "create_time": create_time,
            }
        )

        pid = term.id
        other_words = terminology.other_words
        for other_word in other_words:
            await self.terminology_repository.create(
                {
                    "pid": pid,
                    "word": other_word,
                    "specific_ds": specific_ds,
                    "datasource_host": datasource_host,
                    "datasource_port": datasource_port,
                    "enabled": enabled,
                    "create_time": create_time,
                }
            )

        if self.vector_store is not None:
            try:
                await self.vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize term vector store: {exc}")
            try:
                await self.vector_store.index_term(
                    term_id=term.id,
                    word=word,
                    description=description or "",
                    other_words=other_words,
                    specific_ds=specific_ds,
                    datasource_host=datasource_host,
                    datasource_port=datasource_port,
                    enabled=enabled,
                )
            except Exception as exc:
                logger.warning(f"Failed to index term {term.id} to Milvus: {exc}")

        return terminology

    async def update_terminology(self, terminology: TerminologyInfo) -> TerminologyInfo:
        id = terminology.id
        word = terminology.word
        description = terminology.description
        specific_ds = terminology.specific_ds
        datasource_host = terminology.datasource_host
        datasource_port = terminology.datasource_port
        enabled = terminology.enabled
        other_words = terminology.other_words
        term = await self.terminology_repository.update(
            {
                "id": id,
                "word": word,
                "description": description,
                "specific_ds": specific_ds,
                "datasource_host": datasource_host,
                "datasource_port": datasource_port,
                "enabled": enabled,
            }
        )
        await self.terminology_repository.delete_by_pid(id)
        ret = TerminologyInfo(**term.__dict__)
        for other_word in other_words:
            term = await self.terminology_repository.create(
                {
                    "pid": id,
                    "word": other_word,
                    "specific_ds": specific_ds,
                    "datasource_host": datasource_host,
                    "datasource_port": datasource_port,
                    "enabled": enabled,
                }
            )
            ret.other_words.append(term.word)

        if self.vector_store is not None:
            try:
                await self.vector_store.remove_term(id)
            except Exception as exc:
                logger.warning(f"Failed to remove old term {id} from Milvus: {exc}")
            try:
                await self.vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize term vector store: {exc}")
            try:
                await self.vector_store.index_term(
                    term_id=id,
                    word=word,
                    description=description or "",
                    other_words=other_words,
                    specific_ds=specific_ds,
                    datasource_host=datasource_host,
                    datasource_port=datasource_port,
                    enabled=enabled,
                )
            except Exception as exc:
                logger.warning(f"Failed to re-index term {id} to Milvus: {exc}")

        return ret

    async def get_terms_with_query(
        self, query: str, ds_host: str | None = None, ds_port: int | None = None
    ) -> list[dict]:
        if self.vector_store is not None:
            try:
                await self.vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize term vector store: {exc}")
            try:
                return await self.vector_store.search(
                    query=query,
                    top_k=10,
                    datasource_host=ds_host,
                    datasource_port=ds_port,
                )
            except Exception as exc:
                logger.warning(f"Failed to search terms from Milvus, falling back to pgvector: {exc}")

        from yuxi.models.embed import select_embedding_model
        from yuxi.config import config

        model = select_embedding_model(config.embed_model)
        embedding = await model.aencode([query])
        if ds_host and ds_port is not None:
            return await self.terminology_repository.get_terms_with_embedding(embedding[0], ds_host, ds_port)
        return []

    async def delete_by_id(self, id: int) -> None:
        await self.terminology_repository.delete(id)
        if self.vector_store is not None:
            try:
                await self.vector_store.remove_term(id)
            except Exception as exc:
                logger.warning(f"Failed to remove term {id} from Milvus: {exc}")
