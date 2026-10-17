"""In-memory editing state. No Qt ownership or document writes live here."""
from copy import deepcopy
from uuid import uuid4

from ..profiles.validation import CatalogError
from .realization import build_candidate
from .serialization import decode_state


class TrussEditSession:
    def __init__(self, document, owner, config, document_is_open=None):
        self.identity = uuid4().hex
        self.document = document
        self.owner = owner
        self._document_is_open = document_is_open
        self.owner_name = getattr(owner, "Name", None)
        self.closed = False
        self.config = deepcopy(config)
        self._baseline = deepcopy(config)
        self.applied_state = getattr(owner, "AppliedState", "") if owner is not None else ""
        self.realized_state = decode_state(self.applied_state) if self.applied_state else None
        self.realized_config = (deepcopy(self.realized_state["candidate"]["config"])
                                if self.realized_state is not None else None)
        self._clean_config = self._normalized_config(config)
        self._projection_initialized = False
        self._observed = deepcopy(config)
        self._revision = 0
        self.validated_revision = None
        self.reconciliation_candidate = None
        self.diagnostics = ()
        self.conflict_reason = ""
        self.persisted_config = None

    def assert_persistence(self, requested_config=None):
        """Detect external edits against the document snapshot, never against the draft."""
        self.assert_context(self.document, self.owner)
        if self.owner is not None and not self.conflict_reason:
            if (self.owner.AppliedState != self.applied_state
                    or (self.persisted_config is not None
                        and requested_config != self.persisted_config)):
                self.conflict_reason = (
                    "A treliça foi alterada fora desta sessão (Undo/Redo ou edição externa). "
                    "Cancele e reabra a treliça antes de aplicar.")
        if self.conflict_reason:
            self.invalidate(self.conflict_reason)
            raise ValueError(self.conflict_reason)

    @property
    def needs_application(self):
        if self.owner is None or self.pending_changes:
            return True
        # A loaded requested definition can differ from the last successful result.
        # Fill missing legacy/UI defaults without hiding actual persisted differences.
        realized = deepcopy(self._clean_config)
        realized.update(self.realized_config or {})
        return self._normalized_config(realized) != self._clean_config

    def mark_applied(self, owner, requested_config=None):
        """Rebase only after apply_truss committed; adopt its actual realized definition."""
        state = decode_state(owner.AppliedState)
        candidate = build_candidate(state["candidate"]["config"])
        self.owner, self.owner_name = owner, owner.Name
        self.applied_state = owner.AppliedState
        self.realized_state = state
        self.realized_config = deepcopy(state["candidate"]["config"])
        self.persisted_config = deepcopy(requested_config)
        self.record_candidate(candidate)
        self._baseline = self.snapshot()
        self._clean_config = self._normalized_config(self.config)

    @staticmethod
    def _normalized_config(config):
        # Loading an invalid definition must still allow the user to repair it.
        try:
            normalized = build_candidate(config).config
            normalized.setdefault("connection_intents", {})
            return normalized
        except (ValueError, RuntimeError, KeyError, TypeError, CatalogError):
            return deepcopy(config)

    def initialize_projection(self, config):
        """Account once for defaults displayed by legacy controls, before editing."""
        if self._projection_initialized or self.reconciliation_candidate is not None:
            raise ValueError("A projeção inicial da sessão já foi estabelecida.")
        self.replace_config(config)
        self._clean_config = self._normalized_config(config)
        self._projection_initialized = True

    @property
    def valid(self):
        if self.conflict_reason:
            return False
        try:
            self.assert_context(self.document, self.owner)
        except (ValueError, RuntimeError, ReferenceError):
            return False
        return True

    @property
    def baseline_config(self):
        return deepcopy(self._baseline)

    def assert_context(self, document, owner):
        if self.closed or document is not self.document or owner is not self.owner:
            raise ValueError("Sessão de treliça encerrada ou pertencente a outro documento/objeto.")
        if self._document_is_open is not None and not self._document_is_open():
            raise ValueError("O documento da sessão de treliça foi fechado.")
        if owner is not None and document is not None:
            if owner.Document is not document or document.getObject(self.owner_name) is not owner:
                raise ValueError("O objeto da sessão de treliça não está mais no documento.")

    def _sync_revision(self):
        if self.config != self._observed:
            self._revision += 1
            self._observed = deepcopy(self.config)
            self.validated_revision = None

    @property
    def revision(self):
        self._sync_revision()
        return self._revision

    @property
    def validated_candidate(self):
        return (self.reconciliation_candidate
                if self.valid and self.validated_revision == self.revision else None)

    @property
    def pending_changes(self):
        self._sync_revision()
        if self.config == self._baseline or self.config == self._clean_config:
            return False
        try:
            normalized = build_candidate(self.config).config
            normalized.setdefault("connection_intents", {})
            return normalized != self._clean_config
        except (ValueError, RuntimeError, KeyError, TypeError, CatalogError):
            return True

    def snapshot(self):
        self.assert_context(self.document, self.owner)
        self._sync_revision()
        return deepcopy(self.config)

    def replace_config(self, config):
        self.assert_context(self.document, self.owner)
        if config != self.config:
            self.config.clear()
            self.config.update(deepcopy(config))
        self._sync_revision()

    def record_candidate(self, candidate):
        self.replace_config(candidate.config)
        self.reconciliation_candidate = candidate
        self.validated_revision = self.revision
        self.diagnostics = tuple(candidate.warnings)

    def invalidate(self, message):
        self._sync_revision()
        self.validated_revision = None
        self.diagnostics = (str(message),)

    def close(self):
        self.closed = True
        self.validated_revision = None
