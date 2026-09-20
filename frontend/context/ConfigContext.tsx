'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { ConfigResponse } from '@/types/api';

interface ConfigContextType {
  backendUrl: string | null;
  isLoading: boolean;
  error: string | null;
  retry: () => void;
}

const ConfigContext = createContext<ConfigContextType>({
  backendUrl: null,
  isLoading: true,
  error: null,
  retry: () => {},
});

export const ConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [backendUrl, setBackendUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/config');
      if (!res.ok) {
        throw new Error(`Failed to load app configuration (${res.status} ${res.statusText})`);
      }
      const data: ConfigResponse = await res.json();
      if (!data.backendUrl) {
        throw new Error('Invalid configuration received from server: backendUrl is missing');
      }
      setBackendUrl(data.backendUrl);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown configuration error occurred';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  return (
    <ConfigContext.Provider value={{ backendUrl, isLoading, error, retry: fetchConfig }}>
      {isLoading ? (
        <div className="flex min-h-[60vh] flex-col items-center justify-center p-6 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" data-testid="config-loading-spinner"></div>
          <p className="mt-4 text-sm font-medium text-slate-600 dark:text-slate-400">
            Initializing NyayaSetu configuration...
          </p>
        </div>
      ) : error ? (
        <div className="flex min-h-[60vh] flex-col items-center justify-center p-6 text-center" data-testid="config-error-container">
          <div className="max-w-md rounded-xl border border-red-200 bg-red-50 p-6 shadow-sm dark:border-red-900/50 dark:bg-red-950/40">
            <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600 dark:bg-red-900/50 dark:text-red-300">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-red-800 dark:text-red-200">
              Configuration Error
            </h3>
            <p className="mt-2 text-sm text-red-700 dark:text-red-300">
              {error}
            </p>
            <p className="mt-1 text-xs text-red-600/80 dark:text-red-400/80">
              The backend service endpoint could not be resolved. Please verify the environment settings.
            </p>
            <button
              onClick={fetchConfig}
              className="mt-5 inline-flex items-center rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
            >
              Retry Connection
            </button>
          </div>
        </div>
      ) : (
        children
      )}
    </ConfigContext.Provider>
  );
};

export const useConfig = () => useContext(ConfigContext);
