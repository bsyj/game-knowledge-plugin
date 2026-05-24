import { cn } from "@/lib/utils"
import type { ButtonHTMLAttributes } from "react"

type Variant = "primary" | "secondary" | "outline" | "ghost" | "destructive" | "success"

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: "default" | "sm"
}

const base = "inline-flex min-w-0 touch-manipulation items-center justify-center gap-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"

const sizes: Record<string, string> = {
  default: "h-9 px-4",
  sm: "h-7 px-2.5 text-[0.7rem] rounded-xl",
}

const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground shadow-sm shadow-primary/20 hover:bg-primary/90",
  secondary: "bg-secondary/90 text-secondary-foreground shadow-sm shadow-secondary/20 hover:bg-secondary",
  outline: "border border-[var(--gk-input-border)] bg-[var(--gk-input-bg)] text-default-700 shadow-sm hover:bg-default-100/70 hover:text-default-900",
  ghost: "bg-transparent text-default-500 hover:bg-default-100/60 hover:text-default-900",
  destructive: "bg-destructive text-destructive-foreground shadow-sm shadow-destructive/20 hover:bg-destructive/90",
  success: "bg-success text-success-foreground shadow-sm shadow-success/20 hover:bg-success/90",
}

export default function Button({ variant = "primary", size = "default", className, children, ...props }: Props) {
  return (
    <button className={cn(base, sizes[size], variants[variant], className)} {...props}>
      {children}
    </button>
  )
}
