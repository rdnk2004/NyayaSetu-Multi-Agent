import React, { useState } from 'react';

interface IntakeInputProps {
  fieldKey: string;
  onSubmit: (fieldKey: string, answer: string) => void;
  isLoading: boolean;
}

export const IntakeInput: React.FC<IntakeInputProps> = ({
  fieldKey,
  onSubmit,
  isLoading,
}) => {
  const [answer, setAnswer] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim() || isLoading) return;
    onSubmit(fieldKey, answer.trim());
    setAnswer('');
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-3 flex w-full items-center gap-2 max-w-xl ml-11"
      data-testid="intake-form"
    >
      <div className="relative flex-1">
        <label htmlFor="intake-answer-input" className="sr-only">
          Your Answer
        </label>
        <input
          id="intake-answer-input"
          type="text"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Type your response here..."
          disabled={isLoading}
          className="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-2xs placeholder:text-slate-400 focus:border-indigo-600 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-50 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          autoFocus
        />
      </div>
      <button
        type="submit"
        disabled={!answer.trim() || isLoading}
        data-testid="submit-intake-answer-btn"
        className="inline-flex items-center justify-center rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-indigo-300 dark:disabled:bg-indigo-900/50"
      >
        {isLoading ? (
          <span className="flex items-center gap-1.5">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
            <span>Sending</span>
          </span>
        ) : (
          <span>Submit</span>
        )}
      </button>
    </form>
  );
};
