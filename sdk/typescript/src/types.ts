export type Priority = "high" | "normal";

export interface PrinterTarget {
  ip: string;
  port: number;
}

export interface PrinterCommand {
  command: string;
  [key: string]: unknown;
}

export interface PrintPayload {
  printer_id: string;
  printer: PrinterTarget;
  command: PrinterCommand | { command: PrinterCommand };
  priority?: Priority;
}

export interface PrintInnerResponse {
  attempt?: number;
  command?: PrinterCommand;
  ok?: boolean;
  reason?: string | null;
  response_command?: string | null;
  response_status?: string | null;
  protocol_error_code?: string | null;
  protocol_error_description?: string | null;
  raw_response?: string | null;
  response?: unknown;
  error_type?: string;
  details?: Record<string, unknown> | null;
}

export interface PrintApiResponse {
  success: boolean;
  error?: string | null;
  status?: "completed" | "failed" | string;
  execution_mode?: string;
  job_id?: string;
  printer_id?: string;
  printer?: PrinterTarget;
  command?: PrinterCommand;
  response?: PrintInnerResponse;
  printer_ok?: boolean;
  printer_reason?: string | null;
  printer_response_command?: string | null;
  printer_response_status?: string | null;
  printer_protocol_error_code?: string | null;
  printer_protocol_error_description?: string | null;
  printer_raw_response?: string | null;
  printer_response_payload?: unknown;
  created_at?: string;
  updated_at?: string;
}

export interface JobResponse extends PrintApiResponse {
  success: boolean;
}

export interface JobsResponse {
  success: boolean;
  jobs: PrintApiResponse[];
}

export interface MetricsResponse {
  success: boolean;
  total: number;
  completed: number;
  failed: number;
}

export interface HealthResponse {
  status: string;
  service: string;
}

export interface PrintersResponse {
  [printerId: string]: {
    ip: string;
    port: number;
    connection_status: string;
    socket_connected: boolean;
  };
}

export type PrintOutcomeKind =
  | "success"
  | "payload_error"
  | "transport_error"
  | "read_timeout"
  | "no_response"
  | "printer_rejected"
  | "printer_alarm"
  | "printer_missing_data"
  | "printer_protocol_error"
  | "printer_failed_status"
  | "unknown_failure";

export type RecommendedAction =
  | "done"
  | "fix_payload"
  | "retry_now"
  | "retry_later"
  | "ask_operator";

export interface PrintDecision {
  ok: boolean;
  kind: PrintOutcomeKind;
  shouldRetry: boolean;
  recommendedAction: RecommendedAction;
  reason: string;
  jobId?: string;
  response: PrintApiResponse;
}

export interface ClientOptions {
  baseUrl: string;
  timeoutMs?: number;
  defaultHeaders?: Record<string, string>;
  fetchImpl?: typeof fetch;
}

export interface PrintRequestOptions {
  retries?: number;
  retryDelayMs?: number;
  retryKinds?: PrintOutcomeKind[];
}
