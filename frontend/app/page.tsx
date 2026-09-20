'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useConfig } from '@/context/ConfigContext';
import {
  ChatMessage,
  OrchestratorStageResult,
  SessionStartResponse,
  StageType,
} from '@/types/api';
import { ChatBubble } from '@/components/ChatBubble';
import { IntakeInput } from '@/components/IntakeInput';
import { ResultPanel } from '@/components/ResultPanel';
import { LoadingIndicator } from '@/components/LoadingIndicator';
import { ErrorNotice } from '@/components/ErrorNotice';

export default function HomePage() {
  const { backendUrl } = useConfig();

  // Conversation & session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentStage, setCurrentStage] = useState<StageType | null>(null);
  const [lastStageResult, setLastStageResult] = useState<OrchestratorStageResult | null>(null);

  // Input states
  const [initialMessage, setInitialMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<(() => Promise<void>) | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (typeof chatEndRef.current?.scrollIntoView === 'function') {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, currentStage, errorMessage]);

  // Helper to handle API fetch failures with friendly messages
  const handleFetchError = (err: unknown, actionRetry?: () => Promise<void>) => {
    let friendlyText = "Couldn't reach the server - check your connection and try again.";
    if (err instanceof Error) {
      if (err.message.includes('500') || err.message.includes('server error')) {
        friendlyText = 'Something went wrong on our end - please try again.';
      } else if (err.message.includes('404')) {
        friendlyText = 'Session expired or not found. Please start a new inquiry.';
      } else if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
        friendlyText = "Couldn't reach the server - check your connection and try again.";
      }
    }
    setErrorMessage(friendlyText);
    if (actionRetry) {
      setLastAction(() => actionRetry);
    }
  };

  // Reset conversation to initial state
  const handleReset = () => {
    setSessionId(null);
    setMessages([]);
    setCurrentStage(null);
    setLastStageResult(null);
    setInitialMessage('');
    setErrorMessage(null);
    setLastAction(null);
    setIsLoading(false);
  };

  // 1. Submit Initial Message -> POST /api/sessions
  const handleStartSession = async (overrideMessage?: string) => {
    const textToSend = (overrideMessage || initialMessage).trim();
    if (!textToSend || !backendUrl || isLoading) return;

    setErrorMessage(null);
    setIsLoading(true);
    setLoadingMessage('Understanding legal issue and structuring facts...');

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Add user message to transcript
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp,
    };
    setMessages((prev) => [...prev, userMsg]);

    const performRequest = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: textToSend }),
        });

        if (!res.ok) {
          throw new Error(`Server returned status ${res.status}`);
        }

        const data: SessionStartResponse = await res.json();
        setSessionId(data.session_id);
        setCurrentStage(data.stage);
        setLastStageResult(data);

        processStageResponse(data);
      } catch (err) {
        handleFetchError(err, () => handleStartSession(textToSend));
      } finally {
        setIsLoading(false);
      }
    };

    await performRequest();
  };

  // Process any stage result received from the API
  const processStageResponse = (data: OrchestratorStageResult) => {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (data.stage === 'message_too_long' || data.stage === 'unclear_domain') {
      const noticeContent =
        data.message ||
        (data.stage === 'message_too_long'
          ? 'Your message is too detailed for initial intake. Please summarize the core dispute in 1-2 paragraphs.'
          : 'Could not detect a supported legal domain. Please specify the legal topic (e.g., tenancy, employment, consumer, criminal, property).');

      setMessages((prev) => [
        ...prev,
        {
          id: `sys-${Date.now()}`,
          role: 'system',
          content: noticeContent,
          stage: data.stage,
          timestamp,
        },
      ]);
    } else if (data.stage === 'intake_question') {
      if (data.question_text) {
        setMessages((prev) => [
          ...prev,
          {
            id: `asst-${Date.now()}`,
            role: 'assistant',
            content: data.question_text!,
            stage: data.stage,
            timestamp,
          },
        ]);
      }
    } else if (data.stage === 'final_check_gap') {
      const gapNotice =
        data.gap ||
        'Some relevant case details could not be determined, but we can still proceed with standard statutory grounding.';
      setMessages((prev) => [
        ...prev,
        {
          id: `gap-${Date.now()}`,
          role: 'assistant',
          content: gapNotice,
          stage: data.stage,
          timestamp,
        },
      ]);
    } else if (data.stage === 'complete') {
      // Completed terminal state is rendered by ResultPanel
    }
  };

  // 2. Submit Intake Answer -> POST /api/sessions/{id}/answer
  const handleAnswerQuestion = async (fieldKey: string, answer: string) => {
    if (!sessionId || !backendUrl || isLoading) return;

    setErrorMessage(null);
    setIsLoading(true);
    setLoadingMessage(
      'Checking statutes, running an adversarial legal review, and verifying every citation - this can take up to a minute.'
    );

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Append user answer bubble to conversation
    setMessages((prev) => [
      ...prev,
      {
        id: `user-ans-${Date.now()}`,
        role: 'user',
        content: answer,
        timestamp,
      },
    ]);

    const performRequest = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/sessions/${sessionId}/answer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ field_key: fieldKey, answer }),
        });

        if (!res.ok) {
          throw new Error(`Server returned status ${res.status}`);
        }

        const data: OrchestratorStageResult = await res.json();
        setCurrentStage(data.stage);
        setLastStageResult(data);
        processStageResponse(data);
      } catch (err) {
        handleFetchError(err, () => handleAnswerQuestion(fieldKey, answer));
      } finally {
        setIsLoading(false);
      }
    };

    await performRequest();
  };

  // 3. Proceed past Gap -> POST /api/sessions/{id}/proceed
  const handleProceedSession = async () => {
    if (!sessionId || !backendUrl || isLoading) return;

    setErrorMessage(null);
    setIsLoading(true);
    setLoadingMessage(
      'Checking statutes, running an adversarial legal review, and verifying every citation - this can take up to a minute.'
    );

    const performRequest = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/sessions/${sessionId}/proceed`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });

        if (!res.ok) {
          throw new Error(`Server returned status ${res.status}`);
        }

        const data: OrchestratorStageResult = await res.json();
        setCurrentStage(data.stage);
        setLastStageResult(data);
        processStageResponse(data);
      } catch (err) {
        handleFetchError(err, handleProceedSession);
      } finally {
        setIsLoading(false);
      }
    };

    await performRequest();
  };

  const isInitialState = !sessionId && messages.length === 0;
  const isReviseState =
    currentStage === 'message_too_long' || currentStage === 'unclear_domain';

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-6 sm:px-6">
      {/* Introduction Hero (Only shown before first message or when revised) */}
      {isInitialState && (
        <div className="my-6 text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/50 dark:text-indigo-300">
            ⚖️ Powered by Real Statutory Grounding & Adversarial Debate
          </span>
          <h2 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-white">
            Ask your legal question with confidence
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-600 dark:text-slate-400">
            NyayaSetu interviews you to gather facts, retrieves relevant sections from Indian statutes,
            audits citations against the statutory text, and performs a judicial debate.
          </p>
        </div>
      )}

      {/* Chat Messages Timeline */}
      <div className="flex-1 space-y-4">
        {messages.map((msg) => (
          <ChatBubble
            key={msg.id}
            role={msg.role}
            content={msg.content}
            stage={msg.stage}
            timestamp={msg.timestamp}
          />
        ))}

        {/* Current Active Interactive Stage */}
        {/* 1. Intake Question Stage */}
        {currentStage === 'intake_question' && lastStageResult?.field_key && (
          <IntakeInput
            fieldKey={lastStageResult.field_key}
            onSubmit={handleAnswerQuestion}
            isLoading={isLoading}
          />
        )}

        {/* 2. Final Check Gap Stage */}
        {currentStage === 'final_check_gap' && (
          <div className="mt-2 ml-11 flex items-center gap-3" data-testid="gap-actions">
            <button
              type="button"
              onClick={handleProceedSession}
              disabled={isLoading}
              data-testid="continue-anyway-btn"
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-60"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
              Continue anyway
            </button>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Proceed to statutory search & legal review
            </span>
          </div>
        )}

        {/* 3. Complete Stage (Terminal Result Panel) */}
        {currentStage === 'complete' && lastStageResult && (
          <ResultPanel result={lastStageResult} onReset={handleReset} />
        )}

        {/* Loading Indicator */}
        {isLoading && (
          <LoadingIndicator
            message={loadingMessage}
            isPipelineDeep={
              currentStage === 'intake_question' || currentStage === 'final_check_gap'
            }
          />
        )}

        {/* Error Notice */}
        {errorMessage && (
          <ErrorNotice
            message={errorMessage}
            onRetry={lastAction ? () => lastAction() : undefined}
            onDismiss={() => setErrorMessage(null)}
          />
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Initial / Revision Input Box */}
      {(isInitialState || isReviseState) && (
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleStartSession();
            }}
            data-testid="initial-message-form"
          >
            <label
              htmlFor="citizen-initial-message"
              className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400"
            >
              {isReviseState ? 'Revise Your Legal Dispute' : 'Describe your legal situation or dispute'}
            </label>
            <textarea
              id="citizen-initial-message"
              data-testid="initial-message-input"
              rows={4}
              value={initialMessage}
              onChange={(e) => setInitialMessage(e.target.value)}
              placeholder="Example: I purchased a laptop for ₹45,000 from an e-commerce platform that arrived defective. The seller refused a replacement or refund within the 7-day return window..."
              disabled={isLoading}
              className="w-full rounded-xl border border-slate-300 bg-white p-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-50 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {initialMessage.length} characters (10 - 2,000 recommended)
              </span>

              <button
                type="submit"
                disabled={!initialMessage.trim() || isLoading}
                data-testid="submit-initial-message-btn"
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-indigo-300 dark:disabled:bg-indigo-900/50"
              >
                {isLoading ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
                    <span>Analyzing...</span>
                  </>
                ) : (
                  <>
                    <span>{isReviseState ? 'Resubmit Dispute' : 'Ask NyayaSetu'}</span>
                    <svg
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M14 5l7 7m0 0l-7 7m7-7H3"
                      />
                    </svg>
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Quick Starter Prompts for Citizen Convenience */}
          {isInitialState && (
            <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800/80">
              <div className="text-[11px] font-medium text-slate-400 mb-2">
                Or try one of these common inquiries:
              </div>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() =>
                    setInitialMessage(
                      'I bought a smartphone for ₹25,000 from an online seller two months ago. The display malfunctioned and the authorized service center is refusing warranty repair.'
                    )
                  }
                  className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300"
                >
                  Defective Product: Warranty refusal
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setInitialMessage(
                      'An airline cancelled my flight booked for ₹18,000 three months ago and has refused to refund the ticket amount despite multiple written requests.'
                    )
                  }
                  className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300"
                >
                  Deficiency in Service: Cancelled flight refund
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setInitialMessage(
                      'The builder has delayed handing over possession of my flat by 18 months beyond the agreed date.'
                    )
                  }
                  className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300"
                >
                  Consumer / Real Estate: Delayed flat possession
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
