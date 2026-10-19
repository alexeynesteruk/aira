/**
 * Typed wrappers and the contract subset the review UI reads.
 *
 * Field names mirror the versioned backend contracts (schema_version 0.1.0);
 * only the properties the UI consumes are declared.
 */

export interface SourceSpan {
  block_id: string
  document_id: string
  document_sha256: string
  extraction_id: string
  page: number
  start: number
  end: number
  excerpt: string
}

export interface OperationalError {
  code: string
  message: string
  retryable: boolean
  action: string
  stage?: string | null
  document_id?: string | null
  page?: number | null
}

export interface VersionReference {
  name: string
  version: string
}

export interface ProviderVerification {
  backend?: 'openai' | 'litellm' | 'openai_compatible' | 'custom' | null
  transport?: string | null
  status: string
  provider: string
  checked_at?: string | null
  model_id?: string | null
  region?: string | null
  detail?: string | null
}

export interface ReadinessResponse {
  ready: boolean
  missing_prerequisites: string[]
  provider: ProviderVerification
}

export interface DocumentRecord {
  document_id: string
  role: 'policy' | 'chart'
  filename: string
  sha256: string
  byte_count: number
  page_count: number
  created_at: string
}

export interface TextBlock {
  block_id: string
  text: string
  reading_order: number
}

export interface ExtractedPage {
  page: number
  quality: string
  method?: string | null
  blocks: TextBlock[]
  issues: string[]
}

export interface ExtractionRecord {
  extraction_id: string
  document_id: string
  document_sha256: string
  parser_name: string
  parser_version: string
  configuration_sha256: string
  pages: ExtractedPage[]
}

export interface DocumentResponse {
  document: DocumentRecord
  extractions: ExtractionRecord[]
}

export interface PageResponse {
  document_id: string
  extraction_id: string
  page: ExtractedPage
}

export interface MetadataAnnotation {
  kind: 'text' | 'date'
  annotation_id: string
  origin?: 'staff'
  field: string
  value: string
  created_at: string
  original_sources?: SourceSpan[]
  resolves_conflict?: boolean
  resolution_reason?: string | null
}

export interface FieldSources {
  field: string
  sources: SourceSpan[]
}

export interface RequestContext {
  procedure?: string | null
  procedure_code?: string | null
  anatomical_target?: string | null
  laterality?: string | null
  payer?: string | null
  plan?: string | null
  service_date?: string | null
  assessment_cutoff?: string | null
  field_sources: FieldSources[]
  unresolved_fields: string[]
}

export interface ApplicabilityResult {
  status: 'applicable' | 'mismatch' | 'unresolved'
  rationale: string
  sources: SourceSpan[]
  unresolved_fields: string[]
}

export interface Criterion {
  criterion_id: string
  wording: string
  interpretation: string
  sources: SourceSpan[]
  context: string[]
}

export interface PolicyNode {
  kind: 'all' | 'any' | 'criterion'
  node_id: string
  children?: string[]
  criterion_id?: string
  sources: SourceSpan[]
}

export interface PolicySection {
  section_id: string
  heading: string
  sources: SourceSpan[]
  disposition: 'requirements' | 'context' | 'out_of_scope' | 'unresolved'
  criterion_ids: string[]
  explanation: string
}

export interface ReviewIssue {
  issue_id: string
  category: string
  message: string
  action: string
  blocks_readiness: boolean
  sources: SourceSpan[]
  criterion_ids: string[]
}

export interface Policy {
  policy_id: string
  document_id: string
  document_sha256: string
  title: string
  scope_summary: string
  identifier?: string | null
  revision_date?: string | null
  effective_from?: string | null
  effective_to?: string | null
  criteria: Criterion[]
  nodes: PolicyNode[]
  root_id: string
  sections: PolicySection[]
  issues: ReviewIssue[]
}

export interface ChartFact {
  fact_id: string
  proposition: string
  sources: SourceSpan[]
  polarity: string
  provenance: string
  value?: number | null
  event_date?: string | null
  documentation_date?: string | null
}

export interface EvidenceReference {
  fact_id: string
  relation: 'supporting' | 'contradicting' | 'context'
}

export interface Finding {
  criterion_id: string
  status: 'met' | 'not_met' | 'missing' | 'conflicting' | 'needs_review'
  rationale: string
  evidence: EvidenceReference[]
  unresolved_reasons: string[]
}

export type LogicalValue = 'true' | 'false' | 'unknown'

export interface NodeTrace {
  node_id: string
  kind: 'all' | 'any' | 'criterion'
  logical_value: LogicalValue
  children: string[]
  criterion_id?: string | null
  unresolved_reasons: string[]
  supporting_children: string[]
}

export interface EvaluationResult {
  root_id: string
  logical_value: LogicalValue | null
  outcome:
    | 'applicability_mismatch'
    | 'documented_requirements_satisfied'
    | 'documentation_gaps_or_contrary_evidence'
    | 'review_required'
    | null
  traces: NodeTrace[]
  satisfied_path: string[]
  blockers: { code: string; reference_id?: string | null; message: string }[]
}

