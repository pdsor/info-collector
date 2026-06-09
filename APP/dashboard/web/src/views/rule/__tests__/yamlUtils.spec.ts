import { describe, it, expect } from 'vitest';
import { formatYamlText, getNewRuleYaml } from '@/views/rule/yamlUtils';

describe('formatYamlText', () => {
  it('保留普通 YAML 行不变', () => {
    const input = 'rule_id: "abc"\nversion: 1\n';
    const out = formatYamlText(input);
    expect(out).toBe('rule_id: "abc"\nversion: 1\n');
  });

  it('展开行内对象语法', () => {
    const input = 'extract:\n  title: { selector: "h1", type: "text" }\n';
    const out = formatYamlText(input);
    expect(out).toContain('  title:');
    expect(out).toContain('    selector: "h1"');
    expect(out).toContain('    type: "text"');
  });

  it('展开行内数组语法', () => {
    const input = 'output:\n  fields: ["title", "url"]\n';
    const out = formatYamlText(input);
    expect(out).toContain('  fields:');
    expect(out).toContain('    - "title"');
    expect(out).toContain('    - "url"');
  });

  it('getNewRuleYaml 返回合法骨架', () => {
    const yaml = getNewRuleYaml();
    expect(yaml).toContain('rule_id:');
    expect(yaml).toContain('source:');
    expect(yaml).toContain('extract:');
    expect(yaml).toContain('governance:');
  });
});
