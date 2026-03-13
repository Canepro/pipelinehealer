export const EMPTY_STATES = {
  activities: {
    title: 'No activities yet',
    body: 'When PipelineHealer processes a GitHub Actions run or Jenkins bridge activity, it will appear here.',
  },
  safetyGated: {
    title: 'No safety-gated cases',
    body: 'Safety-gated cases appear when the proposed change is outside policy or needs review.',
  },
  audit: {
    title: 'No audit entries yet',
    body: 'Load audit after making an admin change. Audit is intentionally not fetched automatically.',
  },
} as const
