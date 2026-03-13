import { describe, expect, it } from 'vitest'

import type { Activity } from '../api/client'
import { getActivitySourceInfo } from './activitySource'

function buildActivity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 'activity-1',
    repositoryId: 'repo-1',
    repository_name: 'Canepro/pipelinehealer',
    workflow_run_id: 123,
    workflow_name: 'CI',
    status: 'failed',
    created_at: '2026-03-13T10:00:00Z',
    updated_at: '2026-03-13T10:05:00Z',
    ...overrides,
  }
}

describe('getActivitySourceInfo', () => {
  it('builds GitHub repository and run links for default workflow activities', () => {
    const info = getActivitySourceInfo(buildActivity())

    expect(info.provider).toBe('github')
    expect(info.providerLabel).toBe('GitHub Actions')
    expect(info.repositoryUrl).toBe('https://github.com/Canepro/pipelinehealer')
    expect(info.runUrl).toBe(
      'https://github.com/Canepro/pipelinehealer/actions/runs/123',
    )
    expect(info.runNumberLabel).toBe('Run #123')
  })

  it('prefers Jenkins bridge metadata and avoids fabricating GitHub repo links', () => {
    const info = getActivitySourceInfo(
      buildActivity({
        repository_name: 'team/service-ci',
        workflow_run_id: 45,
        workflow_name: 'deploy-prod',
        source_selection_path: 'jenkins_bridge',
        source_metadata: {
          provider: 'jenkins',
          job_url: 'https://jenkins.example/job/team/job/service-ci/45/',
        },
      }),
    )

    expect(info.provider).toBe('jenkins')
    expect(info.providerLabel).toBe('Jenkins Bridge')
    expect(info.repositoryUrl).toBeNull()
    expect(info.runUrl).toBe(
      'https://jenkins.example/job/team/job/service-ci/45/',
    )
    expect(info.runLabel).toBe('Jenkins Build')
    expect(info.runNumberLabel).toBe('Build #45')
  })
})
