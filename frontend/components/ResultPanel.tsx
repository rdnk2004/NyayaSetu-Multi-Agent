import React, { useState } from 'react';
import { OrchestratorStageResult } from '@/types/api';
import { CitationChip } from './CitationChip';
import { DebateCard } from './DebateCard';
import { CriticReview } from './CriticReview';

interface ResultPanelProps {
  result: OrchestratorStageResult;
  onReset: () => void;
}

export const ResultPanel: React.FC<ResultPanelProps> = ({ result, onReset }) => {
  const [isVerificationOpen, setIsVerificationOpen] = useState(true);

  const hasCitations =
    (result.verified_sections && result.verified_sections.length > 0) ||
    (result.rejected_sections && result.rejected_sections.length > 0);
  const hasDebate = !!result.debate;
  const hasCritic = !!result.critic || result.critic_revision_discarded;
  const hasVerificationDetails = hasCitations || hasDebate || hasCritic;

  return (
    <div
      data-testid="result-panel"
      className="my-6 w-full rounded-2xl border-2 border-indigo-500/30 bg-gradient-to-b from-white to-slate-50/80 p-6 shadow-xl dark:border-indigo-500/30 dark:from-slate-900 dark:to-slate-950"
    >
      {/* Result Header Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm shadow-indigo-600/30">
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3"
              />
            </svg>
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              Legal Synthesis & Statutory Assessment
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Verified by multi-agent statutory grounding & debate
            </p>
          </div>
        </div>

        <button
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-2xs hover:bg-slate-50 hover:text-indigo-600 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
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
          Start New Inquiry
        </button>
      </div>

      {/* Primary Answer */}
      <div className="py-5">
        <h3 className="sr-only">Primary Legal Guidance</h3>
        <div
          data-testid="final-answer"
          className="text-base leading-relaxed text-slate-900 dark:text-slate-100 whitespace-pre-line font-normal"
        >
          {result.final_answer || 'No final answer provided.'}
        </div>
      </div>

      {/* Collapsible Verification Section */}
      {hasVerificationDetails && (
        <div className="mt-4 border-t border-slate-200/80 pt-4 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setIsVerificationOpen(!isVerificationOpen)}
            className="flex w-full items-center justify-between rounded-lg py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-600 transition hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
            aria-expanded={isVerificationOpen}
            data-testid="toggle-verification-btn"
          >
            <span className="flex items-center gap-2">
              <svg
                className="h-4 w-4 text-indigo-600 dark:text-indigo-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
              How we verified this
            </span>
            <svg
              className={`h-4 w-4 transition-transform duration-200 ${
                isVerificationOpen ? 'rotate-180' : ''
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {isVerificationOpen && (
            <div data-testid="verification-details" className="mt-3 space-y-4 pt-1">
              {/* Statutory Citations Audit */}
              {hasCitations && (
                <div className="rounded-xl border border-slate-200 bg-white/70 p-4 dark:border-slate-800 dark:bg-slate-900/60">
                  <div className="mb-2 text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Statutory Sections Cited & Audited:
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {result.verified_sections?.map((sec) => (
                      <CitationChip key={`verified-${sec}`} section={sec} status="verified" />
                    ))}
                    {result.rejected_sections?.map((sec) => (
                      <CitationChip key={`rejected-${sec}`} section={sec} status="rejected" />
                    ))}
                  </div>
                </div>
              )}

              {/* Debate Result (if present) */}
              {hasDebate && result.debate && <DebateCard debate={result.debate} />}

              {/* Critic notes and safety guardrails */}
              {hasCritic && (
                <CriticReview
                  critic={result.critic}
                  criticRevisionDiscarded={result.critic_revision_discarded}
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
