class PaperRetrievalService:
    \"\"\"
    Atomic retrieval service. Fetches metadata, references, citations, authors, and venues
    in a single shot and stores them immediately in Neo4j.
    \"\"\"
    def __init__(self):
        pass

    async def retrieve_paper(self, doi: str):
        \"\"\"
        Fetches full paper details from OpenAlex, embeds it, and stores it in Neo4j.
        Saves local backup to papers2/ folder.
        \"\"\"
        pass
        
    async def bulk_retrieve(self, dois: list[str]):
        \"\"\"
        Batch retrieval of multiple DOIs.
        \"\"\"
        pass
