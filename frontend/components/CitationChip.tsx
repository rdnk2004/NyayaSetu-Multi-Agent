import React from 'react';

interface CitationChipProps {
  section: string;
  status: 'verified' | 'rejected';
}

export const CitationChip: React.FC<CitationChipProps> = ({ section, status }) => {
  const isVerified = status === 'verified';

  if (isVerified) {
    return (
      <span
        data-testid={`citation-chip-verified-${section}`}
        className="inline-flex items-center gap-1.5 rounded-md border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 shadow-xs dark:border-emerald-700/60 dark:bg-emerald-950/50 dark:text-emerald-300"
      >
        <svg
          className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2.5"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        <span className="font-semibold">{section}</span>
        <span className="text-[10px] uppercase tracking-wide opacity-80">(Verified)</span>
      </span>
    );
  }

  return (
    <span
      data-testid={`citation-chip-rejected-${section}`}
      className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-rose-300 bg-rose-50/80 px-2.5 py-1 text-xs font-medium text-rose-800 shadow-xs dark:border-rose-700/60 dark:bg-rose-950/40 dark:text-rose-300"
    >
      <svg
        className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="2.5"
        aria-hidden="true"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
      <span className="line-through decoration-rose-500 font-semibold">{section}</span>
      <span className="text-[10px] uppercase tracking-wide text-rose-700 dark:text-rose-400">
        (Excluded / Unverified)
      </span>
    </span>
  );
};
