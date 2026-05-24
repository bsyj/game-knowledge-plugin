import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface Props {
  className?: string
  size?: number
}

export default function Loading({ className, size = 20 }: Props) {
  return (
    <div className={cn("flex items-center justify-center py-12", className)}>
      <Loader2 className="animate-spin text-default-500" size={size} />
    </div>
  )
}