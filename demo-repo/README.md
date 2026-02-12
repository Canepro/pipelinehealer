# PipelineHealer Demo Repository

This repository is used to demonstrate and test PipelineHealer's self-healing capabilities.

## Triggering Failures

You can manually trigger different types of failures using GitHub Actions workflow dispatch:

1. Go to **Actions** → **CI** → **Run workflow**
2. Select a failure type:
   - `none` - Normal successful build
   - `dependency` - Simulates a dependency installation failure
   - `lint` - Simulates a linting error
   - `test` - Simulates a test failure
   - `build_config` - Simulates a missing configuration error
   - `timeout` - Simulates a timeout

## Expected PipelineHealer Behavior

When a failure occurs, PipelineHealer will:

1. **Detect** the failed workflow run via webhook
2. **Analyze** the failure logs
3. **Diagnose** the root cause
4. **Remediate** by creating a PR or issue

## Testing Scenarios

### Dependency Failure
- **Trigger**: Select `dependency` failure type
- **Expected (Recommended)**: PipelineHealer creates a PR that adds the missing dependency to `package.json`

### Lint Failure
- **Trigger**: Select `lint` failure type
- **Expected (Recommended)**: PipelineHealer creates a PR that adds `eslint.config.js` (ESLint flat config)

### Test Failure
- **Trigger**: Select `test` failure type
- **Expected**: PipelineHealer creates an issue with test failure analysis

### Config Failure
- **Trigger**: Select `build_config` failure type
- **Expected**: PipelineHealer creates an issue about missing environment variables

### Timeout
- **Trigger**: Select `timeout` failure type
- **Expected**: PipelineHealer creates an issue with timeout recommendations

## Tooling Note

This demo repo's CI uses **Bun** (`oven-sh/setup-bun`) to align with PipelineHealer's frontend stack.
