// Rule Center 页面专用工具：YAML 模板和行内字典/列表格式化
// 与旧 app.js 中 formatYamlText、getNewRuleYaml 行为保持一致，迁移为 TS

export function getNewRuleYaml(): string {
  return [
    'rule_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6"',
    'source_id: "example-source"',
    'version: 1',
    'status: DRAFT',
    'source:',
    '  platform: "example"',
    '  type: "html"',
    '  url: "https://example.com"',
    'list:',
    '  items_path: "css:article"',
    'extract:',
    '  title:',
    '    selector: "h1"',
    '    type: "text"',
    'output:',
    '  fields:',
    '    - "title"',
    '  save_raw: false',
    'governance:',
    '  sanitize: true',
    '',
  ].join('\n');
}

function splitInlineYamlValues(value: string): string[] {
  const values: string[] = [];
  let current = '';
  let quote: string | null = null;
  let nested = 0;
  for (const char of value) {
    if ((char === '"' || char === "'") && !quote) {
      quote = char;
    } else if (char === quote) {
      quote = null;
    } else if (!quote && (char === '[' || char === '{')) {
      nested += 1;
    } else if (!quote && (char === ']' || char === '}')) {
      nested -= 1;
    }

    if (char === ',' && !quote && nested === 0) {
      values.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  if (current.trim()) values.push(current.trim());
  return values;
}

export function formatYamlText(source: string): string {
  const text = String(source || '').replace(/\r\n/g, '\n').trim();
  if (!text) return '';

  const out: string[] = [];
  for (const rawLine of text.split('\n')) {
    const line = rawLine.replace(/\s+$/g, '');
    const objectMatch = line.match(/^(\s*)([^:#][^:]*):\s*\{\s*(.+)\s*\}\s*$/);
    const arrayMatch = line.match(/^(\s*)([^:#][^:]*):\s*\[\s*(.*)\s*\]\s*$/);

    if (objectMatch) {
      const [, indent, key, body] = objectMatch;
      out.push(`${indent}${key.trim()}:`);
      for (const part of splitInlineYamlValues(body)) {
        const pair = part.match(/^([^:]+):\s*(.+)$/);
        if (!pair) throw new Error(`无法格式化字段：${part}`);
        out.push(`${indent}  ${pair[1].trim()}: ${pair[2].trim()}`);
      }
      continue;
    }

    if (arrayMatch) {
      const [, indent, key, body] = arrayMatch;
      out.push(`${indent}${key.trim()}:`);
      for (const item of splitInlineYamlValues(body)) {
        if (item) out.push(`${indent}  - ${item}`);
      }
      continue;
    }

    out.push(line);
  }

  return `${out.join('\n')}\n`;
}
