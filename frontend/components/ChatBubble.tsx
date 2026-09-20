import React from 'react';
import { StageType } from '@/types/api';

interface ChatBubbleProps {
  role: 'user' | 'assistant' | 'system';
  content: string;
  stage?: StageType;
  timestamp?: string;
}

export const ChatBubble: React.FC<ChatBubbleProps> = ({
  role,
  content,
  stage,
  timestamp,
}) => {
  if (role === 'user') {
    return (
      <div className="flex w-full justify-end" data-testid="chat-bubble-user">
        <div className="max-w-xl rounded-2xl rounded-tr-xs bg-indigo-600 px-4 py-3 text-white shadow-sm">
          <p className="text-sm leading-relaxed whitespace-pre-line font-normal">{content}</p>
          {timestamp && (
            <span className="mt-1 block text-right text-[10px] text-indigo-200">
              {timestamp}
            </span>
          )}
        </div>
      </div>
    );
  }

  if (role === 'system' || stage === 'message_too_long' || stage === 'unclear_domain') {
    const isTooLong = stage === 'message_too_long';
    return (
      <div
        className="flex w-full justify-center my-2"
        data-testid="chat-bubble-system-notice"
      >
        <div className="w-full max-w-2xl rounded-xl border border-amber-200 bg-amber-50/90 p-4 shadow-2xs dark:border-amber-900/60 dark:bg-amber-950/40">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-amber-100 p-1.5 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                {isTooLong ? 'Inquiry Needs Condensing' : 'Legal Domain Clarification Needed'}
              </h4>
              <p className="mt-1 text-sm text-amber-800 dark:text-amber-300 leading-relaxed whitespace-pre-line">
                {content}
              </p>
              <p className="mt-2 text-xs font-medium text-amber-700 dark:text-amber-400">
                💡 Please revise your inquiry below and submit again.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Assistant bubble
  return (
    <div className="flex w-full justify-start" data-testid="chat-bubble-assistant">
      <div className="flex max-w-xl items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white dark:bg-indigo-600 shadow-xs text-xs font-bold">
          NS
        </div>
        <div className="rounded-2xl rounded-tl-xs border border-slate-200 bg-white px-4 py-3 text-slate-900 shadow-2xs dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100">
          <p className="text-sm leading-relaxed whitespace-pre-line font-normal">{content}</p>
          {timestamp && (
            <span className="mt-1 block text-left text-[10px] text-slate-400">
              {timestamp}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
