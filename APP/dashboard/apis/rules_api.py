import subprocess
import json
import os
from flask import Blueprint, request, jsonify

rules_bp = Blueprint("rules", __name__)

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine")
VENV_PYTHON = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
ENGINE_CLI = os.path.join(ENGINE_DIR, "engine_cli.py")


def run_engine_cli(args: list) -> tuple:
    """Run engine_cli.py with given arguments, return (stdout, stderr, returncode)."""
    cmd = [VENV_PYTHON, ENGINE_CLI] + args
    result = subprocess.run(
        cmd,
        cwd=ENGINE_DIR,
        capture_output=True,
        text=True,
    )
    return result.stdout, result.stderr, result.returncode


@rules_bp.route("", methods=["GET"])
def list_rules():
    """GET /api/rules - List all rules."""
    stdout, stderr, code = run_engine_cli(["list-rules", "--format=json"])
    if code != 0:
        return jsonify({"error": stderr or "Failed to list rules"}), 500
    try:
        data = json.loads(stdout)
        return jsonify(data)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from engine_cli", "raw": stdout}), 500


@rules_bp.route("/<path:rule_path>", methods=["GET"])
def get_rule(rule_path):
    """GET /api/rules/<path> - Get rule YAML content."""
    # rule_path is already URL decoded by Flask
    stdout, stderr, code = run_engine_cli(["get-rule", rule_path, "--format=json"])
    if code != 0:
        return jsonify({"error": stderr or "Rule not found"}), 404
    try:
        data = json.loads(stdout)
        return jsonify(data)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from engine_cli", "raw": stdout}), 500


@rules_bp.route("", methods=["POST"])
def create_rule():
    """POST /api/rules - Create or update a rule."""
    body = request.get_json()
    if not body:
        return jsonify({"error": "Missing JSON body"}), 400
    path = body.get("path")
    yaml_content = body.get("yaml")
    if not path or yaml_content is None:
        return jsonify({"error": "Missing 'path' or 'yaml' field"}), 400

    # Escape yaml_content for shell (simple approach - pass via stdin not available in subprocess here)
    # Use environment or a temp file approach; for now pass directly
    stdout, stderr, code = run_engine_cli(["put-rule", path, "--yaml-content", yaml_content])
    if code != 0:
        return jsonify({"error": stderr or "Failed to save rule"}), 500
    try:
        data = json.loads(stdout)
        return jsonify(data)
    except json.JSONDecodeError:
        return jsonify({"success": True})


@rules_bp.route("/<path:rule_path>", methods=["DELETE"])
def delete_rule(rule_path):
    """DELETE /api/rules/<path> - Delete a rule."""
    stdout, stderr, code = run_engine_cli(["delete-rule", rule_path])
    if code != 0:
        return jsonify({"error": stderr or "Failed to delete rule"}), 500
    try:
        data = json.loads(stdout)
        return jsonify(data)
    except json.JSONDecodeError:
        return jsonify({"success": True})


@rules_bp.route("/<path:rule_path>/toggle", methods=["POST"])
def toggle_rule(rule_path):
    """POST /api/rules/<path>/toggle - Enable or disable a rule."""
    body = request.get_json()
    if body is None:
        return jsonify({"error": "Missing JSON body"}), 400
    enabled = body.get("enabled")
    if enabled is None:
        return jsonify({"error": "Missing 'enabled' field"}), 400

    enable_str = "true" if enabled else "false"
    stdout, stderr, code = run_engine_cli(["enable-rule", rule_path, "--enable=" + enable_str])
    if code != 0:
        return jsonify({"error": stderr or "Failed to toggle rule"}), 500
    try:
        data = json.loads(stdout)
        return jsonify(data)
    except json.JSONDecodeError:
        return jsonify({"success": True, "enabled": enabled})


@rules_bp.route("/<path:rule_path>/run", methods=["POST"])
def run_rule(rule_path):
    """POST /api/rules/<path>/run - Execute a rule immediately."""
    stdout, stderr, code = run_engine_cli(["run-rule", rule_path, "--format=json"])
    if code != 0:
        return jsonify({"error": stderr or "Failed to run rule"}), 500
    try:
        data = json.loads(stdout)
        return jsonify(data)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from engine_cli", "raw": stdout}), 500
