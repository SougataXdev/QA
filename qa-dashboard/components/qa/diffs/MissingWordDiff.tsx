import type { MissingWordIssue } from "@/lib/types";

interface Props {
  issue: MissingWordIssue;
}

/**
 * Renders a missing-word diff as typed React nodes.
 *
 * Each missing token is its own <del> element so that multi-word gaps
 * render clearly. Context words before and after the gap are plain text.
 * All content is rendered as React text nodes — no dangerouslySetInnerHTML.
 *
 *   context_before  [del token1] [del token2] ...  context_after
 */
export default function MissingWordDiff({ issue }: Props) {
  // Defensive fallback: cached job results predating the missing_tokens field
  // will have the field absent at runtime despite the TypeScript type requiring it.
  const tokens: string[] = issue.missing_tokens ?? []

  return (
    <span>
      <span>{issue.context_before} </span>
      {tokens.map((token, idx) => (
        // Key uses index as a fallback — tokens within one issue are positional
        <del key={`${token}-${idx}`}>{token} </del>
      ))}
      <span>{issue.context_after}</span>
    </span>
  );
}
