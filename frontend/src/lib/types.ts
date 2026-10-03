export type Health = 'healthy' | 'warning' | 'degraded' | 'critical' | 'unknown';
export type NodeType = 'router' | 'switch' | 'server' | 'collector';
export type Side = 'top' | 'bottom' | 'left' | 'right';

export interface Iface {
  name: string;
  ifIndex?: number;
  side: Side;
  speedMbps: number;
  description?: string;
  operState?: 'up' | 'down';
  utilization?: number;
}

export interface TopoNode {
  id: string;
  type: NodeType;
  label: string;
  vendor?: string;
  zone?: string;
  managementIp: string;
  position: { x: number; y: number };
  interfaces: Iface[];
  status: Health;
  metrics: Record<string, number>;
}

export interface TopoLink {
  id: string;
  source: string;
  sourcePort: string;
  target: string;
  targetPort: string;
  role: 'uplink' | 'access' | 'backup' | 'discovered';
  speedMbps: number;
  status: Health;
  utilization: number;
  latencyMs: number;
  packetLoss: number;
}

export interface Service {
  id: string;
  label: string;
  host: string;
  port: number;
  dependsOn: string[];
  status: Health;
  metrics: Record<string, number>;
}

export interface Topology {
  site: string;
  vantage: string;
  nodes: TopoNode[];
  links: TopoLink[];
  services: Service[];
  discovery: {
    state: 'waiting' | 'live' | 'degraded';
    source: string;
    observedAt: string | null;
    receivedAt: string | null;
    collectorId: string | null;
    errors: string[];
    staleAfterSeconds: number;
  };
}

export type IncidentStatus =
  | 'open'
  | 'investigating'
  | 'recommendation_ready'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'resolved';

export type ScoreKey =
  | 'metric_anomaly'
  | 'dependency_overlap'
  | 'temporal_proximity'
  | 'blast_radius'
  | 'historical_support';

export interface Evidence {
  id: string;
  entityId: string;
  metric: string;
  value: number;
  baseline: number;
  unit: string;
  ts: string;
  text: string;
}

export interface Candidate {
  entityId: string;
  label: string;
  score: number;
  components: Record<ScoreKey, number>;
  evidence: string[];
  suppressedBy?: string | null;
}

export interface PlaybookStep {
  n: number;
  kind: 'read' | 'change' | 'verify';
  title: string;
  command?: string;
}

export interface VendorCheck {
  capability: string;
  why: string;
  commands: string[];
  available: boolean;
}

export interface VendorDiagnose {
  device: string;
  vendor: string | null;
  os: string | null;
  interface: string | null;
  coverage?: string;
  note?: string;
  checks: VendorCheck[];
}

export interface VendorFix {
  id: string;
  title: string;
  risk: string;
  rollback: string;
  needsApproval: boolean;
  commands: { device: string; capability: string; commands: string[] }[];
}

/** How a change is applied, saved and rolled back on a device's OS (reference text; RootIQ never runs it). */
export interface ConfigModel {
  style: 'running-startup' | 'candidate-commit' | 'auto-save';
  summary: string;
  summaryAr: string;
  enter: string[];
  save: string[];
  snapshot: string[];
  safeChange: string[];
  rollback: string[];
  notes?: string | null;
  cliStyle?: string | null;
  cliStyleAr?: string | null;
}

export interface VendorDevice {
  id: string;
  label: string;
  role: string | null;
  interface: string | null;
  vendor: string | null;
  vendorName: string | null;
  os: string | null;
  osName: string | null;
  version?: string | null;
  confidence: string;
  configModel?: ConfigModel | null;
}

/** Reference commands per device vendor. Shown to the engineer; RootIQ never executes them. */
export interface VendorCommands {
  problem: string;
  title: string;
  titleAr: string;
  devices: VendorDevice[];
  diagnose: VendorDiagnose[];
  fixes: VendorFix[];
  executable: false;
  note: string;
}

export interface VendorProblem {
  id: string;
  title: string;
  titleAr: string;
  severity: string;
  summary: string;
  summaryAr: string;
  causes: string[];
  diagnose: VendorDiagnose[];
  fixes: VendorFix[];
}

export interface VendorContext {
  rootEntity: string;
  kind: string;
  devices: VendorDevice[];
  problems: VendorProblem[];
  known: number;
  aiReference?: AIReference | null;
}

export interface ActionPlan {
  playbookId: string;
  title: string;
  preconditions: string[];
  steps: PlaybookStep[];
  rollback: { title: string; command?: string }[];
  verification: { entity: string; metric: string; op: string; value: number }[];
  expectedEffect: string;
  blastRadius: string;
  riskFactors: string[];
  labImplementation: string;
  requiresApproval: boolean;
  autoExecutable: boolean;
  vendorCommands?: VendorCommands;
}

export interface Verification {
  status: 'verified' | 'partial' | 'unverified' | 'no_criteria';
  passed: number;
  total: number;
  checks: { entity: string; metric: string; op: string; target: number; observed: number | null; ok: boolean }[];
}

