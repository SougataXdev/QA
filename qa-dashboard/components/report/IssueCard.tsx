"use client";

import { motion, AnimatePresence } from "motion/react";
import { useState } from "react";
import { ChevronRight, FileText, Globe } from "lucide-react";
import type { QAIssue } from "@/lib/types";
import ExtraWhitespaceDiff from "@/components/qa/diffs/ExtraWhitespaceDiff";
import CurrencyMismatchDiff from "@/components/qa/diffs/CurrencyMismatchDiff";
import MissingWordDiff from "@/components/qa/diffs/MissingWordDiff";
import MissingParaDiff from "@/components/qa/diffs/MissingParaDiff";

interface IssueCardProps {
  issue: QAIssue;
  index: number;
}

/**
 * Routes each typed QAIssue to its matching diff-renderer component.
 *
 * The switch exhausts the discriminated union — TypeScript will error if a
 * new issue type is added to QAIssue without a matching case here.
 * No dangerouslySetInnerHTML. All content is rendered as safe React nodes.
 */
function DiffRenderer({ issue }: { issue: QAIssue }) {
  switch (issue.type) {
    case "extra_whitespace":
      return <ExtraWhitespaceDiff issue={issue} />;
    case "currency_mismatch":
      return <CurrencyMismatchDiff issue={issue} />;
    case "missing_word":
      return <MissingWordDiff issue={issue} />;
    case "missing_paragraph":
      return <MissingParaDiff issue={issue} />;
  }
}

const severityConfig = {
  must_fix: {
    bg: "bg-red-500/10",
    text: "text-red-400",
    border: "border-l-red-500/60",
    label: "Must fix",
  },
  minor: {
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    border: "border-l-amber-500/60",
    label: "Minor",
  },
};

export default function IssueCard({ issue, index }: IssueCardProps) {
  const [expanded, setExpanded] = useState(issue.severity === "must_fix");
  const config = severityConfig[issue.severity];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ delay: index * 0.04, duration: 0.25 }}
      className={`
        rounded-xl border border-white/[0.06] border-l-[3px]
        bg-white/[0.02] overflow-hidden
        ${config.border}
      `}
    >
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="
          w-full flex items-center gap-3 px-4 py-3.5
          text-left hover:bg-white/[0.02] transition-colors
          cursor-pointer
        "
      >
        {/* Issue number */}
        <span
          className="
          inline-flex items-center justify-center
          w-7 h-7 rounded-full bg-white/[0.05]
          text-xs font-semibold text-white/50
          tabular-nums shrink-0
        "
        >
          {index + 1}
        </span>

        {/* Title */}
        <span className="flex-1 text-sm font-medium text-white/80 truncate">
          {issue.title}
        </span>

        {/* Severity badge */}
        <span
          className={`
            inline-flex items-center rounded-full px-2.5 py-0.5
            text-[10px] font-semibold tracking-wider uppercase select-none
            ${config.bg} ${config.text}
          `}
        >
          {config.label}
        </span>

        {/* Expand arrow */}
        <motion.div
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ duration: 0.15 }}
        >
          <ChevronRight className="h-4 w-4 text-white/20 shrink-0" />
        </motion.div>
      </button>

      {/* Expandable content */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 border-t border-white/[0.04] space-y-3">
              {/* Diff view */}
              <div className="qa-diff-view rounded-lg bg-white/[0.02] p-4 text-sm text-white/70 leading-relaxed">
                <DiffRenderer issue={issue} />
              </div>

              {/* Explanation */}
              <p className="text-[13px] text-white/40 leading-relaxed">
                {issue.explanation}
              </p>

              {/* Location buttons */}
              <div className="flex items-center gap-2 flex-wrap">
                {issue.pdf_location?.page && (
                  <span
                    className="
                    inline-flex items-center gap-1.5
                    px-3 py-1.5 rounded-lg
                    text-[11px] font-medium
                    border border-emerald-500/20
                    text-emerald-400/80 bg-emerald-500/[0.04]
                  "
                  >
                    <FileText className="h-3 w-3" />
                    PDF — Page {issue.pdf_location.page}
                    {issue.pdf_location.column &&
                      issue.pdf_location.column !== "FULL" &&
                      `, Col ${issue.pdf_location.column}`}
                  </span>
                )}

                {issue.web_location?.section && (
                  <span
                    className="
                    inline-flex items-center gap-1.5
                    px-3 py-1.5 rounded-lg
                    text-[11px] font-medium
                    border border-violet-500/20
                    text-violet-400/80 bg-violet-500/[0.04]
                    max-w-[320px] truncate
                  "
                  >
                    <Globe className="h-3 w-3 shrink-0" />
                    Website — {issue.web_location.section}
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
