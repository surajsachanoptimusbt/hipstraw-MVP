// The desk API's shapes (src/hipstraw_mm/desk and foundry/playbook.py).

export type CaseState = "agent_working" | "waiting_review" | "approved" | "returned";
export type WaitingOn = "agent" | "reviewer" | "customer" | "people";
export type StageKey = "ingest" | "review" | "position" | "recommend" | "workflow" | "approval";
export type EventKind = "request" | "step" | "finding" | "pick" | "gate" | "decision";

export interface CaseSummary {
  id: string;
  company: string;
  market: string;
  caseType: string;
  offering: "shadow_launch" | "day_zero" | "campaign";
  state: CaseState;
  waitingOn: WaitingOn;
  stage: StageKey;
  stageIndex: number;
  stages: number;
  createdAt: string;
  updatedAt: string;
  requestedBy: string;
  hypotheses: number;
  lines: (string | null)[][];
}

export interface LedgerEvent {
  seq: number;
  caseId: string;
  at: string;
  stage: StageKey;
  actor: "agent" | "customer" | "reviewer" | "system";
  who: string;
  kind: EventKind;
  title: string;
  detail: string;
  data: Record<string, unknown>;
  prevHash: string;
  hash: string;
}

export interface ConditionCheck { text: string; ok: boolean }

export interface LineOption {
  lineId: string;
  name: string;
  purpose: string;
  eligible: boolean;
  rank: number | null;
  picked: boolean;
  checks: ConditionCheck[];
  moves: string[];
}

export interface MoveView {
  id: string;
  name: string;
  effect: "E0" | "E1" | "E2" | "E3";
  stage: number;
  status: "done" | "next" | "planned";
  needsCharter: boolean;
  does: string;
  records: string[];
  passWhen: string[];
}

export interface TaskPlay {
  taskId: string;
  task: string;
  question: string;
  options: LineOption[];
  lineId: string | null;
  lineName: string;
  reason: string;
  moves: MoveView[];
}

export interface Metric { id: string; label: string; dimension: string; current: number; target: number; state: string }
export interface Finding { dimension: string; ref: string; title: string; state: string; text: string }

export interface EvidenceView {
  id: string;
  type: string;
  rung: string;
  demand: boolean;
  summary: string;
  source: string;
  independent: boolean;
  fromSegment: boolean;
  supports: string[];
  contradicts: string[];
}

export interface HypothesisPlay {
  id: string;
  name: string;
  demand: string;
  segment: string;
  offering: string;
  buyerRole: string;
  priority: number;
  market: Record<string, string>;
  decision: string;
  decisionText: string;
  checkpoint: string;
  firstAction: string;
  tasks: TaskPlay[];
  metrics: Metric[];
  findings: Finding[];
  evidence: EvidenceView[];
}

export interface Recommendation {
  thesis: string;
  product: string;
  market: string;
  geography: string;
  statement: string;
  asOf: string;
  rubricVersion: string;
  repertoireVersion: string | null;
  ranking: string;
  hypotheses: HypothesisPlay[];
  scope: string;
}

export interface StageView {
  key: StageKey;
  name: string;
  what: string;
  status: "done" | "active" | "pending";
  events: number;
  reached: boolean;
}

export interface Approval { action: "approve" | "return"; actor: string; role: string; at: string; note: string; payloadHash: string }

export interface CaseDetail {
  case: CaseSummary;
  thesis: { product: string; market: string; geography?: string; statement: string; hypotheses: { id: string; name: string }[] };
  recommendation: Recommendation | null;
  payloadHash: string | null;
  approval: Approval | null;
  stages: StageView[];
  events: LedgerEvent[];
}

export interface LibraryLine {
  id: string;
  name: string;
  phase: number;
  purpose: string;
  exit: string;
  useWhen: Record<string, string[]>;
  endsProgram: boolean;
  stages: string[][];
}

export interface LibraryMove {
  id: string;
  name: string;
  effect: "E0" | "E1" | "E2" | "E3";
  does: string;
  how: string[];
  records: string[];
  tests: string[];
  watchOut: string;
}

export interface Library {
  repertoireVersion: string;
  rubricVersion: string;
  ranking: string;
  tasks: { id: string; name: string; question: string; lines: string[] }[];
  lines: LibraryLine[];
  moves: LibraryMove[];
  metrics: { id: string; label: string; dimension: string; targets: Record<string, number> }[];
}

export interface LedgerView {
  verify: { ok: boolean; checked: number; brokenAt: number | null; head: string };
  total: number;
  events: LedgerEvent[];
}

export interface Offering { id: string; name: string; status: "live" | "preview"; summary: string; caseTypes: string[] }