export interface KnowledgeHit {
  id: string;
  kind: string;
  source: string;
  title: string;
  score: number;
  snippet: string;
}

export interface AIReference {
  gap: string;
  text: string;
}

export interface Action {
  id: string;
  incidentId: string;
  actionType: string;
  description: string;
  riskLevel: 'low' | 'medium' | 'high';
  approvalStatus: 'pending' | 'approved' | 'rejected' | 'executed' | 'failed';
  decidedBy?: string;
  reason?: string;
  decidedAt?: string;
  executedAt?: string;
  alternatives?: string[];
  scenario?: string;
  plan?: ActionPlan;
  guardrailWarnings?: string[];
  dryRun?: boolean;
}

export interface Incident {
  id: string;
  title: string;
  status: IncidentStatus;
  severity: 'low' | 'medium' | 'high' | 'critical';
  openedAt: string;
  resolvedAt?: string;
  rootCause?: { entityId: string; label: string; confidence: number };
  needsInvestigation: boolean;
  candidates: Candidate[];
  evidence: Evidence[];
  affectedServices: string[];
  causePath: string[];
  impactPath: string[];
  explanation?: { en: string; ar: string; source: 'template' | 'llm' };
  action?: Action;
  rawAlertCount: number;
  members?: string[];
  acknowledgedBy?: string | null;
  acknowledgedAt?: string | null;
  verification?: Verification | null;
  knowledge?: {
    similar: KnowledgeHit[];
    references: KnowledgeHit[];
    aiReference?: AIReference | null;
  } | null;
  vendorContext?: VendorContext | null;
  timings: {
    injectedAt?: string;
    firstAnomalyAt?: string;
    detectedAt?: string;
    analyzedAt?: string;
    decidedAt?: string;
    rejectedAt?: string;
    executedAt?: string;
    recoveredAt?: string;
  };
}

export interface RawAlert {
  id: string;
  sourceId: string;
  metric: string;
  value: number;
  severity: 'warning' | 'critical';
  ts: string;
}

export interface DemoState {
  mode: 'live' | 'sim';
  scenario: string | null;
  state: 'idle' | 'injected' | 'remediating' | 'recovered';
  injectedAt?: string;
}

export interface Snapshot {
  topology: Topology;
  incidents: Incident[];
  alerts: RawAlert[];
  demo: DemoState;
}

export interface AgentStats {
  runs: number;
  errors: number;
  skipped: number;
  avgMs: number;
  lastAt: string | null;
  lastStatus: string | null;
  lastSummary: string | null;
}

export interface AgentInfo {
  id: string;
  name: string;
  nameAr: string;
  layer: 'supervisor' | 'perception' | 'reasoning' | 'knowledge' | 'governance' | 'action' | 'learning';
  autonomy: 'observe' | 'advise' | 'coordinate' | 'act_with_approval';
  mission: string;
  missionAr: string;
  benefit: string;
  benefitAr: string;
  inputs: string[];
  outputs: string[];
  tools: string[];
  needs: string[];
  guardrails: string[];
  usesLlm: boolean;
  canDisable: boolean;
  enabled: boolean;
  stats: AgentStats;
}

export interface AgentStep {
  id: string;
  agent: string;
  action: string;
  incidentId: string | null;
  status: 'ok' | 'error' | 'skipped' | 'denied';
  startedAt: string;
  durationMs: number;
  summary: string;
  data: Record<string, unknown>;
  decision: string | null;
}

export interface AgentsResponse {
  agents: AgentInfo[];
  flow: { stages: { stage: string; agents: string[] }[]; edges: string[][] };
  health: {
    agents: number;
    disabled: string[];
    llm: { enabled: boolean; provider: string; model: string; requested: boolean };
    telemetry: { eventsSeen: number; sources: number; stale: string[]; qualityScore: number };
    knowledge: { chunks: number; loaded?: boolean };
    vendors?: { vendors: number; problems: number; coverage: { full: number; partial: number; 'profile-only': number } };
    traceSteps: number;
  };
}

export interface CopilotAnswer {
  answer: string;
  lang: 'ar' | 'en';
  intent: string;
  entity: string | null;
  incidentId: string | null;
  confidence: string;
  source: 'deterministic' | 'llm';
  sources: { n: number; source: string; title: string; score?: number }[];
  facts: Record<string, unknown>;
  warnings: string[];
}

export type WsMessage =
  | { type: 'agent_step'; ts: number; data: AgentStep }
  | { type: 'snapshot'; ts: number; data: Snapshot }
  | { type: 'link'; ts: number; data: Pick<TopoLink, 'id' | 'status' | 'utilization' | 'latencyMs' | 'packetLoss'> }
  | { type: 'node'; ts: number; data: { id: string; status: Health; metrics: Record<string, number> } }
  | { type: 'service'; ts: number; data: { id: string; status: Health; metrics: Record<string, number> } }
  | { type: 'alert'; ts: number; data: RawAlert }
  | { type: 'incident'; ts: number; data: Incident }
  | { type: 'demo'; ts: number; data: DemoState }
  | { type: 'topology'; ts: number; data: Topology };
