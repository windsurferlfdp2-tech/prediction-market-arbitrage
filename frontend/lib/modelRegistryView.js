export function modelStatusLabel(status) {
  if (status === "approved_for_paper") {
    return "Approved";
  }
  return status.replaceAll("_", " ");
}

export function canApproveModel(status) {
  return status === "candidate" || status === "rejected";
}

export function canRetireModel(status) {
  return status !== "retired";
}

export function shortId(value) {
  if (!value) {
    return "n/a";
  }
  return value.length > 16 ? value.slice(0, 12) : value;
}

export function dateOnly(value) {
  if (!value) {
    return "n/a";
  }
  return value.slice(0, 10);
}
