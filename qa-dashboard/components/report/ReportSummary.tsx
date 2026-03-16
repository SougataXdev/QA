"use client";

import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { Space, DollarSign, FileX, Minus } from "lucide-react";
import type { QASummary, QAIssueType, QAFilterOption } from "@/lib/types";

interface ReportSummaryProps {
  summary: QASummary;
  activeFilter: QAFilterOption;
  onFilter: (filter: QAFilterOption) => void;
}

function AnimatedCount({ target, delay }: { target: number; delay: number }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const timeout = setTimeout(() => {
      const duration = 800;
      const startTime = performance.now();

      const tick = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        setCount(Math.round(target * eased));
        if (progress < 1) requestAnimationFrame(tick);
      };

      requestAnimationFrame(tick);
    }, delay);

    return () => clearTimeout(timeout);
  }, [target, delay]);

  return <span>{count}</span>;
}

const cards: {
  key: QAIssueType;
  label: string;
  icon: typeof Space;
  summaryKey: keyof QASummary;
  severity: "must_fix" | "minor";
}[] = [
  {
    key: "extra_whitespace",
    label: "Extra Spaces",
    icon: Space,
    summaryKey: "extra_whitespace_count",
    severity: "minor",
  },
  {
    key: "currency_mismatch",
    label: "Currency Errors",
    icon: DollarSign,
    summaryKey: "currency_mismatch_count",
    severity: "must_fix",
  },
  {
    key: "missing_word",
    label: "Missing Words",
    icon: FileX,
    summaryKey: "missing_word_count",
    severity: "must_fix",
  },
  {
    key: "missing_paragraph",
    label: "Missing Sections",
    icon: Minus,
    summaryKey: "missing_paragraph_count",
    severity: "must_fix",
  },
];

export default function ReportSummary({
  summary,
  activeFilter,
  onFilter,
}: ReportSummaryProps) {
  return (
    <div className="grid grid-cols-4 gap-3">
      {cards.map((c, i) => {
        const Icon = c.icon;
        const value = summary[c.summaryKey];
        const isActive = activeFilter === c.key;
        const isMustFix = c.severity === "must_fix";

        const countColor =
          value === 0
            ? "text-white/20"
            : isMustFix
              ? "text-red-400"
              : "text-amber-400";

        const borderColor = isActive
          ? isMustFix
            ? "border-red-500/40"
            : "border-amber-500/40"
          : "border-white/[0.06]";

        const bgColor = isActive
          ? isMustFix
            ? "bg-red-500/[0.06]"
            : "bg-amber-500/[0.06]"
          : "bg-white/[0.02]";

        return (
          <motion.button
            key={c.key}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            onClick={() => onFilter(isActive ? "ALL" : c.key)}
            className={`
              relative rounded-xl border ${borderColor} ${bgColor}
              px-3 py-4 flex flex-col items-center gap-2
              cursor-pointer transition-all duration-200
              hover:border-white/[0.12] hover:bg-white/[0.04]
              focus-visible:outline-none focus-visible:ring-2
              focus-visible:ring-blue-500/50 focus-visible:ring-offset-2
              focus-visible:ring-offset-[#0a0a0a]
            `}
          >
            <Icon
              className={`h-3.5 w-3.5 ${
                value === 0
                  ? "text-white/10"
                  : isMustFix
                    ? "text-red-400/50"
                    : "text-amber-400/50"
              }`}
            />
            <span className={`text-2xl font-light tabular-nums ${countColor}`}>
              <AnimatedCount target={value} delay={i * 80} />
            </span>
            <span className="text-[10px] text-white/30 uppercase tracking-widest leading-tight text-center">
              {c.label}
            </span>

            {/* Active indicator dot */}
            {isActive && (
              <motion.div
                layoutId="activeCardDot"
                className={`absolute -bottom-1 left-1/2 -translate-x-1/2 h-1 w-6 rounded-full ${
                  isMustFix ? "bg-red-400" : "bg-amber-400"
                }`}
                transition={{
                  type: "spring",
                  stiffness: 400,
                  damping: 30,
                }}
              />
            )}
          </motion.button>
        );
      })}
    </div>
  );
}
