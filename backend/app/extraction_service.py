"""The resume-to-profile use case: build blocks, cut chunks, store, draft.

Three endpoints serve this same sequence and differ only in where the material
came from: pasted text, an uploaded PDF/DOCX, or several inputs bundled
together. Keeping the sequence here leaves a route with the parts that are
genuinely HTTP - reading the body, picking a parser from the filename, turning
a failure into a status code - and gives the flow one place to change.

``extract_profile_from_chunks`` is used rather than ``extract_profile_from_blocks``
on purpose: the chunks are built here because they have to be stored before the
model is called, and the stored ids must be the ids the model was shown. That is
the only reason a citation in the draft can still be resolved to the paragraph
it came from once the response is gone.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from .chunking import (
    Block,
    Chunk,
    blocks_from_mapping,
    blocks_from_text,
    chunk_blocks,
    merge_blocks,
)
from .extractor import ExtractionResult, extract_profile_from_chunks
from .llm import LLMClient
from .schemas import (
    ResumeExtractionRequest,
    ResumeExtractionResponse,
    ResumeSourceBundleRequest,
)
from .schemas_resources import ResumeCreate
from .services import create_resume


class ResumeExtractionService:
    """Draft a profile from one batch of resume material.

    The caller resolves the model client and passes it in: a missing API key
    is a deployment problem the route reports as 503, not something that should
    reach the extractor and come back as a degraded draft.
    """

    def __init__(self, session: Session, client: LLMClient) -> None:
        self._session = session
        self._client = client

    def from_text(self, data: ResumeExtractionRequest) -> ResumeExtractionResponse:
        """Draft from pasted resume text."""

        return self._run(
            [blocks_from_text(data.text)],
            user_id=data.user_id,
            source_type="text",
            source_name="pasted-resume",
            max_chunk_tokens=data.max_chunk_tokens,
        )

    def from_bundle(
        self, data: ResumeSourceBundleRequest
    ) -> ResumeExtractionResponse:
        """Draft from resume text, a self description and project entries.

        Each source is parsed into its own group, so a citation still names
        where it came from and the difference between "I interned there" and
        "my project used that" survives into the draft.
        """

        groups: list[Sequence[Block]] = []
        if data.resume_text and data.resume_text.strip():
            groups.append(blocks_from_text(data.resume_text, source="resume"))
        if data.self_description and data.self_description.strip():
            groups.append(
                blocks_from_text(data.self_description, source="self_description")
            )
        if data.projects:
            # A list of project entries is wrapped so each one keeps its own
            # block instead of being flattened into a single string.
            payload = (
                {"projects": data.projects}
                if isinstance(data.projects, list)
                else data.projects
            )
            groups.append(blocks_from_mapping(payload, source="project"))

        return self._run(
            groups,
            user_id=data.user_id,
            source_type="text",
            source_name="bundle",
            max_chunk_tokens=data.max_chunk_tokens,
        )

    def from_blocks(
        self,
        blocks: Sequence[Block],
        *,
        user_id: str | None,
        source_type: str,
        source_name: str,
        max_chunk_tokens: int = 900,
    ) -> ResumeExtractionResponse:
        """Draft from blocks a file parser already produced.

        PDF and DOCX parsers do layout work that ``blocks_from_text`` cannot,
        so their blocks must enter the pipeline directly instead of being
        flattened back into a string and re-split.
        """

        return self._run(
            [blocks],
            user_id=user_id,
            source_type=source_type,
            source_name=source_name,
            max_chunk_tokens=max_chunk_tokens,
        )

    def _run(
        self,
        groups: Sequence[Sequence[Block]],
        *,
        user_id: str | None,
        source_type: str,
        source_name: str,
        max_chunk_tokens: int,
    ) -> ResumeExtractionResponse:
        chunks = chunk_blocks(merge_blocks(*groups), max_tokens=max_chunk_tokens)
        resume_id = self._store_chunks(
            chunks,
            user_id=user_id,
            source_type=source_type,
            source_name=source_name,
        )
        result = extract_profile_from_chunks(chunks, self._client)
        return _response(result, resume_id)

    def _store_chunks(
        self,
        chunks: Sequence[Chunk],
        *,
        user_id: str | None,
        source_type: str,
        source_name: str,
    ) -> str | None:
        """Store the parsed chunks when the caller identifies a user.

        A chunk id means nothing once the response is gone, so this record is
        what lets a confirmed profile point back at the paragraph a claim came
        from. Without ``user_id`` the flow stays stateless, which is what the
        demo relies on before a user exists.
        """

        if not user_id:
            return None

        payload = ResumeCreate(
            user_id=user_id,
            source_type=source_type,
            source_name=source_name,
            content={
                "chunks": [
                    {
                        "id": chunk.chunk_id,
                        "source": chunk.source,
                        "section": chunk.section,
                        "text": chunk.text,
                        "tokens": chunk.tokens,
                    }
                    for chunk in chunks
                ],
                "chunk_count": len(chunks),
            },
        )
        return create_resume(self._session, payload).id


def _response(
    result: ExtractionResult, resume_id: str | None
) -> ResumeExtractionResponse:
    return ResumeExtractionResponse(
        profile=result.profile,
        recommended_roles=result.recommended_roles,
        missing_information=result.missing_information,
        evidence=result.evidence,
        unresolved_evidence=result.unresolved,
        chunk_ids=result.chunk_ids,
        degraded=result.degraded,
        resume_id=resume_id,
        notes=result.notes,
    )
