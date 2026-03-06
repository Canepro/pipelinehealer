const KNOWN_LABELS: Record<string, string> = {
  'ci-doctor': 'CI Doctor',
  'external-diagnostics': 'External Diagnostics',
  'github-mcp': 'GitHub MCP',
  'knowledge-mcp': 'Knowledge MCP',
  github: 'GitHub',
  gh_aw: 'GitHub Agentic Workflows',
  azure_monitor: 'Azure Monitor',
}

export function formatSourceLabel(source: string): string {
  const normalizedRaw = source.trim().toLowerCase()
  if (KNOWN_LABELS[normalizedRaw]) {
    return KNOWN_LABELS[normalizedRaw]
  }
  const normalized = normalizedRaw.replace(/[_-]+/g, ' ')
  if (!normalized) {
    return 'External'
  }
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase())
}
