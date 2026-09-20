import React from 'react';

export const DisclaimerBanner: React.FC = () => {
  return (
    <div
      role="note"
      aria-label="Legal Disclaimer"
      className="sticky top-0 z-50 w-full border-b border-amber-200 bg-amber-50/95 px-4 py-2.5 backdrop-blur shadow-xs dark:border-amber-900/60 dark:bg-amber-950/90"
    >
      <div className="mx-auto flex max-w-5xl items-start gap-2.5 text-xs text-amber-950 dark:text-amber-200">
        <svg
          className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <p className="leading-relaxed font-medium">
          <span className="font-semibold uppercase tracking-wider text-amber-800 dark:text-amber-300">
            Important Legal Notice:
          </span>{' '}
          This tool provides information grounded in retrieved statutory text. It is not a
          substitute for professional legal advice and cannot guarantee any case outcome.
        </p>
      </div>
    </div>
  );
};
