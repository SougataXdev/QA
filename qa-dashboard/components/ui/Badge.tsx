'use client'

import { motion } from 'motion/react'

type SeverityType = 'must_fix' | 'minor' | 'all_clear'

interface BadgeProps {
  severity: SeverityType
  size?: 'sm' | 'md'
}

const config: Record<
  SeverityType,
  { bg: string; text: string; label: string }
> = {
  must_fix: {
    bg: 'bg-red-500/15',
    text: 'text-red-400',
    label: 'MUST FIX',
  },
  minor: {
    bg: 'bg-amber-500/15',
    text: 'text-amber-400',
    label: 'MINOR',
  },
  all_clear: {
    bg: 'bg-green-500/15',
    text: 'text-green-400',
    label: 'ALL CLEAR',
  },
}

const sizes = {
  sm: 'px-2 py-0.5 text-[10px]',
  md: 'px-2.5 py-1 text-xs',
}

export default function Badge({ severity, size = 'md' }: BadgeProps) {
  const { bg, text, label } = config[severity]

  return (
    <motion.span
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 500, damping: 25 }}
      className={`
        inline-flex items-center rounded-full font-semibold
        tracking-wider uppercase select-none
        ${bg} ${text} ${sizes[size]}
      `}
    >
      {label}
    </motion.span>
  )
}
