'use client'

import { AnimatePresence, motion } from 'motion/react'
import { type ReactNode, useState } from 'react'

interface TooltipProps {
  content: string
  children: ReactNode
  side?: 'top' | 'bottom'
}

export default function Tooltip({
  content,
  children,
  side = 'top',
}: TooltipProps) {
  const [visible, setVisible] = useState(false)

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0, y: side === 'top' ? 4 : -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: side === 'top' ? 4 : -4 }}
            transition={{ duration: 0.15 }}
            className={`
              absolute z-50 whitespace-nowrap
              rounded-md bg-white/10 backdrop-blur-md
              px-2.5 py-1.5 text-xs text-white/80
              pointer-events-none
              ${
                side === 'top'
                  ? 'bottom-full mb-2 left-1/2 -translate-x-1/2'
                  : 'top-full mt-2 left-1/2 -translate-x-1/2'
              }
            `}
          >
            {content}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
