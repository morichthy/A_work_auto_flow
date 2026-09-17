"""短期查询身份与会话绑定；重启/TTL到期不能重置旧查询账本。"""
from dataclasses import dataclass, field
import threading
import time
import uuid

from memory.contracts import canonical_hash

from .budget import Ledger, check_limits
from .validation import QueryError
from .wire import digest


@dataclass
class QueryState:
    query_id: str
    request: object
    request_digest: str
    ledger: Ledger
    created: float
    expires_at: str
    access_handle: str
    lock: object = field(default_factory=threading.Lock)
    result: dict | None = None
    candidates: dict = field(default_factory=dict)
    ordered: list = field(default_factory=list)
    cursor_ids: dict = field(default_factory=dict)
    responses: dict = field(default_factory=dict)
    status: str = "running"
    proposals: dict = field(default_factory=dict)
    # Search resumes the original metadata window. Only admitted records enter
    # ordered/candidates; unread identities stay here without cached body text.
    recall: dict = field(default_factory=dict)


class StateStore:
    def __init__(self, *, ttl=900, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self.access_handle = str(uuid.uuid4())
        self.states = {}
        self.lock = threading.RLock()

    def create(self, request):
        from dataclasses import asdict
        from datetime import datetime, timedelta, timezone
        check_limits(request.budget)
        now = self.clock()
        with self.lock:
            for key in list(self.states):
                if now - self.states[key].created >= self.ttl:
                    self.states[key].ledger.cancelled.set()
                    del self.states[key]
            if len(self.states) >= 128:
                raise QueryError("CONFLICT", "本会话查询数量达到上限，请等待旧查询到期")
            qid = "MQ-" + str(uuid.uuid4())
            state = QueryState(qid, request, digest(request), Ledger(request.budget, clock=self.clock), now,
                (datetime.now(timezone.utc) + timedelta(seconds=self.ttl)).isoformat().replace("+00:00", "Z"), self.access_handle)
            self.states[qid] = state
            return state

    def get(self, query_id):
        with self.lock:
            value = self.states.get(query_id)
            if value is None or self.clock() - value.created >= self.ttl:
                if value is not None:
                    value.ledger.cancelled.set()
                    del self.states[query_id]
                raise QueryError("EXPIRED", "查询已到期或进程已重启，请重新搜索")
            if value.access_handle != self.access_handle:
                raise QueryError("DENIED", "查询不属于当前会话")
            return value
