"""Tests for OpenAlex service utility methods."""
import pytest
from services.openalex_service import OpenAlexService
from models.openalex_models import Work


class TestReconstructAbstract:
    def test_basic_reconstruction(self) -> None:
        inverted: dict[str, list[int]] = {'Hello': [0], 'world': [1]}
        assert OpenAlexService.reconstruct_abstract(inverted) == 'Hello world'

    def test_out_of_order_positions(self) -> None:
        inverted: dict[str, list[int]] = {'world': [1], 'Hello': [0]}
        assert OpenAlexService.reconstruct_abstract(inverted) == 'Hello world'

    def test_repeated_word(self) -> None:
        inverted: dict[str, list[int]] = {'is': [1, 3], 'this': [0], 'a': [2], 'test': [4]}
        assert OpenAlexService.reconstruct_abstract(inverted) == 'this is a is test'


class TestExtractIds:
    def test_extract_openalex_id_from_url(self) -> None:
        work = Work(id='https://openalex.org/W2741809807')
        assert OpenAlexService.extract_openalex_id(work) == 'W2741809807'

    def test_extract_openalex_id_plain(self) -> None:
        work = Work(id='W12345')
        assert OpenAlexService.extract_openalex_id(work) == 'W12345'

    def test_extract_openalex_id_none(self) -> None:
        assert OpenAlexService.extract_openalex_id(Work()) is None

    def test_extract_doi_from_url(self) -> None:
        work = Work(doi='https://doi.org/10.1038/test')
        assert OpenAlexService.extract_doi(work) == '10.1038/test'

    def test_extract_doi_plain(self) -> None:
        work = Work(doi='10.1038/test')
        assert OpenAlexService.extract_doi(work) == '10.1038/test'

    def test_extract_doi_none(self) -> None:
        assert OpenAlexService.extract_doi(Work()) is None


class TestBatchValidation:
    @pytest.mark.asyncio
    async def test_batch_empty_list_raises(self) -> None:
        service = OpenAlexService()
        with pytest.raises(ValueError, match='empty'):
            await service.batch_get_works([])
        await service.close()

    @pytest.mark.asyncio
    async def test_batch_over_100_raises(self) -> None:
        service = OpenAlexService()
        with pytest.raises(ValueError, match='100'):
            await service.batch_get_works(['doi'] * 101)
        await service.close()
