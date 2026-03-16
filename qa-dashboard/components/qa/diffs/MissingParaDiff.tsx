import type { MissingParagraphIssue } from "@/lib/types";

interface Props {
  issue: MissingParagraphIssue;
}

/**
 * Renders a missing-paragraph diff as typed React nodes.
 *
 * The entire paragraph is the missing content — no inline diff is possible.
 * The .para-missing class is already defined in the stylesheet.
 * Text is rendered as a React text node — not injected as HTML.
 */
export default function MissingParaDiff({ issue }: Props) {
  return <div className="para-missing">{issue.paragraph_text}</div>;
}
