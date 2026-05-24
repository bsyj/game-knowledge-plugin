import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react-swc'
import path from 'path'
import type { Plugin } from 'vite'
import { defineConfig } from 'vite'

function unwrapCssCascadeLayers(): Plugin {
  const versionFor = (text: string) => {
    let hash = 2166136261
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i)
      hash = Math.imul(hash, 16777619)
    }
    return (hash >>> 0).toString(36)
  }

  const unwrapLayerBlocks = (css: string) => {
    let output = ''
    let index = 0
    while (index < css.length) {
      if (!css.startsWith('@layer ', index)) {
        output += css[index]
        index += 1
        continue
      }

      const headerEnd = css.indexOf('{', index)
      const semicolon = css.indexOf(';', index)
      if (semicolon !== -1 && (headerEnd === -1 || semicolon < headerEnd)) {
        index = semicolon + 1
        continue
      }
      if (headerEnd === -1) {
        output += css.slice(index)
        break
      }

      let depth = 0
      let cursor = headerEnd
      for (; cursor < css.length; cursor += 1) {
        const char = css[cursor]
        if (char === '{') depth += 1
        if (char === '}') {
          depth -= 1
          if (depth === 0) break
        }
      }

      output += css.slice(headerEnd + 1, cursor)
      index = cursor + 1
    }
    return output
  }

  return {
    name: 'unwrap-css-cascade-layers-for-legacy-webview',
    apply: 'build',
    enforce: 'post',
    generateBundle(_, bundle) {
      const cssVersions = new Map<string, string>()
      for (const asset of Object.values(bundle)) {
        if (asset.type === 'asset' && asset.fileName.endsWith('.css') && typeof asset.source === 'string') {
          asset.source = unwrapLayerBlocks(asset.source)
          cssVersions.set(asset.fileName, versionFor(asset.source))
        }
      }

      for (const asset of Object.values(bundle)) {
        if (asset.type !== 'asset' || !asset.fileName.endsWith('.html') || typeof asset.source !== 'string') continue
        let html = asset.source
        for (const [fileName, version] of cssVersions.entries()) {
          html = html.replaceAll(fileName, `${fileName}?v=${version}`)
        }
        asset.source = html
      }
    },
  }
}

export default defineConfig({
  base: './',
  plugins: [tailwindcss(), react(), unwrapCssCascadeLayers()],
  server: {
    port: 5180,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5810',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks: {
          'heroui': ['@heroui/react', 'framer-motion'],
          'icons': ['lucide-react'],
          'utils': ['axios', 'clsx', 'tailwind-merge'],
        },
      },
    },
  },
})
