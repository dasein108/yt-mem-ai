import type { DetailedHTMLProps, HTMLAttributes } from 'react'

declare global {
  interface Window {
    electron?: { isElectron: boolean; platform: string }
  }
}

// React 19's @types/react nests the JSX namespace inside `declare namespace React`
// (exported as `React.JSX`, re-exported by `react/jsx-runtime`) rather than a global
// `JSX` namespace. Augmenting the global namespace has no effect on JSX resolution
// under `jsx: "react-jsx"`, so we augment the `react` module's namespace instead.
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      webview: DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
        src?: string
        allowpopups?: string
      }
    }
  }
}

export {}
