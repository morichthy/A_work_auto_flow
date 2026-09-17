"""查询生命周期内的累计硬预算；活动执行时间与用户停留TTL分开。

读取在打开文件前预留额度；同一个查询的并发操作由状态锁拒绝。
取消使用独立Event，不等待执行锁，因此首次异步搜索也可停止后续工作。
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import threading
import time
import uuid

from .contracts import Budget
from .validation import QueryError


class Ledger:
    def __init__(self, limits, *, clock=time.monotonic):
        self.limits = asdict(limits)
        self.used = {key: 0 for key in self.limits}
        self.clock = clock
        self.cancelled = threading.Event()
        self.lock = threading.RLock()
        self.active_started = None
        self.elapsed_seconds = 0.0
        # Held capacity is separate from actual usage. A provider consumes its
        # own hold, and its caller later confirms the same totals with settle;
        # the confirmation must not debit those bytes/tokens a second time.
        self.held = {key: 0 for key in self.limits}
        self.budget_handle = "BL-" + str(uuid.uuid4())
        self.reservations = {}
        self.provider_context = threading.local()
        self.provider_overrun = False

    def _elapsed_ms(self):
        seconds = self.elapsed_seconds + ((self.clock() - self.active_started) if self.active_started is not None else 0.0)
        return int(seconds * 1000)

    def checkpoint(self):
        if self.cancelled.is_set():
            raise QueryError("CANCELLED", "操作已取消，已完成部分保留")
        with self.lock:
            elapsed = self._elapsed_ms()
            if elapsed >= self.limits["wall_ms"]:
                raise QueryError("BUDGET", "执行时间预算已用完")
            if self.provider_overrun or any(self.used[key] > limit for key, limit in self.limits.items() if key != "wall_ms"):
                raise QueryError("BUDGET", "提供器实际消耗超出预约，已如实结算并停止新工作")

    def charge(self, key, amount, *, reservation=None):
        self.checkpoint()
        if type(amount) is not int or amount < 0 or key not in self.used:
            raise ValueError("invalid trusted budget accounting")
        if key == "wall_ms":
            raise ValueError("wall time is observed by active intervals, not manually charged")
        with self.lock:
            token = reservation or getattr(self.provider_context, "reservation", None)
            if token is not None:
                saved = self._reservation(token)
                if saved["receipt"] is not None:
                    raise QueryError("CONFLICT", "已结算的预约不能继续扣费")
                if saved["spent"][key] + amount > saved["token"]["ceiling"][key]:
                    raise QueryError("BUDGET", "提供器工作超过已预约上界，执行前拒绝")
                saved["spent"][key] += amount
                self.held[key] -= amount
            elif self.used[key] + self.held[key] + amount > self.limits[key]:
                raise QueryError("BUDGET", "操作达到累计预算上限或占用了其他提供器预约")
            self.used[key] += amount

    def remaining(self, key):
        with self.lock:
            observed = self._elapsed_ms() if key == "wall_ms" else self.used[key]
            token = getattr(self.provider_context, "reservation", None)
            if token is not None:
                saved = self._reservation(token)
                if saved["receipt"] is None:
                    return max(0, saved["token"]["ceiling"][key] - saved["spent"][key])
            return max(0, self.limits[key] - observed - self.held[key])

    def snapshot(self):
        with self.lock:
            value = dict(self.used)
            value["wall_ms"] = self._elapsed_ms()
            # elapsed is an observed cost, not a fabricated clamped value. A
            # blocking primitive may finish just after a deadline; callers must
            # checkpoint after it and return budget/partial, never success.
            return value

    def _usage(self, raw):
        """部分维度按零补齐；bool、负值、未知单位都不能进入可信账本。"""
        if not isinstance(raw, dict) or set(raw) - set(self.limits) or any(type(value) is not int or value < 0 for value in raw.values()):
            raise QueryError("VALIDATION", "费用必须是已登记维度的非负整数")
        return {key: raw.get(key, 0) for key in self.limits}

    def _reservation(self, token):
        if not isinstance(token, dict) or set(token) != {"reservation_id", "budget_handle", "ceiling"}:
            raise QueryError("VALIDATION", "预约凭据结构不正确")
        saved = self.reservations.get(token["reservation_id"]) if isinstance(token["reservation_id"], str) else None
        if token["budget_handle"] != self.budget_handle or saved is None:
            raise QueryError("DENIED", "预约不属于当前查询账本")
        if token != saved["token"]:
            raise QueryError("CONFLICT", "不能修改已签发预约的成本上界")
        return saved

    def reserve(self, ceiling):
        """原子占有尚未消费的额度；并行提供器不能预约同一份剩余额度。"""
        requested = self._usage(ceiling)
        with self.lock:
            self.checkpoint()
            if getattr(self.provider_context, "reservation", None) is not None:
                raise QueryError("CONFLICT", "父流水线已有预约；子调用应沿用该预约而非重复预订")
            for key, amount in requested.items():
                observed = self._elapsed_ms() if key == "wall_ms" else self.used[key]
                if observed + self.held[key] + amount > self.limits[key]:
                    raise QueryError("BUDGET", "剩余额度无法保证提供器声明的成本上界")
            token = {"reservation_id": "BR-" + str(uuid.uuid4()), "budget_handle": self.budget_handle, "ceiling": requested}
            self.reservations[token["reservation_id"]] = {"token": deepcopy(token), "spent": {key: 0 for key in self.limits}, "receipt": None}
            for key, amount in requested.items():
                self.held[key] += amount
            return token

    def settle(self, reservation, actual):
        """确认真实消耗并释放余量；取消/超时之后仍必须允许执行此清账动作。

        外部提供器事后报告超出预约时无法撤销已发生费用，因此如实记账并在
        receipt 标记 overrun；后续 checkpoint 拒绝继续工作。已通过 charge
        计量的子调用费用只核对，不重复累计。墙钟始终取活动区间的实际并集，
        不累加客户端或并行子提供器报告的 wall_ms。
        """
        observed = self._usage(actual)
        with self.lock:
            saved = self._reservation(reservation)
            if saved["receipt"] is not None:
                if saved["receipt"]["actual"] != observed:
                    raise QueryError("CONFLICT", "同一预约重复结算的实际消耗不一致")
                return deepcopy(saved["receipt"])
            if any(observed[key] < saved["spent"][key] for key in self.limits if key != "wall_ms"):
                raise QueryError("CONFLICT", "结算值不能少于已实际计量的子调用消耗")
            ceiling = saved["token"]["ceiling"]
            overrun = any(observed[key] > ceiling[key] for key in self.limits)
            self.provider_overrun |= overrun
            for key in self.limits:
                self.held[key] -= ceiling[key] - saved["spent"][key]
                if key != "wall_ms":
                    self.used[key] += observed[key] - saved["spent"][key]
            receipt = {"reservation_id": reservation["reservation_id"], "budget_handle": self.budget_handle,
                       "actual": observed, "released": {key: max(0, ceiling[key] - observed[key]) for key in self.limits},
                       "overrun": overrun, "consumed": self.snapshot()}
            saved["receipt"] = deepcopy(receipt)
            return receipt

    @contextmanager
    def provider(self, reservation):
        """将已有 charge 调用绑定到实际提供器预约；父子调用沿用同一身份。"""
        with self.lock:
            saved = self._reservation(reservation)
            if saved["receipt"] is not None:
                raise QueryError("CONFLICT", "已结算预约不能开始提供器工作")
        previous = getattr(self.provider_context, "reservation", None)
        if previous is not None and previous != reservation:
            raise QueryError("CONFLICT", "嵌套提供器不能切换预约身份")
        self.provider_context.reservation = reservation
        try:
            self.checkpoint()
            yield
        finally:
            self.provider_context.reservation = previous

    @contextmanager
    def active(self, *, cleanup=False):
        with self.lock:
            if self.active_started is not None:
                raise QueryError("CONFLICT", "同一查询已有活动操作")
            self.active_started = self.clock()
        try:
            if not cleanup:
                self.checkpoint()
            yield
            if not cleanup:
                self.checkpoint()
        finally:
            with self.lock:
                self.elapsed_seconds += self.clock() - self.active_started
                self.used["wall_ms"] = int(self.elapsed_seconds * 1000)
                self.active_started = None


# 默认5分钟为实际活动时间之和，用户停留不扣时间。真实文稿的固定来源
# 重核也消耗字节；16 MiB / 8万字符容纳同一次查询的组装与连续展开，
# 不靠重置账本或跳过授权来掩盖原2 MiB过早耗尽的问题。
DEFAULT_BUDGET = Budget(300000, 16 * 1024 * 1024, 80000, 100, 50, 100, 2, 0)
SERVER_LIMITS = Budget(600000, 32 * 1024 * 1024, 100000, 2000, 1000, 2000, 6, 200000, 20, 150000, 50000, 200)


def check_limits(budget):
    for key, value in asdict(budget).items():
        if value > getattr(SERVER_LIMITS, key):
            raise QueryError("VALIDATION", "请求预算超过服务器允许上限", fields=(key,))
