from __future__ import annotations

from .features.relationship.bond import CharacterBondService
from .features.relationship.state import CharacterStateService
from .storage import Storage
from .features.novel.canvas import NovelCanvasMixin
from .features.novel.canvas_access import NovelCanvasAccessMixin
from .features.novel.canvas_defaults import NovelCanvasDefaultMixin
from .features.novel.canvas_parsing import NovelCanvasParsingMixin
from .features.novel.canvas_planning import NovelCanvasPlanningMixin
from .features.novel.canvas_prompting import NovelCanvasPromptMixin
from .features.novel.canvas_sync import NovelCanvasSyncMixin
from .features.novel.audit import NovelAuditMixin
from .features.novel.generation import NovelGenerationMixin
from .features.novel.generation_beats import NovelGenerationBeatsMixin
from .features.novel.generation_context import NovelGenerationContextMixin
from .features.novel.generation_mock import NovelGenerationMockMixin
from .features.novel.generation_postprocess import NovelGenerationPostprocessMixin
from .features.novel.generation_response import NovelGenerationResponseMixin
from .features.novel.optimizer import NovelInstructionOptimizerMixin
from .features.novel.project import NovelProjectMixin
from .features.novel.quality import NovelQualityMixin
from .features.novel.handoff import NovelHandoffMixin
from .features.novel.serialization import NovelSerializationMixin
from .features.novel.shortform import NovelShortformMixin
from .features.novel.state import NovelStateMixin


class NovelService(
    NovelCanvasMixin,
    NovelCanvasPromptMixin,
    NovelCanvasParsingMixin,
    NovelCanvasPlanningMixin,
    NovelCanvasDefaultMixin,
    NovelCanvasAccessMixin,
    NovelCanvasSyncMixin,
    NovelProjectMixin,
    NovelGenerationMixin,
    NovelGenerationPostprocessMixin,
    NovelGenerationResponseMixin,
    NovelGenerationBeatsMixin,
    NovelGenerationContextMixin,
    NovelGenerationMockMixin,
    NovelInstructionOptimizerMixin,
    NovelQualityMixin,
    NovelAuditMixin,
    NovelHandoffMixin,
    NovelShortformMixin,
    NovelStateMixin,
    NovelSerializationMixin,
):
    def __init__(
        self,
        state_service: CharacterStateService,
        bond_service: CharacterBondService,
        storage: Storage | None = None,
    ) -> None:
        self.state_service = state_service
        self.bond_service = bond_service
        self.storage = storage
