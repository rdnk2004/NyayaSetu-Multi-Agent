import React from 'react';

interface LoadingIndicatorProps {
  message?: string;
  isPipelineDeep?: boolean;
}

export const LoadingIndicator: React.FC<LoadingIndicatorProps> = ({
  message = 'Checking statutes, running an adversarial legal review, and verifying every citation - this can take up to a minute.',
  isPipelineDeep = true,
}) => {
  return (
    <div
      data-testid="pipeline-loading-indicator"
      className="my-4 flex w-full max-w-2xl items-start gap-3 rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-50/80 via-white to-indigo-50/40 p-4 shadow-2xs dark:border-indigo-900/40 dark:from-slate-900 dark:via-slate-900 dark:to-indigo-950/30"
    >
      <div className="relative flex h-8 w-8 shrink-0 items-center justify-center">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-20"></span>
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent"></div>
      </div>

      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-indigo-700 dark:text-indigo-400">
            Multi-Agent Legal Pipeline Running
          </span>
          <span className="inline-flex h-2 w-2 rounded-full bg-indigo-600 animate-pulse"></span>
        </div>
        <p className="mt-1 text-sm text-slate-700 dark:text-slate-300 leading-relaxed font-medium">
          {message}
        </p>

        {isPipelineDeep && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
              ⚡ Grounded QA
            </span>
            <span className="text-slate-400">→</span>
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
              ⚖️ Precedent Retrieval
            </span>
            <span className="text-slate-400">→</span>
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
              🛡️ Citation Audit
            </span>
            <span className="text-slate-400">→</span>
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
              ⚔️ Debate & Critic
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
