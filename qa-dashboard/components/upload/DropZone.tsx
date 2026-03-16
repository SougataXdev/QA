'use client'

import { motion } from 'motion/react'
import { FileUp, FileCheck, X } from 'lucide-react'
import { useCallback, useState, useRef } from 'react'
import { useQAStore } from '@/store/useQAStore'

export default function DropZone() {
  const { pdfFile, setPdf } = useQAStore()
  const [isDragOver, setIsDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    (file: File) => {
      if (file.type === 'application/pdf' || file.name.endsWith('.pdf')) {
        setPdf(file)
      }
    },
    [setPdf]
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile]
  )

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }, [])

  const onDragLeave = useCallback(() => {
    setIsDragOver(false)
  }, [])

  const onInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
    },
    [handleFile]
  )

  const removeFile = useCallback(() => {
    const store = useQAStore.getState()
    store.reset()
    if (inputRef.current) inputRef.current.value = ''
  }, [])

  if (pdfFile) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="
          relative rounded-xl border border-green-500/20
          bg-green-500/[0.04] p-6
        "
      >
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-green-500/10">
            <FileCheck className="h-6 w-6 text-green-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-medium text-white">
              {pdfFile.name}
            </p>
            <p className="text-xs text-white/40 mt-0.5">
              {(pdfFile.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
          <button
            onClick={removeFile}
            className="
              flex h-8 w-8 items-center justify-center rounded-lg
              text-white/40 hover:text-white hover:bg-white/[0.06]
              transition-colors cursor-pointer
            "
            aria-label="Remove file"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onClick={() => inputRef.current?.click()}
      animate={{
        borderColor: isDragOver
          ? 'rgba(59, 130, 246, 0.5)'
          : 'rgba(255, 255, 255, 0.08)',
        backgroundColor: isDragOver
          ? 'rgba(59, 130, 246, 0.05)'
          : 'rgba(255, 255, 255, 0.02)',
      }}
      transition={{ duration: 0.2 }}
      className="
        relative flex flex-col items-center justify-center
        rounded-xl border-2 border-dashed p-10
        cursor-pointer min-h-[200px]
        group
      "
    >
      {/* Gradient glow on hover */}
      <div
        className="
          absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100
          transition-opacity duration-500
          bg-[radial-gradient(ellipse_at_center,rgba(59,130,246,0.06),transparent_70%)]
        "
      />

      <motion.div
        animate={isDragOver ? { scale: 1.1, y: -4 } : { scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
        className="
          flex h-14 w-14 items-center justify-center rounded-xl
          bg-white/[0.04] mb-4
        "
      >
        <FileUp className="h-6 w-6 text-white/40 group-hover:text-blue-400 transition-colors" />
      </motion.div>

      <p className="text-sm font-medium text-white/60 group-hover:text-white/80 transition-colors">
        Drop your PDF here
      </p>
      <p className="text-xs text-white/30 mt-1">
        or click to browse
      </p>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        onChange={onInputChange}
        className="hidden"
        aria-label="Upload PDF file"
      />
    </motion.div>
  )
}
