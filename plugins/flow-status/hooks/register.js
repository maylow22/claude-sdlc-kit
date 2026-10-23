// The topic being worked on and the step of the feature flow it stands at, as this
// plugin's status line under the prompt. The model reports the topic and its own steps
// through a tool; the steps the feature plugin runs in subagents and skills are read
// off the calls themselves, so the model does not have to remember them.

const TOOL = 'mcp__flow-status__update'

// The steps of /feature:start in their order; the index is shown as n/N.
const PHASES = [
  'analyza',
  'plan',
  'plan-review',
  'implementace',
  'e2e',
  'lint',
  'code-review',
  'opravy',
  'dokumentace',
  'security',
  'konzultace',
  'commit',
]
const DONE = 'hotovo'

// A subagent_type or skill name -> the step it runs.
const AUTO = [
  [/^feature:start$/, 'analyza'],
  [/plan-review/, 'plan-review'],
  [/e2e-tester/, 'e2e'],
  [/linter/, 'lint'],
  [/code-review|feature:reviewer$/, 'code-review'],
  [/doc-writer/, 'dokumentace'],
  [/security-review/, 'security'],
]

// Being on one of these says nothing about the topic, so no branch stands in for it.
const BASE_BRANCHES = new Set(['main', 'master', 'develop', ''])

// The description is the only place the model reads how to use the tool: a security
// plugin may skip a prompt.compose hook, a tool listed up front is always seen.
const DESCRIPTION = [
  "Updates the topic and workflow phase shown in the user's terminal status line.",
  'Call it when you start working on a task and whenever its phase changes.',
  '- topic: a few words in Czech naming what is being solved (or the feature branch name when nothing better fits); pass it again only when the topic changes.',
  `- phase: one of ${[...PHASES, DONE].join(', ')}. Use "${DONE}" when the task is finished.`,
  'Steps run by feature:* subagents and skills (plan review, E2E, lint, code review, docs, security) are tracked automatically. Do not call it for one-off questions.',
].join('\n')

// Module state: a reload of the module starts the line over, which only matters while
// the mod itself is being edited.
let topic = null
let phase = null
let branch = ''

async function refreshBranch($) {
  const { exitCode, stdout } = await $.process.run(['git', 'branch', '--show-current'])
  branch = exitCode === 0 ? stdout.trim() : ''
}

function show($) {
  const label = topic ?? (BASE_BRANCHES.has(branch) ? null : branch)
  if (label === null && phase === null) {
    $.ui.status(undefined)
    return
  }
  const index = PHASES.indexOf(phase)
  const step =
    phase === null
      ? ''
      : phase === DONE
        ? `✓ ${DONE}`
        : index >= 0
          ? `▸ ${phase} ${index + 1}/${PHASES.length}`
          : `▸ ${phase}`
  $.ui.status([label && `◆ ${label}`, step].filter(Boolean).join('  │  '))
}

export const register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: 'update',
      description: DESCRIPTION,
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Short Czech name of what is being solved' },
          phase: { type: 'string', enum: [...PHASES, DONE] },
        },
      },
      isDeferred: false,
    })
    await refreshBranch($).catch(() => undefined)
    show($)

    return next(e)
  })

  // Reporting a step is not worth a permission prompt.
  on('tool.check', { tool: TOOL }, () => ({ decision: 'allow' })).catch(($, e, next) => next(e))

  on('tool.call', { tool: TOOL }, ($, e) => {
    if (e.topic) topic = e.topic.trim()
    if (e.phase) phase = e.phase
    show($)

    return { result: 'ok' }
  }).catch(() => ({ deny: 'flow-status: status line update failed' }))

  on('tool.call', ($, e, next) => {
    // Only the main loop: a workflow's own agents would report steps of their own.
    if (e.agentId === undefined && (e.tool === 'Agent' || e.tool === 'Skill')) {
      const name = String(e.subagent_type ?? e.skill ?? '')
      const hit = AUTO.find(([pattern]) => pattern.test(name))
      if (hit) {
        // A new /feature:start is a new topic.
        if (hit[1] === 'analyza') topic = null
        phase = hit[1]
        show($)
      }
    }

    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    await refreshBranch($).catch(() => undefined)
    show($)

    return next(e)
  })
}
