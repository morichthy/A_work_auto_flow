/** Human-facing export name only: never change the authoritative RS identity.
 * Windows filename characters/control bytes are removed; code-point truncation
 * preserves Unicode characters. A short RS suffix distinguishes equal goals. */
export function readingNoteName(
  goal: string | undefined,
  sessionId: string,
  revision: number,
) {
  const clean = (goal || "")
    .replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, "-")
    .replace(/-+/g, "-")
    .replace(/\s+/g, " ")
    .trim();
  const title =
    [...clean]
      .slice(0, 48)
      .join("")
      .replace(/[. -]+$/g, "") || "阅读笔记";
  const shortId =
    sessionId
      .replace(/^RS-/, "")
      .replace(/[^a-zA-Z0-9]/g, "")
      .slice(0, 12) || "unknown";
  return `${title}-RS-${shortId}-r${revision}.md`;
}
