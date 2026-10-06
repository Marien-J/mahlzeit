import { useEffect, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/** A bottom sheet on phones, a centred dialog on wide screens. Closes on Escape and backdrop. */
export function Sheet({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog || dialog.open) return
    // Older browsers (and jsdom) lack showModal; an open non-modal dialog still works.
    if (typeof dialog.showModal === 'function') dialog.showModal()
    else dialog.setAttribute('open', '')
  }, [])
  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
    >
      <div className="sheet-body">
        <header className="row spread">
          <h2>{title}</h2>
          <button type="button" className="icon" aria-label={t('common.close')} onClick={onClose}>
            ×
          </button>
        </header>
        {children}
      </div>
    </dialog>
  )
}
