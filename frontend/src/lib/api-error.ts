/**
 * Turn an API rejection into something worth showing a user.
 *
 * FastAPI returns `detail` as a plain string for raised HTTPExceptions but as a
 * list of per-field objects for validation failures, so both shapes have to be
 * handled or a 422 renders as "[object Object]".
 */

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

interface ApiErrorShape {
  response?: { data?: { detail?: string | ValidationIssue[] } };
  message?: string;
}

function formatIssue(issue: ValidationIssue): string {
  // loc is ["body", "<field>"] — the field name is the only useful part.
  const field = issue.loc?.filter((part) => part !== "body").join(".");
  const message = issue.msg ?? "is invalid";
  return field ? `${field}: ${message}` : message;
}

export function apiErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  const detail = (error as ApiErrorShape)?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map(formatIssue).join("; ");
  }

  const message = (error as ApiErrorShape)?.message;
  return message?.trim() ? message : fallback;
}
