import { expect, test } from 'claude-code/testing'

const TOOL = 'mcp__flow-status__update'

// Each hook here stands for the engine beneath the plugin; `lines` collects what the
// plugin pins as its status line, `undefined` for a cleared one.
function engine(on, branch: string) {
  const lines: (string | undefined)[] = []
  on('tool.register', (_, e) => ({ value: { tool: `mcp__flow-status__${e.name}` } }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: `${branch}\n`, stderr: '' } }))
  on('ui.status', (_, e) => {
    lines.push(e.text)
    return { value: undefined }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
  on('turn.complete', () => ({}))
  return lines
}

async function start($) {
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
}

test('on a base branch with nothing reported the line stays empty', async ($, on) => {
  const lines = engine(on, 'develop')
  await start($)

  expect(lines.at(-1)).toBe(undefined)
})

test('a feature branch stands in for the topic until the model names one', async ($, on) => {
  const lines = engine(on, 'feature/leve-menu')
  await start($)
  expect(lines.at(-1)).toBe('◆ feature/leve-menu')

  await $.tool.call({ tool: TOOL, topic: 'Levé menu konverzace', phase: 'implementace' })
  expect(lines.at(-1)).toBe('◆ Levé menu konverzace  │  ▸ implementace 4/12')
})

test('a phase alone keeps the topic, and hotovo closes the run', async ($, on) => {
  const lines = engine(on, 'develop')
  await start($)

  await $.tool.call({ tool: TOOL, topic: 'Export', phase: 'plan' })
  await $.tool.call({ tool: TOOL, phase: 'hotovo' })
  expect(lines.at(-1)).toBe('◆ Export  │  ✓ hotovo')
})

test('the feature plugin’s subagents move the step on their own', async ($, on) => {
  const lines = engine(on, 'develop')
  await start($)
  await $.tool.call({ tool: TOOL, topic: 'Export', phase: 'implementace' })

  await $.tool.call({ tool: 'Agent', subagent_type: 'feature:e2e-tester', prompt: 'x', description: 'x' })
  expect(lines.at(-1)).toBe('◆ Export  │  ▸ e2e 5/12')

  await $.tool.call({ tool: 'Skill', skill: 'feature:security-review' })
  expect(lines.at(-1)).toBe('◆ Export  │  ▸ security 10/12')
})

test('a new /feature:start drops the previous topic', async ($, on) => {
  const lines = engine(on, 'develop')
  await start($)
  await $.tool.call({ tool: TOOL, topic: 'Export', phase: 'commit' })

  await $.tool.call({ tool: 'Skill', skill: 'feature:start' })
  expect(lines.at(-1)).toBe('▸ analyza 1/12')
})

test('an agent inside a subagent or workflow does not move the step', async ($, on) => {
  const lines = engine(on, 'develop')
  await start($)
  await $.tool.call({ tool: TOOL, topic: 'Export', phase: 'code-review' })

  await $.tool.call({ tool: 'Agent', subagent_type: 'feature:linter', prompt: 'x', description: 'x', agentId: 'a1' })
  expect(lines.at(-1)).toBe('◆ Export  │  ▸ code-review 7/12')
})
