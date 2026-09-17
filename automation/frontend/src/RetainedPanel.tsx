import { createContext, useContext, useRef, type ReactNode } from "react";
const PanelActivity = createContext(true);
export const usePanelActive = () => useContext(PanelActivity);
/** 首次访问才挂载，离开仅隐藏并冻结输入，保留结果与草稿且不因后台修订重新读取。 */
export function RetainedPanel({
  active,
  preload = false,
  children,
}: {
  active: boolean;
  preload?: boolean;
  children: ReactNode;
}) {
  const content = useRef<ReactNode>(null);
  if (active || (preload && content.current === null))
    content.current = children;
  const parentActive = usePanelActive();
  return (
    <PanelActivity.Provider value={active && parentActive}>
      <div hidden={!active}>{content.current}</div>
    </PanelActivity.Provider>
  );
}
