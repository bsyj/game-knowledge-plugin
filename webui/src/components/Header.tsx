import { Gamepad2 } from "lucide-react"

export default function Header() {
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-white/10 bg-content1/60 px-4 backdrop-blur-md">
      <h1 className="flex items-center text-lg font-semibold tracking-tight">
        <Gamepad2 className="mr-2 h-5 w-5 text-primary" />
        GameKnowledge
        <span className="ml-2 text-xs font-normal text-default-500">游戏知识库</span>
      </h1>
    </header>
  )
}
