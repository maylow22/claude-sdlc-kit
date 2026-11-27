export const meta = {
  name: 'code-review',
  description: 'Review of a feature branch diff through three lenses, every serious finding refuted',
  whenToUse: 'Run by step 7 of /feature:start. args: {brief, baseBranch, branch} — brief holds the task, the approved plan and the branches, nothing about how development went.',
  phases: [
    { title: 'Review', detail: 'feature:reviewer over three lenses at once' },
    { title: 'Verify', detail: 'an independent agent tries to refute every blocker and major' },
  ],
}

const LENSES = [
  ['bugs', 'Correctness. Run the `code-review` skill over the diff and hunt for real bugs — wrong behavior, unhandled states, broken contracts.'],
  ['simplify', 'Quality through the lens of the `simplify` skill: duplication, dead code, needless abstraction, unrequested configurability, mismatch with the surrounding style.'],
  ['scope', 'The diff against the task and the approved plan: does it solve what it was meant to, did it add more than the plan called for, is anything the plan promised missing?'],
]

// A different model family misses different things. Opt-in only (`--codex`), because the diff
// leaves for OpenAI — something a client repo may not allow.
const CODEX_PROMPT =
  `Run an independent code review with the Codex CLI and return its report. You do not review ` +
  `the code yourself and you change nothing.\n\n` +
  `1. Find the binary — the first of these whose \`--version\` succeeds: \`$CODEX_BIN\`, \`codex\` on PATH, ` +
  `\`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex\`.\n` +
  `2. Write everything below the line "For Codex:" to a temp file and, from the repository root, run ` +
  `(Bash timeout 600000):\n` +
  // Not `codex exec review --base`: that mode refuses a custom prompt, and Codex should see the task and the plan.
  `   \`"$CODEX" exec -s read-only --ephemeral -o <out file> - < <prompt file>\`\n` +
  `3. Return the contents of <out file> verbatim. If no binary answers or the run fails, return ` +
  `one line, \`CODEX UNAVAILABLE: <reason>\`, and nothing else — do not fall back to reviewing yourself.\n\n` +
  `For Codex:\n\n${args.brief}\n\n` +
  `Review that diff for real bugs, broken contracts, and anything the task asked for that is missing or ` +
  `exceeded. Report each finding as: severity (blocker | major | minor) · file:line · what is wrong · why. ` +
  `Change no files.`

const lenses = args.codex ? [...LENSES, ['codex', null]] : LENSES

const VERDICTS = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          finding: { type: 'string', description: 'the finding as the report states it, one line' },
          refuted: { type: 'boolean', description: 'true = does not hold against the real code' },
          why: { type: 'string', description: 'what you read and what it showed' },
        },
        required: ['finding', 'refuted', 'why'],
      },
    },
  },
  required: ['verdicts'],
}

const out = await pipeline(
  lenses,
  ([key, lens]) =>
    key === 'codex'
      ? agent(CODEX_PROMPT, { label: 'review:codex', phase: 'Review' })
      : agent(`${args.brief}\n\nYour lens for this review: ${lens}`, {
          agentType: 'feature:reviewer',
          label: `review:${key}`,
          phase: 'Review',
        }),
  (report, [key]) =>
    report &&
    (report.startsWith('CODEX UNAVAILABLE') ? { key, report, verdicts: { verdicts: [] } } :
    agent(
      `A review report on the diff of ${args.branch} against ${args.baseBranch} follows.\n\n${report}\n\n` +
        `Take every blocker and major finding and try to REFUTE it against the real code — open the files, ` +
        `read them whole, follow the call sites. Mark refuted:true whenever you cannot reproduce the problem from the code.`,
      { label: `verify:${key}`, phase: 'Verify', schema: VERDICTS },
    ).then((verdicts) => ({ key, report, verdicts }))),
)

return out.filter(Boolean)
