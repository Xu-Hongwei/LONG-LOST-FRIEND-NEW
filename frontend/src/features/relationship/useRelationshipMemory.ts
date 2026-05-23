import { computed, ref, watch, type Ref } from "vue";
import { deleteMemoryItem, patchMemory, updateMemoryItem } from "./api";
import type { ContextSlot, MemoryItem, MemoryPane, MemoryPatch } from "../../types";

type MemoryFilter = "all" | "global" | "character" | "session" | "recall";

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

export function useRelationshipMemory(
  sessionId: Ref<string>,
  memoryPane: Ref<MemoryPane | null>,
  promptSlots: Ref<ContextSlot[]>,
  busy: Ref<boolean>,
  error: Ref<string>
) {
  const manualNoteDraft = ref("");
  const memoryFilter = ref<MemoryFilter>("all");
  const editingMemoryId = ref("");
  const memoryDraft = ref<MemoryPatch>({});
  const expandedMemoryId = ref("");
  const expandedSlotKey = ref("");
  const stateExpanded = ref(false);
  const bondExpanded = ref(false);

  watch(memoryPane, (pane) => {
    manualNoteDraft.value = pane?.manual_note || "";
  }, { immediate: true });

  const includedSlots = computed(() => promptSlots.value.filter((slot) => slot.included));
  const excludedSlots = computed(() => promptSlots.value.filter((slot) => !slot.included));
  const filteredMemories = computed(() => {
    if (!memoryPane.value) return [];
    if (memoryFilter.value === "recall") return memoryPane.value.last_recall || [];
    if (memoryFilter.value === "all") return memoryPane.value.memories;
    return memoryPane.value.memories.filter((memory) => memory.memory_scope === memoryFilter.value);
  });
  const recallCount = computed(() => memoryPane.value?.last_recall?.length || 0);
  const memoryCounts = computed(() => {
    const memories = memoryPane.value?.memories || [];
    return {
      all: memories.length,
      global: memories.filter((memory) => memory.memory_scope === "global").length,
      character: memories.filter((memory) => memory.memory_scope === "character").length,
      session: memories.filter((memory) => memory.memory_scope === "session").length,
      recall: recallCount.value
    };
  });
  const memoryDiagnostics = computed(() => memoryPane.value?.diagnostics || {});
  const postprocessStatus = computed(() => String(memoryDiagnostics.value.status || "idle"));
  const postprocessStatusLabel = computed(() => {
    const labels: Record<string, string> = {
      idle: "idle",
      queued: "queued",
      running: "running",
      succeeded: "succeeded",
      failed: "failed",
      skipped: "skipped",
      partial: "partial"
    };
    return labels[postprocessStatus.value] || postprocessStatus.value;
  });
  const postprocessStages = computed(() => {
    const stages = memoryDiagnostics.value.stages;
    if (!stages || typeof stages !== "object") return [];
    return ["memory", "state", "bond"].map((key) => {
      const stage = ((stages as Record<string, unknown>)[key] || {}) as Record<string, unknown>;
      return {
        key,
        status: String(stage.status || "idle"),
        detail: stage.error_type
          ? String(stage.error_type)
          : stage.reason
            ? String(stage.reason)
            : key === "bond" && stage.status === "succeeded"
              ? `${Number(stage.accepted_events_count || 0)}/${Number(stage.extracted_events_count || 0)} events${stage.stage_changed ? " / stage changed" : ""}${stage.condition_changed ? " / condition changed" : ""}${stage.progression_frozen ? " / frozen" : ""}`
            : key === "memory" && stage.status === "succeeded"
              ? `${Number(stage.stored_count || 0)} saved`
              : stage.updated !== undefined
                ? `updated ${stage.updated ? "yes" : "no"}`
                : stage.duration_ms !== undefined
                  ? `${Number(stage.duration_ms)}ms`
                  : ""
      };
    });
  });
  const postprocessDetail = computed(() => {
    const diagnostics = memoryDiagnostics.value;
    if (postprocessStatus.value === "failed") {
      return String(diagnostics.error_type || diagnostics.error_message || "unknown error");
    }
    if (postprocessStatus.value === "skipped") {
      return String(diagnostics.reason || "not available");
    }
    if (postprocessStatus.value === "succeeded") {
      return `${Number(diagnostics.stored_count || 0)} saved / ${Number(diagnostics.extracted_count || 0)} extracted`;
    }
    if (postprocessStatus.value === "partial") {
      return `${Number(diagnostics.stored_count || 0)} saved, some stages failed`;
    }
    if (postprocessStatus.value === "queued" || postprocessStatus.value === "running") {
      return String(diagnostics.user_message_id || "");
    }
    return "no recent analysis";
  });

  async function saveMemoryNote() {
    if (!sessionId.value || !memoryPane.value) return;
    busy.value = true;
    error.value = "";
    try {
      memoryPane.value = await patchMemory(sessionId.value, { manual_note: manualNoteDraft.value });
    } catch (err) {
      error.value = readableError(err);
    } finally {
      busy.value = false;
    }
  }

  async function toggleFreeze() {
    if (!sessionId.value || !memoryPane.value) return;
    busy.value = true;
    error.value = "";
    try {
      memoryPane.value = await patchMemory(sessionId.value, { frozen: !memoryPane.value.frozen });
    } catch (err) {
      error.value = readableError(err);
    } finally {
      busy.value = false;
    }
  }

  function startEditMemory(memory: MemoryItem) {
    editingMemoryId.value = memory.id;
    memoryDraft.value = {
      memory_type: memory.memory_type,
      memory_scope: memory.memory_scope,
      content: memory.content,
      confidence: memory.confidence,
      importance: memory.importance
    };
  }

  function cancelEditMemory() {
    editingMemoryId.value = "";
    memoryDraft.value = {};
  }

  async function saveMemoryItem(memoryId: string) {
    if (!sessionId.value) return;
    busy.value = true;
    error.value = "";
    try {
      memoryPane.value = await updateMemoryItem(sessionId.value, memoryId, memoryDraft.value);
      cancelEditMemory();
    } catch (err) {
      error.value = readableError(err);
    } finally {
      busy.value = false;
    }
  }

  async function removeMemoryItem(memoryId: string) {
    if (!sessionId.value) return;
    busy.value = true;
    error.value = "";
    try {
      memoryPane.value = await deleteMemoryItem(sessionId.value, memoryId);
      if (editingMemoryId.value === memoryId) cancelEditMemory();
      if (expandedMemoryId.value === memoryId) expandedMemoryId.value = "";
    } catch (err) {
      error.value = readableError(err);
    } finally {
      busy.value = false;
    }
  }

  function toggleMemoryDetails(memoryId: string) {
    expandedMemoryId.value = expandedMemoryId.value === memoryId ? "" : memoryId;
  }

  function toggleSlotDetails(slotKey: string) {
    expandedSlotKey.value = expandedSlotKey.value === slotKey ? "" : slotKey;
  }

  return {
    manualNoteDraft,
    memoryFilter,
    editingMemoryId,
    memoryDraft,
    expandedMemoryId,
    expandedSlotKey,
    stateExpanded,
    bondExpanded,
    includedSlots,
    excludedSlots,
    filteredMemories,
    memoryCounts,
    memoryDiagnostics,
    postprocessStatus,
    postprocessStatusLabel,
    postprocessStages,
    postprocessDetail,
    saveMemoryNote,
    toggleFreeze,
    startEditMemory,
    cancelEditMemory,
    saveMemoryItem,
    removeMemoryItem,
    toggleMemoryDetails,
    toggleSlotDetails
  };
}
