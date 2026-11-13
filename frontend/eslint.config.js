import vue from 'eslint-plugin-vue'

export default [
  { ignores: ['dist/**', 'test-results/**', 'playwright-report/**'] },
  {
    files: ['**/*.js', '**/*.vue'],
    rules: {
      'no-unreachable': 'error',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  ...vue.configs['flat/essential'],
]
