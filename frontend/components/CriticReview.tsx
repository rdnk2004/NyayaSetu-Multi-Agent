import React from 'react';
import { CriticResult } from '@/types/api';

interface CriticReviewProps {
  critic: CriticResult | null;
  criticRevisionDiscarded: boolean;
}

export const CriticReview: React.FC<CriticReviewProps> = ({
  critic,
  criticRevisionDiscarded,
}) => {
  if (!critic && !criticRevisionDiscarded) {
    return null;
  }

  return (
    <div className="mt-4 space-y-3">
      {/* Safety Reassurance Note when an ungrounded revision was discarded */}
      {criticRevisionDiscarded && (
        <div
          data-testid="critic-discarded-note"
          className="rounded-xl border border-teal-200 bg-teal-50/90 p-4 text-xs dark:border-teal-900/60 dark:bg-teal-950/40"
        >
          <div className="flex items-start gap-2.5">
            <svg
              className="h-4 w-4 shrink-0 text-teal-600 dark:text-teal-400 mt-0.5"
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
            <div>
              <span className="font-semibold text-teal-900 dark:text-teal-200">
                Statutory Verification Guardrail Active:
              </span>{' '}
              <span className="text-teal-800 dark:text-teal-300">
                Our verification system caught an unverifiable claim in an earlier draft of this
                answer and removed it before showing you this result.
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Critic Transparency Note if approved === false and critique_notes provided */}
      {critic && !critic.approved && critic.critique_notes && (
        <div
          data-testid="critic-notes-panel"
          className="rounded-xl border border-indigo-200 bg-indigo-50/70 p-4 text-xs dark:border-indigo-900/50 dark:bg-indigo-950/40"
        >
          <div className="flex items-start gap-2.5">
            <svg
              className="h-4 w-4 shrink-0 text-indigo-600 dark:text-indigo-400 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div>
              <div className="font-semibold text-indigo-900 dark:text-indigo-200 mb-1">
                Quality Review & Refinement Notes
              </div>
              <p className="text-indigo-800 dark:text-indigo-300 leading-relaxed">
                {critic.critique_notes}
              </p>
              <p className="mt-1 text-[11px] text-indigo-600/80 dark:text-indigo-400/80">
                The preliminary synthesis was audited and adjusted to ensure exact statutory alignment and balanced analysis.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
