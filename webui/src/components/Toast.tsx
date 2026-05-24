import { createContext, useCallback, useContext, useState, type ReactNode } from "react"
import { cn } from "@/lib/utils"

interface ToastItem {
  id: number
  message: string
  type: "success" | "error" | "info"
  leaving: boolean
}

interface ToastCtx {
  toast: (msg: string, type?: "success" | "error" | "info") => void
}

const Ctx = createContext<ToastCtx>({ toast: () => {} })

let _id = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const toast = useCallback((message: string, type: "success" | "error" | "info" = "info") => {
    const id = ++_id
    setItems((prev) => [...prev, { id, message, type, leaving: false }])
    setTimeout(() => {
      setItems((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)))
      setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 300)
    }, 3000)
  }, [])

  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div className="fixed inset-x-3 top-3 z-50 flex flex-col gap-2 sm:inset-x-auto sm:right-4 sm:top-4">
        {items.map((item) => (
          <div
            key={item.id}
            className={cn(
              "w-full rounded-xl px-4 py-2.5 text-sm font-medium shadow-lg sm:max-w-sm animate-[toast-in_0.2s_ease-out]",
              item.leaving && "animate-[toast-out_0.3s_ease-in_forwards]",
              item.type === "success" && "bg-success text-success-foreground",
              item.type === "error" && "bg-destructive text-destructive-foreground",
              item.type === "info" && "bg-secondary text-secondary-foreground",
            )}
          >
            {item.message}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

export function useToast() {
  return useContext(Ctx)
}
