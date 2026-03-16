import type { CurrencyMismatchIssue } from "@/lib/types";

interface Props {
  issue: CurrencyMismatchIssue;
}

/**
 * Renders a currency-mismatch diff as typed React nodes.
 *
 * Shows the wrong website value struck through (<del>) and the correct
 * PDF value inserted (<ins>), with surrounding context. All text is
 * rendered as React text nodes — React's JSX renderer automatically
 * escapes any "<", ">", or "&" in the data, eliminating XSS risk.
 *
 *   context_before  [web_symbol  numeric + unit]  [pdf_symbol  numeric + unit]  context_after
 *                    ───── del ──────────────────   ───────── ins ──────────────
 */
export default function CurrencyMismatchDiff({ issue }: Props) {
  const unit = issue.unit ? ` ${issue.unit}` : "";

  return (
    <span>
      <span>{issue.context_before}</span>
      {/* What the website wrongly shows */}
      <del>
        {issue.web_symbol}
        {issue.numeric_value}
        {unit}
      </del>{" "}
      {/* What the PDF says it should be */}
      <ins>
        {issue.pdf_symbol}
        {issue.numeric_value}
        {unit}
      </ins>
      <span>{issue.context_after}</span>
    </span>
  );
}
