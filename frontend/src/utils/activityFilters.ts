type ActivitiesDrilldownFilters = {
  repository?: string | null;
  failureType?: string | null;
  status?: string | null;
  focus?: string | null;
};

export function buildActivitiesDrilldownPath(
  filters: ActivitiesDrilldownFilters,
): string {
  const searchParams = new URLSearchParams();
  const repository = filters.repository?.trim();
  const failureType = filters.failureType?.trim();
  const status = filters.status?.trim();
  const focus = filters.focus?.trim();

  if (repository) searchParams.set("repository", repository);
  if (failureType) searchParams.set("failure_type", failureType);
  if (status) searchParams.set("status", status);
  if (focus) searchParams.set("focus", focus);

  const query = searchParams.toString();
  return `/app/activities${query ? `?${query}` : ""}`;
}
