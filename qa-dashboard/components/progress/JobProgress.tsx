'use client'

import { motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import Button from '@/components/ui/Button'
import { useQAStore } from '@/store/useQAStore'

function AnimatedCounter({ value }: { value: number }) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    const duration = 800
    const start = display
    const delta = value - start
    const startTime = performance.now()

    const tick = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      // Ease out: 1 - (1 - t)^3
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(Math.round(start + delta * eased))

      if (progress < 1) {
        requestAnimationFrame(tick)
      }
    }

    requestAnimationFrame(tick)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return <span>{display}</span>
}

export default function JobProgress() {
  const { progress, progressMessage, jobStatus, reset } = useQAStore()

  const isFailed = jobStatus === 'FAILED'

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="flex flex-col items-center justify-center py-20 px-8"
    >
      {/* Pulsing ring behind the number */}
      <div className="relative flex items-center justify-center mb-8">
        {!isFailed && (
          <motion.div
            className="absolute h-36 w-36 rounded-full border border-blue-500/20"
            animate={{
              scale: [1, 1.15, 1],
              opacity: [0.3, 0.1, 0.3],
            }}
            transition={{
              duration: 2.5,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
          />
        )}

        <motion.div
          className="absolute h-28 w-28 rounded-full border border-blue-500/10"
          animate={
            isFailed
              ? { borderColor: 'rgba(239,68,68,0.2)' }
              : {
                  scale: [1, 1.08, 1],
                  opacity: [0.2, 0.05, 0.2],
                }
          }
          transition={{
            duration: 3,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: 0.5,
          }}
        />

        {/* Large percentage number */}
        <div
          className={`
            relative text-6xl font-light tabular-nums
            ${isFailed ? 'text-red-400' : 'text-white'}
          `}
        >
          <AnimatedCounter value={progress} />
          <span className="text-2xl text-white/30 ml-1">%</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="w-full max-w-md h-1.5 rounded-full bg-white/[0.06] overflow-hidden mb-4">
        <motion.div
          className={`
            h-full rounded-full
            ${isFailed ? 'bg-red-500' : 'bg-blue-500'}
          `}
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{
            type: 'spring',
            stiffness: 60,
            damping: 20,
          }}
        />
      </div>

      {/* Status message */}
      <div className="flex items-center gap-2 mb-6">
        {!isFailed && (
          <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin" />
        )}
        <motion.p
          key={progressMessage}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className={`
            text-sm
            ${isFailed ? 'text-red-400' : 'text-white/50'}
          `}
        >
          {progressMessage || (isFailed ? 'Job failed' : 'Processing...')}
        </motion.p>
      </div>

      {/* Cancel / Retry */}
      <Button
        variant={isFailed ? 'danger' : 'ghost'}
        size="sm"
        onClick={reset}
      >
        {isFailed ? 'Start Over' : 'Cancel'}
      </Button>
    </motion.div>
  )
}
