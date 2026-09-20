import React from 'react';
import { DebateResult } from '@/types/api';

interface DebateCardProps {
  debate: DebateResult;
}

export const DebateCard: React.FC<DebateCardProps> = ({ debate }) => {
  const supportedSideText = debate.clearly_supported_side
    ? debate.clearly_supported_side === 'plaintiff'
      ? 'Plaintiff / Aggrieved Party'
      : 'Defense / Counterparty'
    : 'Neither side clearly supported';

  return (
    <div
      data-testid="debate-card"
      className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-900/60"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 pb-3 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Adversarial Legal Review & Debate
          </span>
        </div>
        <div>
          {debate.is_grey_zone ? (
            <span
              data-testid="debate-status-grey-zone"
              className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-100/90 px-3 py-0.5 text-xs font-semibold text-amber-900 dark:border-amber-700 dark:bg-amber-950/70 dark:text-amber-300"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse"></span>
              Contested (Grey Zone - Judicial Discretion Expected)
            </span>
          ) : (
            <span
              data-testid="debate-status-clear-cut"
              className="inline-flex items-center gap-1.5 rounded-full border border-blue-300 bg-blue-100/90 px-3 py-0.5 text-xs font-semibold text-blue-900 dark:border-blue-700 dark:bg-blue-950/70 dark:text-blue-300"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500"></span>
              Clear-cut (Direct Statutory Precedent)
            </span>
          )}
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          Judicial Assessment:
        </div>
        <p className="text-sm leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-line">
          {debate.judge_summary}
        </p>
        <div className="mt-2 text-xs text-slate-600 dark:text-slate-400">
          <span className="font-medium text-slate-700 dark:text-slate-300">
            Supported side on current facts:
          </span>{' '}
          <span className="font-semibold text-indigo-700 dark:text-indigo-400">
            {supportedSideText}
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 text-xs">
        {/* Plaintiff argument */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
          <div className="font-semibold text-slate-900 dark:text-slate-100 mb-1 flex items-center justify-between">
            <span>Aggrieved / Plaintiff Position</span>
          </div>
          <p className="text-slate-700 dark:text-slate-300 leading-normal">
            {debate.plaintiff_argument || 'No specific plaintiff argument recorded.'}
          </p>
          {debate.plaintiff_cited_sections?.length > 0 && (
            <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
              Cited: {debate.plaintiff_cited_sections.join(', ')}
            </div>
          )}
        </div>

        {/* Defense argument */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
          <div className="font-semibold text-slate-900 dark:text-slate-100 mb-1 flex items-center justify-between">
            <span>Opposing / Defense Position</span>
          </div>
          <p className="text-slate-700 dark:text-slate-300 leading-normal">
            {debate.defense_argument || 'No specific defense argument recorded.'}
          </p>
          {debate.defense_cited_sections?.length > 0 && (
            <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
              Cited: {debate.defense_cited_sections.join(', ')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
