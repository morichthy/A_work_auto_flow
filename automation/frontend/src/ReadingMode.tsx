import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { failureMessage, type Reading, type Result } from "./CurrentReading";

/** 草稿由会话 key 隔离；保存后读服务器 HEAD，绝不在浏览器推算修订或启动 AI。 */
export function ReadingMode({
  reading,
  onSaved,
}: {
  reading: Reading;
  onSaved: (value: Reading) => void;
}) {
  const [strategy, setStrategy] = useState(reading.strategy ?? "standard");
  const [text, setText] = useState(reading.association_text ?? "");
  const [revision, setRevision] = useState(reading.revision);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const active = useRef(true),
    pending = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  // 外部显式刷新可能取得新版。保留未保存草稿，不自行覆盖服务器字段。
  useEffect(() => {
    setRevision(reading.revision);
  }, [reading.revision]);
  async function perform(save: boolean) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (save) {
        const result = await api<Result<unknown>>(
          "materials/reading-configure",
          {
            session_id: reading.session_id,
            expected_revision: revision,
            request_id: crypto.randomUUID(),
            strategy,
            association_text: text,
            // 显式选择联想模式即允许本会话联想；保留轮次上限，不改工作区偏好。
            ...(strategy === "associative"
              ? {
                  association: {
                    ...(reading.association ?? { max_rounds: 3 }),
                    enabled: true,
                  },
                }
              : {}),
          },
        );
        if (!active.current) return;
        if (!result.value) throw Error(failureMessage(result));
      }
      const response = await api<Result<Reading>>("materials/reading-view", {
        session_id: reading.session_id,
        notes_only: true,
      });
      if (!active.current) return;
      if (!response.value) throw Error(failureMessage(response));
      setRevision(response.value.revision);
      onSaved(response.value);
      setMessage(
        save
          ? "模式与方向已保存，交给阅读 agent 后继续；尚未启动搜索。"
          : "已读取最新版本，草稿保留，请核对后保存。",
      );
    } catch (e) {
      if (active.current) setError(failureMessage(e) + "；草稿已保留。");
    } finally {
      pending.current = false;
      if (active.current) setBusy(false);
    }
  }
  return (
    <section aria-label="阅读模式设置">
      <label className="field">
        当前阅读模式
        <select
          aria-label="当前阅读模式"
          value={strategy}
          disabled={busy || reading.archived}
          onChange={(e) => {
            setStrategy(e.target.value as NonNullable<Reading["strategy"]>);
            setMessage("");
          }}
        >
          <option value="standard">标准阅读</option>
          <option value="associative">联想加深</option>
          <option value="quick">快速阅读</option>
        </select>
      </label>
      <p className="muted">
        标准阅读：检索 → Owner → 完整文稿 →
        note。联想加深：沿已有note线索在同一会话继续阅读。快速阅读：逐条判断召回文本并写note，不代表全文覆盖。
      </p>
      <label className="field">
        联想搜索文本（可选）
        <textarea
          aria-label="联想搜索文本（可选）"
          rows={3}
          value={text}
          disabled={busy || reading.archived}
          onChange={(e) => {
            setText(e.target.value);
            setMessage("");
          }}
        />
      </label>
      <p className="muted">
        留空时由阅读 agent
        根据已有note与缺口提出方向；保存只更新本会话，不修改原目标、授权或工作区默认值。
      </p>
      {strategy === "associative" && (
        <p className="muted">
          保存联想加深模式会启用本会话联想，最多
          {reading.association?.max_rounds ?? 3}轮，已用轮次不重置。
        </p>
      )}
      <button
        disabled={busy || reading.archived}
        onClick={() => void perform(true)}
      >
        保存阅读模式与方向
      </button>
      <button disabled={busy} onClick={() => void perform(false)}>
        读取最新会话（保留草稿）
      </button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
