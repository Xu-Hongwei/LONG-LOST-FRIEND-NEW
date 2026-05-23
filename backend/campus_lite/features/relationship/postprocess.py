from __future__ import annotations

import logging
import time

from ...characters import CharacterStore
from ...llm import LlmClient
from ...storage import Storage
from .bond import CharacterBondService
from .memory import MemoryService
from .state import CharacterStateService


logger = logging.getLogger(__name__)


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


class RelationshipPostprocessService:
    def __init__(
        self,
        *,
        storage: Storage,
        characters: CharacterStore,
        memory: MemoryService,
        character_state: CharacterStateService,
        character_bond: CharacterBondService,
        llm: LlmClient,
    ) -> None:
        self.storage = storage
        self.characters = characters
        self.memory = memory
        self.character_state = character_state
        self.character_bond = character_bond
        self.llm = llm

    async def run(
        self,
        visitor_id: str,
        session_id: str,
        user_message_id: str,
        card_id: str,
        user_text: str,
        reply: str,
        recalled: list,
        recent: list[dict[str, str]],
        previous_state: dict[str, object],
        previous_bond: dict[str, object],
    ) -> None:
        started = time.perf_counter()
        diagnostics = {
            "status": "running",
            "user_message_id": user_message_id,
            "started_at": utc_timestamp(),
            "stages": {
                "memory": {"status": "queued"},
                "state": {"status": "queued"},
                "bond": {"status": "queued"},
            },
        }

        def set_stage(stage: str, payload: dict[str, object]) -> None:
            stages = diagnostics.setdefault("stages", {})
            stage_payload = dict(stages.get(stage, {})) if isinstance(stages, dict) else {}
            stage_payload.update(payload)
            diagnostics["stages"][stage] = stage_payload
            self.storage.set_postprocess_diagnostics(session_id, diagnostics)

        self.storage.set_postprocess_diagnostics(session_id, diagnostics)
        try:
            if not self.llm.provider:
                diagnostics.update({
                    "status": "skipped",
                    "finished_at": utc_timestamp(),
                    "duration_ms": elapsed_ms(started),
                    "reason": "llm_not_configured",
                    "stages": {
                        "memory": {"status": "skipped", "reason": "llm_not_configured"},
                        "state": {"status": "skipped", "reason": "llm_not_configured"},
                        "bond": {"status": "skipped", "reason": "llm_not_configured"},
                    },
                })
                self.storage.set_postprocess_diagnostics(session_id, diagnostics)
                return

            card = self.characters.get(card_id)
            session = self.storage.get_session(session_id)
            frozen = bool(session["frozen"]) if session else False
            extracted = []
            memory_records = []
            embedded_count = 0
            summary_updated = False

            memory_started = time.perf_counter()
            if frozen:
                set_stage("memory", {"status": "skipped", "reason": "session_frozen", "finished_at": utc_timestamp()})
            else:
                set_stage("memory", {"status": "running", "started_at": utc_timestamp()})
                extracted = await self.llm.extract_memories(user_text, reply)
                memory_error = self.llm.last_chat_error
                if memory_error:
                    set_stage(
                        "memory",
                        {
                            "status": "failed",
                            "finished_at": utc_timestamp(),
                            "duration_ms": elapsed_ms(memory_started),
                            "error_type": memory_error,
                        },
                    )
                    logger.warning("memory extraction failed for session %s: %s", session_id, memory_error)
                else:
                    memory_records = self.memory.add_extracted(visitor_id, session_id, card.id, user_message_id, extracted)
                    if memory_records:
                        vectors = await self.llm.embed_texts([content for _, content in memory_records])
                        self.memory.store_embeddings(memory_records, vectors, self.llm.embedding_provider_name() if vectors else None)
                        embedded_count = len(vectors)
                    if extracted or len(self.storage.recent_messages(session_id, 20)) >= 6:
                        self.memory.update_recent_summary(session_id)
                        summary_updated = True
                    set_stage(
                        "memory",
                        {
                            "status": "succeeded",
                            "finished_at": utc_timestamp(),
                            "duration_ms": elapsed_ms(memory_started),
                            "extracted_count": len(extracted),
                            "stored_count": len(memory_records),
                            "embedded_count": embedded_count,
                            "summary_updated": summary_updated,
                        },
                    )

            state_started = time.perf_counter()
            set_stage("state", {"status": "running", "started_at": utc_timestamp()})
            scored_state = await self.llm.score_character_state(card, previous_state, recent, user_text, reply, recalled)
            state_error = self.llm.last_chat_error
            if state_error:
                set_stage(
                    "state",
                    {
                        "status": "failed",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(state_started),
                        "error_type": state_error,
                    },
                )
                logger.warning("state analysis failed for session %s: %s", session_id, state_error)
            else:
                self.character_state.update_from_score(session_id, previous_state, scored_state, card)
                set_stage(
                    "state",
                    {
                        "status": "succeeded",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(state_started),
                        "updated": bool(scored_state),
                    },
                )

            bond_started = time.perf_counter()
            set_stage("bond", {"status": "running", "started_at": utc_timestamp()})
            extracted_events = await self.llm.extract_relationship_events(
                card,
                previous_bond,
                previous_state,
                recent,
                user_text,
                reply,
                recalled,
            )
            bond_error = self.llm.last_chat_error
            if bond_error:
                set_stage(
                    "bond",
                    {
                        "status": "failed",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(bond_started),
                        "error_type": bond_error,
                    },
                )
                logger.warning("bond analysis failed for session %s: %s", session_id, bond_error)
            else:
                _, bond_diagnostics = self.character_bond.update_from_events(
                    visitor_id=visitor_id,
                    session_id=session_id,
                    source_message_ids=[user_message_id],
                    character=card,
                    previous=previous_bond,
                    extracted=extracted_events,
                    evidence_context=self.character_bond._evidence_context(recent, user_text, reply),
                )
                set_stage(
                    "bond",
                    {
                        "status": "succeeded",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(bond_started),
                        "updated": bool(bond_diagnostics["accepted_events_count"]),
                        **bond_diagnostics,
                    },
                )

            stage_statuses = [
                str(stage.get("status"))
                for stage in diagnostics.get("stages", {}).values()
                if isinstance(stage, dict)
            ]
            failed_count = sum(status == "failed" for status in stage_statuses)
            completed_count = sum(status in {"succeeded", "skipped"} for status in stage_statuses)
            overall_status = "succeeded"
            if failed_count and completed_count:
                overall_status = "partial"
            elif failed_count:
                overall_status = "failed"
            diagnostics.update({
                "status": overall_status,
                "finished_at": utc_timestamp(),
                "duration_ms": elapsed_ms(started),
                "extracted_count": len(extracted),
                "stored_count": len(memory_records),
                "embedded_count": embedded_count,
                "summary_updated": summary_updated,
                "frozen": frozen,
            })
            self.storage.set_postprocess_diagnostics(session_id, diagnostics)
        except Exception as exc:
            diagnostics.update({
                "status": "failed",
                "finished_at": utc_timestamp(),
                "duration_ms": elapsed_ms(started),
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:400],
            })
            self.storage.set_postprocess_diagnostics(session_id, diagnostics)
            logger.exception("post-turn analysis failed for session %s: %s", session_id, exc)
