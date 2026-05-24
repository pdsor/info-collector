"""Rule Center 前端编辑器静态行为测试。"""

import json
import os
import subprocess
import textwrap


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
APP_JS = os.path.join(ROOT, "APP/dashboard/static/js/app.js")


def run_app_js_probe(probe):
    """在 Node VM 中加载真实前端脚本并执行探针代码。"""
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(APP_JS)}, 'utf8');
const context = {{
  console,
  API: {{}},
  Vue: {{
    createApp: () => ({{ component() {{}}, mount() {{}} }}),
    ref: (value) => ({{ value }}),
    computed: (fn) => ({{ value: fn() }}),
    onMounted: () => {{}},
    onUnmounted: () => {{}}
  }}
}};
vm.createContext(context);
vm.runInContext(code + '\\n' + {json.dumps(probe)}, context);
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_new_rule_yaml_uses_readable_rule_v2_layout():
    """新建规则模板应使用可读的 Rule v2 分层 YAML。"""
    probe = textwrap.dedent(
        """
        const yaml = getNewRuleYaml();
        console.log(JSON.stringify({
          yaml,
          hasSource: yaml.includes('\\nsource:\\n  platform: "example"\\n  type: "html"'),
          hasExtractBlock: yaml.includes('\\nextract:\\n  title:\\n    selector: "h1"\\n    type: "text"'),
          hasOutputFields: yaml.includes('\\noutput:\\n  fields:\\n    - "title"\\n  save_raw: false')
        }));
        """
    )

    payload = run_app_js_probe(probe)

    assert payload["hasSource"] is True
    assert payload["hasExtractBlock"] is True
    assert payload["hasOutputFields"] is True
    assert "{ selector:" not in payload["yaml"]


def test_format_yaml_text_expands_common_inline_yaml():
    """格式化按钮使用的函数应展开常见行内对象和数组。"""
    probe = textwrap.dedent(
        """
        const source = [
          'extract:',
          '  title: { selector: "h1", type: "text" }',
          'output:',
          '  fields: ["title", "url"]',
          '  save_raw: false'
        ].join('\\n');
        const yaml = formatYamlText(source);
        console.log(JSON.stringify({
          yaml,
          expandedObject: yaml.includes('  title:\\n    selector: "h1"\\n    type: "text"'),
          expandedArray: yaml.includes('  fields:\\n    - "title"\\n    - "url"'),
          endsWithNewline: yaml.endsWith('\\n')
        }));
        """
    )

    payload = run_app_js_probe(probe)

    assert payload["expandedObject"] is True
    assert payload["expandedArray"] is True
    assert payload["endsWithNewline"] is True


def test_rule_center_template_exposes_format_button():
    """Rule Center 工具栏应提供格式化按钮。"""
    probe = textwrap.dedent(
        """
        console.log(JSON.stringify({
          hasButton: RuleCenter.template.includes('格式化'),
          hasHandler: RuleCenter.template.includes('@click="formatRuleYaml"')
        }));
        """
    )

    payload = run_app_js_probe(probe)

    assert payload["hasButton"] is True
    assert payload["hasHandler"] is True
