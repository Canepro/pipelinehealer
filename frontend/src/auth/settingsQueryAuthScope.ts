export function getSettingsQueryAuthScope({
  useSessionAuth,
  adminKey,
  adminKeyScopeId,
}: {
  useSessionAuth: boolean;
  adminKey: string;
  adminKeyScopeId: number | null;
}): string {
  if (useSessionAuth) {
    return "session-auth";
  }

  if (!adminKey) {
    return "no-auth";
  }

  return `admin-key:${adminKeyScopeId ?? 0}`;
}

export function getNextAdminKeyScopeId(
  current: number | null,
): number {
  return (current ?? 0) + 1;
}
