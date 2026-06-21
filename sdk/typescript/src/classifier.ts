import {
  PrintApiResponse,
  PrintDecision,
  PrintOutcomeKind,
  RecommendedAction,
} from "./types.js";

const RETRYABLE_KINDS = new Set<PrintOutcomeKind>([
  "transport_error",
  "read_timeout",
  "no_response",
]);

function chooseAction(kind: PrintOutcomeKind): RecommendedAction {
  switch (kind) {
    case "success":
      return "done";
    case "payload_error":
      return "fix_payload";
    case "transport_error":
    case "read_timeout":
      return "retry_now";
    case "no_response":
      return "retry_later";
    case "printer_alarm":
    case "printer_missing_data":
    case "printer_protocol_error":
      return "ask_operator";
    case "printer_rejected":
    case "printer_failed_status":
    case "unknown_failure":
    default:
      return "ask_operator";
  }
}

function mapFailureKind(response: PrintApiResponse): PrintOutcomeKind {
  const errorType = (response.response?.error_type ||
    (response.response?.details as Record<string, unknown> | undefined)?.[
      "error_type"
    ] ||
    "") as string;
  const cmd = (response.printer_response_command || "").toUpperCase();
  const status = (response.printer_response_status || "").toUpperCase();
  const protocolCode = response.printer_protocol_error_code;

  if (errorType === "read_timeout") {
    return "read_timeout";
  }
  if (errorType === "empty_response") {
    return "no_response";
  }
  if (errorType === "transport_exception") {
    return "transport_error";
  }
  if (cmd === "NYES") {
    return "printer_rejected";
  }
  if (cmd === "RSAL") {
    return "printer_alarm";
  }
  if (cmd === "RSMPOD") {
    return "printer_missing_data";
  }
  if (status === "SYSN" || !!protocolCode) {
    return "printer_protocol_error";
  }
  if (["FAILED", "ERROR", "FULL", "NOK"].includes(status)) {
    return "printer_failed_status";
  }
  return "unknown_failure";
}

export function classifyPrintResponse(response: PrintApiResponse): PrintDecision {
  const jobId = response.job_id;

  if (!response.success) {
    const kind: PrintOutcomeKind =
      !response.status && !!response.error ? "payload_error" : mapFailureKind(response);
    const reason = response.printer_reason || response.error || "Print request failed";
    return {
      ok: false,
      kind,
      shouldRetry: RETRYABLE_KINDS.has(kind),
      recommendedAction: chooseAction(kind),
      reason,
      jobId,
      response,
    };
  }

  return {
    ok: true,
    kind: "success",
    shouldRetry: false,
    recommendedAction: "done",
    reason: response.printer_reason || "Command acknowledged by printer",
    jobId,
    response,
  };
}

export function defaultRetryKinds(): PrintOutcomeKind[] {
  return Array.from(RETRYABLE_KINDS);
}
