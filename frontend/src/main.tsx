import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router'

import { App } from './App'
import { SpeechProvider } from './speech/SpeechProvider'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SpeechProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </SpeechProvider>
    </QueryClientProvider>
  </StrictMode>,
)
