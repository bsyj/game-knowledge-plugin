import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import "./index.css"

const savedTheme = localStorage.getItem("gk-webui-theme") === "light" ? "light" : "dark"
document.documentElement.dataset.theme = savedTheme
document.documentElement.classList.remove(savedTheme === "dark" ? "light" : "dark")
document.documentElement.classList.add(savedTheme)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
