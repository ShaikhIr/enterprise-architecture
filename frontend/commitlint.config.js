export default {
  extends: ['@commitlint/config-conventional'],
  parserPreset: {
    parserOpts: {
      // Allows an optional ticket prefix, e.g. "PROJ-123: feat(auth): ..."
      headerPattern: /^(?:[A-Z]{2,10}-\d+[^:]*:\s*)?(\w+)(?:\((.+)\))?:\s(.+)$/,
      headerCorrespondence: ['type', 'scope', 'subject'],
    },
  },
  rules: {
    'type-enum': [
      2,
      'always',
      ['feat', 'fix', 'chore', 'docs', 'style', 'refactor', 'perf', 'test', 'build', 'ci'],
    ],
    'header-max-length': [2, 'always', 200],
  },
};
