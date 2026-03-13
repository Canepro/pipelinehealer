import type { Activity } from '../api/client'
import { formatSourceLabel } from './formatSourceLabel'

type ActivityProvider = 'github' | 'jenkins' | 'external'

export type ActivitySourceInfo = {
  provider: ActivityProvider
  providerLabel: string
  workflowLabel: string
  runLabel: string
  runLinkLabel: string
  runNumberLabel: string
  repositoryUrl: string | null
  runUrl: string | null
  repositoryPrimary: string
  repositorySecondary: string | null
}

function getSourceMetadata(activity: Activity): Record<string, unknown> {
  if (!activity.source_metadata || typeof activity.source_metadata !== 'object') {
    return {}
  }
  return activity.source_metadata as Record<string, unknown>
}

function getTrimmedString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function getHttpUrl(value: unknown): string | null {
  const raw = getTrimmedString(value)
  if (!raw) return null
  try {
    const url = new URL(raw)
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      return url.toString()
    }
  } catch {
    return null
  }
  return null
}

function splitRepositoryName(repositoryName: string): {
  primary: string
  secondary: string | null
  slug: string | null
} {
  const trimmed = repositoryName.trim()
  if (!trimmed) {
    return {
      primary: 'Unknown repository',
      secondary: null,
      slug: null,
    }
  }
  const parts = trimmed.split('/', 2).map((part) => part.trim())
  if (parts.length === 2 && parts[0] && parts[1]) {
    return {
      primary: parts[1],
      secondary: parts[0],
      slug: `${parts[0]}/${parts[1]}`,
    }
  }
  return {
    primary: trimmed,
    secondary: null,
    slug: null,
  }
}

export function getActivitySourceInfo(activity: Activity): ActivitySourceInfo {
  const metadata = getSourceMetadata(activity)
  const metadataProvider =
    getTrimmedString(metadata.provider)?.toLowerCase() ?? null
  const provider: ActivityProvider =
    activity.source_selection_path === 'jenkins_bridge' ||
    metadataProvider === 'jenkins'
      ? 'jenkins'
      : metadataProvider === 'github' ||
          metadataProvider === 'github_actions' ||
          metadataProvider === 'gh_aw' ||
          metadataProvider === null
        ? 'github'
        : 'external'

  const repository = splitRepositoryName(activity.repository_name)
  const providerLabel =
    provider === 'jenkins'
      ? 'Jenkins Bridge'
      : provider === 'github'
        ? 'GitHub Actions'
        : formatSourceLabel(metadataProvider ?? activity.source_selection_path ?? 'external')

  const repositoryUrl =
    getHttpUrl(metadata.repository_url) ??
    (provider === 'github' && repository.slug
      ? `https://github.com/${repository.slug}`
      : null)

  const runUrl =
    getHttpUrl(metadata.job_url) ??
    getHttpUrl(metadata.run_url) ??
    (provider === 'github' && repository.slug
      ? `https://github.com/${repository.slug}/actions/runs/${activity.workflow_run_id}`
      : null)

  return {
    provider,
    providerLabel,
    workflowLabel: provider === 'jenkins' ? 'Job' : provider === 'github' ? 'Workflow' : 'Pipeline',
    runLabel:
      provider === 'jenkins'
        ? 'Jenkins Build'
        : provider === 'github'
          ? 'Workflow Run'
          : 'Pipeline Run',
    runLinkLabel:
      provider === 'jenkins'
        ? 'Jenkins build'
        : provider === 'github'
          ? 'Workflow run'
          : 'Pipeline run',
    runNumberLabel:
      provider === 'jenkins'
        ? `Build #${activity.workflow_run_id}`
        : provider === 'github'
          ? `Run #${activity.workflow_run_id}`
          : `Execution #${activity.workflow_run_id}`,
    repositoryUrl,
    runUrl,
    repositoryPrimary: repository.primary,
    repositorySecondary: repository.secondary ?? (repositoryUrl ? null : providerLabel),
  }
}
