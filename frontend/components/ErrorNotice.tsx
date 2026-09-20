import React from 'react';

interface ErrorNoticeProps {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}

export const ErrorNotice: React.FC<ErrorNoticeProps> = ({
  message,
  onRetry,
  onDismiss,
}) => {
  return (
    <div
      role="alert"
      data-testid="error-notice"
      className="my-3 w-full max-w-2xl rounded-xl border border-rose-200 bg-rose-50/90 p-4 shadow-xs dark:border-rose-900/60 dark:bg-rose-950/40"
    >
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-rose-100 p-1.5 text-rose-600 dark:bg-rose-900/50 dark:text-rose-300">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-rose-900 dark:text-rose-200">
            Notice
          </h4>
          <p className="mt-1 text-sm text-rose-800 dark:text-rose-300 leading-relaxed font-normal">
            {message}
          </p>
          <div className="mt-3 flex items-center gap-3">
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                data-testid="error-retry-btn"
                className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white shadow-2xs transition hover:bg-rose-700 focus:outline-hidden focus:ring-2 focus:ring-rose-500 focus:ring-offset-2"
              >
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                Retry
              </button>
            )}
            {onDismiss && (
              <button
                type="button"
                onClick={onDismiss}
                className="text-xs font-medium text-rose-700 hover:text-rose-900 dark:text-rose-400 dark:hover:text-rose-200"
              >
                Dismiss
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
