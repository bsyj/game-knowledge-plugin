import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatNumber(n: number): string {
  return n.toLocaleString()
}

export function formatDate(ts: number | string | undefined): string {
  if (ts == null || ts === "") return "-"
  const numeric = typeof ts === "number" ? ts : Number(ts)
  const value = Number.isFinite(numeric)
    ? numeric > 0 && numeric < 1_000_000_000_000
      ? numeric * 1000
      : numeric
    : ts
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return "-"
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "…" : s
}
