'use client'

import { motion } from 'motion/react'
import type { ReactNode, MouseEventHandler } from 'react'

interface ButtonProps {
  children: ReactNode
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  pulse?: boolean
  loading?: boolean
  disabled?: boolean
  className?: string
  onClick?: MouseEventHandler<HTMLButtonElement>
  type?: 'button' | 'submit' | 'reset'
}

const variants = {
  primary:
    'bg-blue-600 text-white hover:bg-blue-500 disabled:bg-white/[0.06] disabled:text-white/30',
  secondary:
    'bg-white/[0.06] text-white/80 hover:bg-white/[0.1] hover:text-white disabled:text-white/30',
  ghost:
    'bg-transparent text-white/60 hover:bg-white/[0.06] hover:text-white disabled:text-white/30',
  danger:
    'bg-red-600/20 text-red-400 hover:bg-red-600/30 disabled:text-white/30',
}

const sizes = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
}

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  pulse = false,
  loading = false,
  disabled,
  className = '',
  onClick,
  type = 'button',
}: ButtonProps) {
  const isDisabled = disabled || loading

  return (
    <motion.button
      type={type}
      whileHover={isDisabled ? undefined : { scale: 1.02 }}
      whileTap={isDisabled ? undefined : { scale: 0.98 }}
      animate={
        pulse && !isDisabled
          ? {
              scale: [1, 1.02, 1],
              transition: { duration: 2, repeat: Infinity, ease: 'easeInOut' },
            }
          : undefined
      }
      disabled={isDisabled}
      onClick={onClick}
      className={`
        relative inline-flex items-center justify-center gap-2
        rounded-lg font-medium
        transition-colors duration-200
        cursor-pointer
        disabled:cursor-not-allowed
        ${variants[variant]}
        ${sizes[size]}
        ${className}
      `}
    >
      {loading && (
        <svg
          className="h-4 w-4 animate-spin"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      )}
      {children}
    </motion.button>
  )
}
