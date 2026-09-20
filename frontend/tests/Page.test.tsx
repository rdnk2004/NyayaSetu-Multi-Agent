import React from 'react';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import HomePage from '@/app/page';
import { ConfigProvider } from '@/context/ConfigContext';
import { DisclaimerBanner } from '@/components/DisclaimerBanner';
import { OrchestratorStageResult, SessionStartResponse } from '@/types/api';

// Helper component that replicates the layout shell (disclaimer + config + page)
const TestAppShell = () => {
  return (
    <div>
      <DisclaimerBanner />
      <ConfigProvider>
        <HomePage />
      </ConfigProvider>
    </div>
  );
};

describe('NyayaSetu Frontend Component & Orchestrator Flow Tests', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('renders the initial message input on first load', async () => {
    // Mock /api/config
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ backendUrl: 'http://localhost:8000' }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestAppShell />);

    // Wait for ConfigProvider to resolve
    const textarea = await screen.findByTestId('initial-message-input');
    expect(textarea).toBeInTheDocument();

    const submitBtn = screen.getByTestId('submit-initial-message-btn');
    expect(submitBtn).toBeInTheDocument();
    expect(screen.getByText(/Ask NyayaSetu/i)).toBeInTheDocument();
  });

  it('renders an intake question and lets the user submit an answer', async () => {
    const intakeQuestionResponse: SessionStartResponse = {
      session_id: 'session-xyz-123',
      stage: 'intake_question',
      message: null,
      field_key: 'security_deposit_amount',
      question_text: 'What was the exact amount of security deposit paid to your landlord?',
      gap: null,
      verified: null,
      final_answer: null,
      verified_sections: [],
      rejected_sections: [],
      debate: null,
      critic: null,
      critic_revision_discarded: false,
    };

    const nextStageResponse: OrchestratorStageResult = {
      stage: 'intake_question',
      message: null,
      field_key: 'written_agreement',
      question_text: 'Do you have a written, registered rental agreement?',
      gap: null,
      verified: null,
      final_answer: null,
      verified_sections: [],
      rejected_sections: [],
      debate: null,
      critic: null,
      critic_revision_discarded: false,
    };

    global.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/api/config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ backendUrl: 'http://localhost:8000' }),
        });
      }
      if (url.includes('/api/sessions') && options?.method === 'POST') {
        if (url.includes('/answer')) {
          return Promise.resolve({
            ok: true,
            json: async () => nextStageResponse,
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => intakeQuestionResponse,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestAppShell />);

    // Type initial message and submit
    const textarea = await screen.findByTestId('initial-message-input');
    fireEvent.change(textarea, {
      target: { value: 'My landlord withheld my rental deposit in Bengaluru.' },
    });

    const submitBtn = screen.getByTestId('submit-initial-message-btn');
    fireEvent.click(submitBtn);

    // Verify intake question appears in assistant bubble
    const questionBubble = await screen.findByText(
      /What was the exact amount of security deposit paid to your landlord\?/i
    );
    expect(questionBubble).toBeInTheDocument();

    // Verify intake input form is rendered
    const intakeInput = screen.getByPlaceholderText(/Type your response here/i);
    expect(intakeInput).toBeInTheDocument();

    // Submit answer to intake question
    fireEvent.change(intakeInput, { target: { value: '₹50,000 paid via bank transfer' } });
    const answerSubmitBtn = screen.getByTestId('submit-intake-answer-btn');
    fireEvent.click(answerSubmitBtn);

    // Verify next question is received and user answer is appended
    await waitFor(() => {
      expect(screen.getByText('₹50,000 paid via bank transfer')).toBeInTheDocument();
      expect(
        screen.getByText(/Do you have a written, registered rental agreement\?/i)
      ).toBeInTheDocument();
    });

    // Verify fetch was called with correct parameters
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/sessions/session-xyz-123/answer',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          field_key: 'security_deposit_amount',
          answer: '₹50,000 paid via bank transfer',
        }),
      })
    );
  });

  it('renders the final result panel correctly given a mocked "complete" stage response, including verified_sections and the critic_revision_discarded note when true', async () => {
    const completeResponse: SessionStartResponse = {
      session_id: 'session-complete-999',
      stage: 'complete',
      message: null,
      field_key: null,
      question_text: null,
      gap: null,
      verified: true,
      final_answer:
        'Under Section 108 of the Transfer of Property Act and local Tenancy Laws, a tenant is entitled to the full refund of the security deposit within 30 days of vacating, subject only to reasonable deductions for actual damages backed by receipts.',
      verified_sections: ['Section 108 Transfer of Property Act', 'Section 105 TPA'],
      rejected_sections: ['Section 420 IPC'],
      debate: {
        is_grey_zone: true,
        judge_summary:
          'Tenant has established possession surrender, but absence of written handover receipt leaves room for landlord contestation regarding wear and tear.',
        clearly_supported_side: 'plaintiff',
        plaintiff_argument: 'Tenant vacated premises and gave 30 days notice.',
        plaintiff_cited_sections: ['Section 108'],
        defense_argument: 'Landlord claims verbal notice was insufficient.',
        defense_cited_sections: ['Section 106'],
      },
      critic: {
        approved: false,
        final_answer: 'Refined synthesis grounded in verified statutes.',
        critique_notes:
          'Removed premature references to criminal breach of trust; civil recovery suit under Order 37 CPC is the grounded statutory remedy.',
        flagged_grey_zone_conflict: true,
      },
      critic_revision_discarded: true,
    };

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ backendUrl: 'http://localhost:8000' }),
        });
      }
      if (url.includes('/api/sessions')) {
        return Promise.resolve({
          ok: true,
          json: async () => completeResponse,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestAppShell />);

    // Submit initial message
    const textarea = await screen.findByTestId('initial-message-input');
    fireEvent.change(textarea, { target: { value: 'Deposit dispute query' } });
    fireEvent.click(screen.getByTestId('submit-initial-message-btn'));

    // Verify ResultPanel renders
    const resultPanel = await screen.findByTestId('result-panel');
    expect(resultPanel).toBeInTheDocument();

    // Verify primary final_answer is displayed prominently
    expect(screen.getByTestId('final-answer')).toHaveTextContent(
      'Under Section 108 of the Transfer of Property Act'
    );

    // Verify verified citation chips and rejected citation chips
    expect(
      screen.getByTestId('citation-chip-verified-Section 108 Transfer of Property Act')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('citation-chip-rejected-Section 420 IPC')
    ).toBeInTheDocument();

    // Verify critic_revision_discarded note is shown with honest reassurance phrasing
    const discardedNote = screen.getByTestId('critic-discarded-note');
    expect(discardedNote).toBeInTheDocument();
    expect(discardedNote).toHaveTextContent(
      'Our verification system caught an unverifiable claim in an earlier draft of this answer and removed it before showing you this result.'
    );

    // Verify debate card honest grey-zone badge is present
    expect(screen.getByTestId('debate-status-grey-zone')).toHaveTextContent(/Contested/i);
    expect(screen.getByText(/Plaintiff \/ Aggrieved Party/i)).toBeInTheDocument();

    // Verify critic notes transparency
    expect(screen.getByTestId('critic-notes-panel')).toHaveTextContent(
      'Removed premature references to criminal breach of trust'
    );
  });

  it('renders a friendly error state on a mocked network failure', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ backendUrl: 'http://localhost:8000' }),
        });
      }
      if (url.includes('/api/sessions')) {
        return Promise.reject(new TypeError('Failed to fetch'));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestAppShell />);

    const textarea = await screen.findByTestId('initial-message-input');
    fireEvent.change(textarea, { target: { value: 'Consumer protection inquiry' } });
    fireEvent.click(screen.getByTestId('submit-initial-message-btn'));

    // Verify friendly error message appears
    const errorNotice = await screen.findByTestId('error-notice');
    expect(errorNotice).toBeInTheDocument();
    expect(errorNotice).toHaveTextContent(
      "Couldn't reach the server - check your connection and try again."
    );

    // Verify retry button is present
    expect(screen.getByTestId('error-retry-btn')).toBeInTheDocument();
  });

  it('the disclaimer is present in the rendered output regardless of stage', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ backendUrl: 'http://localhost:8000' }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestAppShell />);

    const disclaimerText =
      'This tool provides information grounded in retrieved statutory text. It is not a substitute for professional legal advice and cannot guarantee any case outcome.';

    // Check disclaimer presence in initial stage
    const disclaimer = await screen.findByRole('note', { name: /Legal Disclaimer/i });
    expect(disclaimer).toBeInTheDocument();
    expect(disclaimer).toHaveTextContent(disclaimerText);
  });
});