export interface AssessmentResult {
  outcome:
    | 'applicability_mismatch'
    | 'documented_requirements_satisfied'
    | 'documentation_gaps_or_contrary_evidence'
    | 'review_required'
  applicability: ApplicabilityResult
  policy?: Policy | null
  facts: ChartFact[]
  findings: Finding[]
  logical_value?: LogicalValue | null
  issues: ReviewIssue[]
  evaluation?: EvaluationResult | null
}

export interface StageUsage {
  phase: string
  attempts: number
  duration_ms: number
  input_tokens?: number | null
  output_tokens?: number | null
  ocr_pages: number
  provider_request_ids: string[]
  provider_response_ids: string[]
  model_id?: string | null
}

export interface ConfigurationProvenance {
  parser: VersionReference
  parser_configuration_sha256: string
  prompts: VersionReference[]
  provider: string
  model_id: string
  region?: string | null
  sdk_version: string
  inference: { max_output_tokens: number }
}

export interface RunProgress {
  completed_phases: string[]
  completed_pages: number
  total_pages?: number | null
  activity?: string | null
}

export interface RunRecord {
  run_id: string
  parent_run_id?: string | null
  policy_build_id?: string | null
  chart_build_id?: string | null
  policy_path_id?: string | null
  policy_document_id: string
  policy_sha256: string
  chart_document_id: string
  chart_sha256: string
  input_fingerprint: string
  configuration: ConfigurationProvenance
  request_context?: RequestContext | null
  annotations: MetadataAnnotation[]
  created_at: string
  updated_at: string
  status: 'queued' | 'running' | 'completed' | 'needs_input' | 'failed' | 'interrupted'
  phase?: string | null
  progress: RunProgress
  applicability?: ApplicabilityResult | null
  result?: AssessmentResult | null
  error?: OperationalError | null
  usage: StageUsage[]
}

export interface AssessmentAccepted {
  run_id: string
  status: 'queued' | 'running'
  phase?: string | null
  status_url: string
}

export interface SubmissionBody {
  policy_build_id?: string
  chart_build_id?: string
  policy_document_id: string
  chart_document_id: string
  parent_run_id?: string
  annotations?: MetadataAnnotation[]
}

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public action?: string,
  ) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error =
      body !== null && typeof body === 'object' && 'error' in body
        ? (body as { error: OperationalError }).error
        : undefined
    throw new ApiRequestError(
      response.status,
      error?.code ?? `http_${response.status}`,
      error?.message ?? `The server returned status ${response.status}.`,
      error?.action,
    )
  }
  return body as T
}

export async function getReadiness(): Promise<ReadinessResponse> {
  // A 503 readiness response is the normal unconfigured state, not a failure.
  const response = await fetch('/health/ready')
  if (response.status === 200 || response.status === 503) {
    return (await response.json()) as ReadinessResponse
  }
  throw new ApiRequestError(
    response.status,
    `http_${response.status}`,
    `The server returned status ${response.status}.`,
  )
}

export async function uploadDocument(file: File, role: 'policy' | 'chart'): Promise<DocumentResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('role', role)
  return request('/api/documents', { method: 'POST', body: form })
}

export function getDocument(documentId: string): Promise<DocumentResponse> {
  return request(`/api/documents/${documentId}`)
}

export function getPage(documentId: string, page: number, extractionId: string): Promise<PageResponse> {
  return request(`/api/documents/${documentId}/pages/${page}?extraction_id=${extractionId}`)
}

export function submitAssessment(body: SubmissionBody): Promise<AssessmentAccepted> {
  return request('/api/assessments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function getRun(runId: string): Promise<RunRecord> {
  return request(`/api/assessments/${runId}`)
}

export interface BuildRecord {
  build_id: string
  parent_build_id: string | null
  document_id: string
  document_sha256: string
  role: 'policy' | 'chart'
  status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted'
  phase: string
  total_sections: number
  completed_sections: number
  review_status: 'draft' | 'approved' | 'rejected'
  cached: boolean
  configuration: ConfigurationProvenance
  policy: Policy | null
  chart: { facts: ChartFact[] } | null
  issues: string[]
  error: OperationalError | null
  steps: { name: string; checkpoint_key: string; cached: boolean }[]
  coverage: { section_id: string; unit_id: string; source: SourceSpan; disposition: string; explanation: string; audited: boolean }[]
}

export function startBuild(documentId: string): Promise<BuildRecord> {
  return request(`/api/documents/${documentId}/builds`, { method: 'POST' })
}
export function listBuilds(documentId: string): Promise<{ builds: BuildRecord[] }> {
  return request(`/api/documents/${documentId}/builds`)
}
export function getBuild(buildId: string): Promise<BuildRecord> {
  return request(`/api/builds/${buildId}`)
}
export function actOnBuild(buildId: string, action: 'retry' | 'rebuild' | 'approve' | 'reject'): Promise<BuildRecord> {
  return request(`/api/builds/${buildId}/${action}`, { method: 'POST' })
}
