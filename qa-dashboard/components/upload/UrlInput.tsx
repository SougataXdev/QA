'use client'

import { motion, AnimatePresence } from 'motion/react'
import { Check, X, Globe } from 'lucide-react'
import { useCallback, useState } from 'react'
import { useQAStore } from '@/store/useQAStore'

function isValidUrl(str: string): boolean {
  try {
    const url = new URL(str)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export default function UrlInput() {
  const { targetUrl, setTargetUrl } = useQAStore()
  const [touched, setTouched] = useState(false)

  const valid = isValidUrl(targetUrl)
  const showValidation = touched && targetUrl.length > 0

  const onBlur = useCallback(() => {
    setTouched(true)
  }, [])

  return (
    <div className="relative">
      <label
        htmlFor="target-url"
        className="block text-xs font-medium text-white/40 uppercase tracking-widest mb-2"
      >
        Target URL
      </label>

      <div className="relative">
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-white/20">
          <Globe className="h-4 w-4" />
        </div>

        <input
          id="target-url"
          type="url"
          value={targetUrl}
          onChange={(e) => setTargetUrl(e.target.value)}
          onBlur={onBlur}
          placeholder="https://example.com/page-to-compare"
          className={`
            w-full rounded-lg border bg-white/[0.03] px-10 py-3
            text-sm text-white placeholder:text-white/20
            outline-none transition-all duration-200
            focus:ring-1
            ${
              showValidation
                ? valid
                  ? 'border-green-500/30 focus:border-green-500/50 focus:ring-green-500/20'
                  : 'border-red-500/30 focus:border-red-500/50 focus:ring-red-500/20'
                : 'border-white/[0.08] focus:border-blue-500/50 focus:ring-blue-500/20'
            }
          `}
        />

        <AnimatePresence mode="wait">
          {showValidation && (
            <motion.div
              key={valid ? 'valid' : 'invalid'}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.5 }}
              transition={{ type: 'spring', stiffness: 500, damping: 25 }}
              className="absolute right-3 top-1/2 -translate-y-1/2"
            >
              {valid ? (
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500/20">
                  <Check className="h-3 w-3 text-green-400" />
                </div>
              ) : (
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-red-500/20">
                  <X className="h-3 w-3 text-red-400" />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {showValidation && !valid && (
          <motion.p
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="text-xs text-red-400/80 mt-1.5"
          >
            Enter a valid URL starting with http:// or https://
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}
