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


    async def get_all_terminology(self) -> list[Terminology]:
        return await self.terminology_repository.get_all()


    async def create_terminology(self, terminology: TerminologyInfo) -> list[Terminology]:
        word = terminology.word
        description = terminology.description
        specific_ds = terminology.specific_ds
        datasource_host = terminology.datasource_host
        datasource_port = terminology.datasource_port
        enabled = terminology.enabled
        embedding = await self.embedder.aencode(word) # TODO : 需要根据术语名称生成embedding
        list_terms = []
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
        list_terms.append(term)

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
            list_terms.append(term)
        
        return list_terms


    async def get_terms_with_query(self, query: str) -> list[Terminology]:
        embedding = await self.embedder.aencode(query)
        return await self.terminology_repository.get_terms_with_embedding(embedding[0])


    async def delete_by_id(self, id: int) -> None:
        return await self.terminology_repository.delete(id)