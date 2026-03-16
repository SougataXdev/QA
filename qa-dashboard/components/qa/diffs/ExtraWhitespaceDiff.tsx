import type { ExtraWhitespaceIssue } from "@/lib/types";

interface Props {
  issue: ExtraWhitespaceIssue;
}

/**
 * Renders an extra-whitespace diff as typed React nodes.
 *
 * The invisible error (multiple spaces) is made visible via a <mark>
 * that shows how many spaces were found. All text comes from typed
 * string fields — no HTML strings, no dangerouslySetInnerHTML.
 *
 *   context_before  [N spaces]  context_after
 */
export default function ExtraWhitespaceDiff({ issue }: Props) {
  return (
    <span>
      <span>{issue.context_before}</span>
      <mark className="ws">[{issue.space_count} spaces]</mark>
      <span>{issue.context_after}</span>
    </span>
  );
}
