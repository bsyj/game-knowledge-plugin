import { cn } from "@/lib/utils"
import type { ReactNode } from "react"

interface Props {
  title?: ReactNode
  actions?: ReactNode
  className?: string
  children: ReactNode
}

export default function Card({ title, actions, className, children }: Props) {
  return (
    <section className={cn("napcat-panel rounded-2xl p-4 sm:p-5", className)}>
      {(title || actions) && (
        <div className="mb-3.5 flex flex-col items-stretch justify-between gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          {title && <h2 className="w-full text-[0.9375rem] font-semibold tracking-tight text-default-900 sm:w-auto">{title}</h2>}
          {actions && <div className="flex max-w-full flex-wrap gap-2 overflow-x-auto sm:justify-end">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}
