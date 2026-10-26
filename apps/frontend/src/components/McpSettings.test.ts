import { describe, expect, it, vi } from 'vitest';

// The component imports the API client, which needs a browser; only the helper is tested.
vi.mock('../services/api', () => ({ api: {}, MCP_URL: 'https://scirm.example.com/mcp' }));

import { claudeCommand } from './McpSettings';

describe('claudeCommand', () => {
  it('builds the Claude Code command for this SCIRM', () => {
    expect(claudeCommand('scirm_AbCd1234_xyz')).toBe(
      'claude mcp add --transport http scirm https://scirm.example.com/mcp --header "Authorization: Bearer scirm_AbCd1234_xyz"');
  });
});
