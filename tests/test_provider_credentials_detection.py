from pathlib import Path
import ast


CORE_PATH = Path(__file__).resolve().parents[1] / "src" / "core.py"


def test_core_has_placeholder_secret_filter():
    text = CORE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    placeholders = None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_PLACEHOLDER_SECRET_VALUES"
            and isinstance(node.value, ast.Set)
        ):
            placeholders = {
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
            break

    assert placeholders is not None
    assert {"", "your_key_here", "your_token_here", "none", "null", "changeme"} <= placeholders


def test_gigachat_checks_use_sanitized_secret_reader():
    text = CORE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    secret_calls = {
        node.args[0].value
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_read_secret_env"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        )
    }
    assert {"GIGACHAT_ACCESS_TOKEN", "GIGACHAT_CLIENT_ID", "GIGACHAT_CLIENT_SECRET"} <= secret_calls


def test_yandex_checks_use_sanitized_secret_reader():
    text = CORE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    secret_calls = {
        node.args[0].value
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_read_secret_env"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        )
    }
    assert {"YANDEX_IAM_TOKEN", "YANDEX_FOLDER_ID"} <= secret_calls
