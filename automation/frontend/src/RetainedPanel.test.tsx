import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useEffect, useState } from "react";
import { RetainedPanel, usePanelActive } from "./RetainedPanel";
afterEach(cleanup);
it("延迟挂载、保留本地结果、冻结隐藏修订并传递可见状态", () => {
  const request = vi.fn();
  function Page({ revision }: { revision: number }) {
    const [text, setText] = useState("");
    const active = usePanelActive();
    useEffect(() => {
      request(revision);
    }, [revision]);
    return (
      <input
        aria-label="草稿"
        value={text}
        data-active={String(active)}
        onChange={(event) => setText(event.target.value)}
      />
    );
  }
  const view = render(
    <RetainedPanel active={false}>
      <Page revision={0} />
    </RetainedPanel>,
  );
  expect(request).not.toHaveBeenCalled();
  view.rerender(
    <RetainedPanel active>
      <Page revision={0} />
    </RetainedPanel>,
  );
  fireEvent.change(screen.getByLabelText("草稿"), {
    target: { value: "保留结果" },
  });
  view.rerender(
    <RetainedPanel active={false}>
      <Page revision={1} />
    </RetainedPanel>,
  );
  expect(screen.getByLabelText("草稿")).not.toBeVisible();
  expect(screen.getByLabelText("草稿")).toHaveAttribute("data-active", "false");
  expect(request).toHaveBeenCalledTimes(1);
  view.rerender(
    <RetainedPanel active>
      <Page revision={1} />
    </RetainedPanel>,
  );
  expect(screen.getByLabelText("草稿")).toHaveValue("保留结果");
  expect(request).toHaveBeenCalledTimes(2);
});
it("预加载只执行一次，导航恢复不重新挂载", () => {
  const mounted = vi.fn();
  function Page() {
    useEffect(mounted, []);
    return <p>证据</p>;
  }
  const view = render(
    <RetainedPanel active={false} preload>
      <Page />
    </RetainedPanel>,
  );
  expect(mounted).toHaveBeenCalledTimes(1);
  view.rerender(
    <RetainedPanel active preload>
      <Page />
    </RetainedPanel>,
  );
  expect(mounted).toHaveBeenCalledTimes(1);
  expect(screen.getByText("证据")).toBeVisible();
});
