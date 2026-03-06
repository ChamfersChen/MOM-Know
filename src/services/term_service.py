import os

from src.storage.postgres.models_terminology import Terminology, TerminologyInfo
from src.repositories.terminology_repository import TerminologyRepository
from src import config
from src.models.embed import OtherEmbedding



class TermService:
    def __init__(self):
        self.terminology_repository = TerminologyRepository()
        config_dict = config.embed_model_names['siliconflow/BAAI/local-bge-m3'].model_dump()
        config_dict["api_key"] = os.getenv(config_dict["api_key"]) or config_dict["api_key"]
        self.embedder = OtherEmbedding(
                model=config_dict.get("name"),
                base_url=config_dict.get("base_url"),
                api_key=config_dict.get("api_key"),
            )


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

    async def enable_terminology(self, id:int, enabled: bool) -> TerminologyInfo:
        term = await self.terminology_repository.enable_terminology(id, enabled)
        children = await self.terminology_repository.get_children_by_pid(id)
        for child in children:
            await self.enable_terminology(child.id, enabled)

        res = TerminologyInfo(**term.__dict__)
        
        for child in children:
            if child.pid is not None:
                res.other_words.append(child.word)
        return res



    async def create_terminology(self, terminology: TerminologyInfo) -> TerminologyInfo:
        word = terminology.word
        description = terminology.description
        specific_ds = terminology.specific_ds
        datasource_host = terminology.datasource_host
        datasource_port = terminology.datasource_port
        enabled = terminology.enabled
        embedding = await self.embedder.aencode(word) # TODO : 需要根据术语名称生成embedding
        term = await self.terminology_repository.create(
            {
                "word":word,
                "description":description,
                "embedding":embedding[0],
                "specific_ds":specific_ds,
                "datasource_host":datasource_host,
                "datasource_port":datasource_port,
                "enabled":enabled,
            }
        )

        pid = term.id
        other_words = terminology.other_words
        for other_word in other_words:
            embedding = await self.embedder.aencode(other_word) # TODO : 需要根据术语名称生成embedding
            term = await self.terminology_repository.create(
                {
                    "pid":pid,
                    "word":other_word,
                    "embedding":embedding[0],
                    "specific_ds":specific_ds,
                    "datasource_host":datasource_host,
                    "datasource_port":datasource_port,
                    "enabled":enabled,
                }
            )
        
        return terminology

    async def update_terminology(self, terminology: TerminologyInfo) -> TerminologyInfo:
        """更新术语

        Parameters
        ----------
        terminology : TerminologyInfo

        Returns
        -------
        list[TerminologyInfo]
        """
        id = terminology.id
        word = terminology.word
        description = terminology.description
        specific_ds = terminology.specific_ds
        datasource_host = terminology.datasource_host
        datasource_port = terminology.datasource_port
        enabled = terminology.enabled
        other_words = terminology.other_words
        embedding = await self.embedder.aencode(word) # TODO : 需要根据术语名称生成embedding
        term = await self.terminology_repository.update(
            {
                "id":id,
                "word":word,
                "description":description,
                "embedding":embedding[0],
                "specific_ds":specific_ds,
                "datasource_host":datasource_host,
                "datasource_port":datasource_port,
                "enabled":enabled,
            }
        )
        await self.terminology_repository.delete_by_pid(id)
        ret = TerminologyInfo(**term.__dict__)
        for other_word in other_words:
            embedding = await self.embedder.aencode(other_word) # TODO : 需要根据术语名称生成embedding
            term = await self.terminology_repository.create(
                {
                    "pid":id,
                    "word":other_word,
                    "embedding":embedding[0],
                    "specific_ds":specific_ds,
                    "datasource_host":datasource_host,
                    "datasource_port":datasource_port,
                    "enabled":enabled,
                }
            )
            ret.other_words.append(term.word)

        return ret


    async def get_terms_with_query(self, query: str) -> list[Terminology]:
        embedding = await self.embedder.aencode(query)
        return await self.terminology_repository.get_terms_with_embedding(embedding[0])


    async def delete_by_id(self, id: int) -> None:
        return await self.terminology_repository.delete(id)