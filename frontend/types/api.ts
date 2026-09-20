/**
 * TypeScript Data Contracts for the NyayaSetu API and Orchestrator.
 */

export type StageType =
  | 'message_too_long'
  | 'unclear_domain'
  | 'intake_question'
  | 'final_check_gap'
  | 'complete';

export interface DebateResult {
  is_grey_zone: boolean;
  judge_summary: string;
  clearly_supported_side: 'plaintiff' | 'defense' | null;
  plaintiff_argument: string;
  plaintiff_cited_sections: string[];
  defense_argument: string;
  defense_cited_sections: string[];
}

export interface CriticResult {
  approved: boolean;
  final_answer: string;
  critique_notes: string;
  flagged_grey_zone_conflict: boolean;
}

export interface OrchestratorStageResult {
  stage: StageType;
  message: string | null;
  field_key: string | null;
  question_text: string | null;
  gap: string | null;
  verified: boolean | null;
  final_answer: string | null;
  verified_sections: string[];
  rejected_sections: string[];
  debate: DebateResult | null;
  critic: CriticResult | null;
  critic_revision_discarded: boolean;
  session_id?: string;
}

export interface SessionStartResponse extends OrchestratorStageResult {
  session_id: string;
}

export interface ConfigResponse {
  backendUrl: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  stage?: StageType;
  result?: OrchestratorStageResult;
  timestamp: string;
}
