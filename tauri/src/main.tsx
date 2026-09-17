import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
// import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import App from '@/App';
// Import CSS from app directory using alias so Tailwind can scan the source files
import '@/index.css';
import { PlatformProvider } from '@/platform/PlatformContext';
import { tauriPlatform } from './platform';

const LOG_KEY = 'voicebox-desktop-boot-log';
const MAX_LOG_LINES = 250;

type ConsoleMethod = 'log' | 'info' | 'warn' | 'error';

function normalizeLogArg(arg: unknown): string {
  if (arg instanceof Error) {
    return `${arg.name}: ${arg.message}${arg.stack ? `\n${arg.stack}` : ''}`;
  }

  if (typeof arg === 'string') {
    return arg;
  }

  try {
    return JSON.stringify(arg);
  } catch {
    return String(arg);
  }
}

function appendBootLog(level: string, args: unknown[]) {
  try {
    const line = `[${new Date().toISOString()}] [${level}] ${args.map(normalizeLogArg).join(' ')}`;
    const raw = window.localStorage.getItem(LOG_KEY);
    const lines = raw ? JSON.parse(raw) as string[] : [];
    lines.push(line);
    window.localStorage.setItem(LOG_KEY, JSON.stringify(lines.slice(-MAX_LOG_LINES)));
  } catch {
    // Logging must never block app startup.
  }
}

function installDesktopBootDiagnostics() {
  if (typeof window === 'undefined') return;

  window.__voiceboxGetBootLog = () => {
    try {
      return JSON.parse(window.localStorage.getItem(LOG_KEY) || '[]') as string[];
    } catch {
      return [];
    }
  };

  window.__voiceboxClearBootLog = () => {
    try {
      window.localStorage.removeItem(LOG_KEY);
    } catch {
      // noop
    }
  };

  (['log', 'info', 'warn', 'error'] as ConsoleMethod[]).forEach((method) => {
    const original = console[method].bind(console);
    console[method] = (...args: unknown[]) => {
      appendBootLog(method, args);
      original(...args);
    };
  });

  window.addEventListener('error', (event) => {
    appendBootLog('window.error', [
      event.message,
      event.filename,
      `${event.lineno}:${event.colno}`,
      event.error,
    ]);
  });

  window.addEventListener('unhandledrejection', (event) => {
    appendBootLog('unhandledrejection', [event.reason]);
  });

  console.info('[boot] Voicebox desktop diagnostics installed', {
    href: window.location.href,
    userAgent: navigator.userAgent,
    env: {
      prod: import.meta.env.PROD,
      dev: import.meta.env.DEV,
      mode: import.meta.env.MODE,
    },
  });
}

installDesktopBootDiagnostics();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      gcTime: 1000 * 60 * 10, // 10 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const rootElement = document.getElementById('root');

if (!rootElement) {
  console.error('[boot] Missing #root element; React cannot mount');
  throw new Error('Missing #root element');
}

console.info('[boot] Mounting Voicebox desktop React app');

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <PlatformProvider platform={tauriPlatform}>
        <App />
        {/* <ReactQueryDevtools initialIsOpen={false} /> */}
      </PlatformProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
