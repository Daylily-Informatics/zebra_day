from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVATE_SCRIPT = PROJECT_ROOT / "activate"
DEFAULT_VERSION = "5.1.3"
DEFAULT_DEPLOY_NAME = "5-1-3"


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _build_fake_conda(tmp_path: Path) -> Path:
    conda_base = tmp_path / "fake-conda"
    conda_exe = conda_base / "bin" / "conda"

    env_python_script = """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-c" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "pip" && "${3:-}" == "install" ]]; then
  printf '%s\\n' "$*" >> "${FAKE_PIP_LOG}"
  if [[ "${FAKE_ZDAY_PIP_INSTALL_FAIL:-0}" == "1" ]]; then
    exit 1
  fi
  exit 0
fi
exit 0
"""

    for deploy_name in {DEFAULT_DEPLOY_NAME, "abc-12345", "5-1-34567"}:
        env_bin = conda_base / "envs" / f"ZEBRA_DAY-{deploy_name}" / "bin"
        env_bin.mkdir(parents=True, exist_ok=True)
        for tool_name in ("initdb", "pg_ctl"):
            _write_executable(env_bin / tool_name, "#!/usr/bin/env bash\nexit 0\n")
        _write_executable(env_bin / "python", env_python_script)

    _write_executable(
        conda_exe,
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1:-}}" == "info" && "${{2:-}}" == "--base" ]]; then
  printf '%s\\n' "{conda_base}"
  exit 0
fi
if [[ "${{1:-}}" == "info" && "${{2:-}}" == "--envs" ]]; then
  env_name="${{FAKE_ZDAY_ENV_NAME:-ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}}}"
  env_path="{conda_base}/envs/${{env_name}}"
  if [[ "${{FAKE_ZDAY_ENV_PRESENT:-0}}" == "1" ]]; then
    printf '# conda environments:\\n#\\nbase * {conda_base}\\n%s %s\\n' "$env_name" "$env_path"
  else
    printf '# conda environments:\\n#\\nbase * {conda_base}\\n'
  fi
  exit 0
fi
if [[ "${{1:-}}" == "env" && "${{2:-}}" == "create" ]]; then
  printf '%s\\n' "$*" >> "${{FAKE_CONDA_CALL_LOG}}"
  exit 0
fi
if [[ "${{1:-}}" == "env" && "${{2:-}}" == "remove" ]]; then
  printf '%s\\n' "$*" >> "${{FAKE_CONDA_CALL_LOG}}"
  exit 0
fi
if [[ "${{1:-}}" == "install" ]]; then
  printf '%s\\n' "$*" >> "${{FAKE_CONDA_CALL_LOG}}"
  exit 0
fi
printf 'unexpected conda call: %s\\n' "$*" >&2
exit 1
""",
    )

    conda_sh = conda_base / "etc" / "profile.d" / "conda.sh"
    conda_sh.parent.mkdir(parents=True, exist_ok=True)
    conda_sh.write_text(
        f"""conda() {{
  if [[ "${{1:-}}" == "activate" ]]; then
    printf 'activate:%s\\n' "${{2:-}}" >> "${{FAKE_CONDA_CALL_LOG}}"
    export CONDA_DEFAULT_ENV="${{2:-}}"
    export CONDA_PREFIX="{conda_base}/envs/${{2:-}}"
    return 0
  fi
  if [[ "${{1:-}}" == "deactivate" ]]; then
    printf 'deactivate\\n' >> "${{FAKE_CONDA_CALL_LOG}}"
    unset CONDA_DEFAULT_ENV
    unset CONDA_PREFIX
    return 0
  fi
  command "{conda_exe}" "$@"
}}
""",
        encoding="utf-8",
    )

    return conda_base


def _write_fake_python3(tmp_path: Path) -> Path:
    python3_path = tmp_path / "bin" / "python3"
    _write_executable(
        python3_path,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "setuptools_scm" ]]; then
  printf '%s\\n' "${FAKE_ZDAY_VERSION:-5.1.3}"
  exit 0
fi
exit 0
""",
    )
    return python3_path


def _source_activate(
    env: dict[str, str],
    *,
    deploy_name: str | None = None,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    argv = [f"source {shlex.quote(str(ACTIVATE_SCRIPT))}"]
    if deploy_name is not None:
        argv.append(shlex.quote(deploy_name))
    argv.extend(shlex.quote(arg) for arg in extra_args)
    return subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", " ".join(argv)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def test_activate_defaults_deploy_name_from_package_version(tmp_path: Path) -> None:
    conda_base = _build_fake_conda(tmp_path)
    _write_fake_python3(tmp_path)
    conda_log = tmp_path / "conda.log"
    pip_log = tmp_path / "pip.log"

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{conda_base / 'bin'}:/usr/bin:/bin"
    env["FAKE_CONDA_CALL_LOG"] = str(conda_log)
    env["FAKE_PIP_LOG"] = str(pip_log)
    env["FAKE_ZDAY_VERSION"] = DEFAULT_VERSION
    env["FAKE_ZDAY_ENV_PRESENT"] = "0"
    env["FAKE_ZDAY_ENV_NAME"] = f"ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}"
    env.pop("CONDA_DEFAULT_ENV", None)
    env.pop("CONDA_PREFIX", None)

    result = _source_activate(env)

    assert result.returncode == 0
    assert f"Deployment: {DEFAULT_DEPLOY_NAME}" in result.stdout
    assert f"CONDA_DEFAULT_ENV=ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}" in result.stdout
    conda_calls = conda_log.read_text(encoding="utf-8")
    assert f"env create -n ZEBRA_DAY-{DEFAULT_DEPLOY_NAME} -f {PROJECT_ROOT / 'environment.yaml'}" in conda_calls
    assert "env remove" not in conda_calls


def test_activate_rejects_invalid_explicit_deploy_name() -> None:
    result = _source_activate(os.environ.copy(), deploy_name="ab")

    assert result.returncode == 1
    assert "deploy-name must match ^[A-Za-z0-9-]{3,9}$" in result.stdout


def test_activate_accepts_nine_character_hyphenated_deploy_name(tmp_path: Path) -> None:
    conda_base = _build_fake_conda(tmp_path)
    _write_fake_python3(tmp_path)
    conda_log = tmp_path / "conda.log"
    pip_log = tmp_path / "pip.log"

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{conda_base / 'bin'}:/usr/bin:/bin"
    env["FAKE_CONDA_CALL_LOG"] = str(conda_log)
    env["FAKE_PIP_LOG"] = str(pip_log)
    env["FAKE_ZDAY_VERSION"] = DEFAULT_VERSION
    env["FAKE_ZDAY_ENV_PRESENT"] = "0"
    env["FAKE_ZDAY_ENV_NAME"] = "ZEBRA_DAY-abc-12345"
    env.pop("CONDA_DEFAULT_ENV", None)
    env.pop("CONDA_PREFIX", None)

    result = _source_activate(env, deploy_name="abc-12345")

    assert result.returncode == 0
    assert "Deployment: abc-12345" in result.stdout
    assert "deploy-name must match" not in result.stdout
    conda_calls = conda_log.read_text(encoding="utf-8")
    assert f"env create -n ZEBRA_DAY-abc-12345 -f {PROJECT_ROOT / 'environment.yaml'}" in conda_calls


def test_activate_truncates_default_deploy_name_to_nine_chars(tmp_path: Path) -> None:
    conda_base = _build_fake_conda(tmp_path)
    _write_fake_python3(tmp_path)
    conda_log = tmp_path / "conda.log"
    pip_log = tmp_path / "pip.log"

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{conda_base / 'bin'}:/usr/bin:/bin"
    env["FAKE_CONDA_CALL_LOG"] = str(conda_log)
    env["FAKE_PIP_LOG"] = str(pip_log)
    env["FAKE_ZDAY_VERSION"] = "5.1.345678"
    env["FAKE_ZDAY_ENV_PRESENT"] = "0"
    env["FAKE_ZDAY_ENV_NAME"] = "ZEBRA_DAY-5-1-34567"
    env.pop("CONDA_DEFAULT_ENV", None)
    env.pop("CONDA_PREFIX", None)

    result = _source_activate(env)

    assert result.returncode == 0
    assert "Deployment: 5-1-34567" in result.stdout
    conda_calls = conda_log.read_text(encoding="utf-8")
    assert f"env create -n ZEBRA_DAY-5-1-34567 -f {PROJECT_ROOT / 'environment.yaml'}" in conda_calls


def test_activate_cleans_new_env_on_failure(tmp_path: Path) -> None:
    conda_base = _build_fake_conda(tmp_path)
    _write_fake_python3(tmp_path)
    conda_log = tmp_path / "conda.log"
    pip_log = tmp_path / "pip.log"

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{conda_base / 'bin'}:/usr/bin:/bin"
    env["FAKE_CONDA_CALL_LOG"] = str(conda_log)
    env["FAKE_PIP_LOG"] = str(pip_log)
    env["FAKE_ZDAY_VERSION"] = DEFAULT_VERSION
    env["FAKE_ZDAY_ENV_PRESENT"] = "0"
    env["FAKE_ZDAY_ENV_NAME"] = f"ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}"
    env["FAKE_ZDAY_PIP_INSTALL_FAIL"] = "1"
    env.pop("CONDA_DEFAULT_ENV", None)
    env.pop("CONDA_PREFIX", None)

    result = _source_activate(env)

    assert result.returncode == 1
    assert "zebra_day activation failed" in result.stdout
    assert f"Removed newly created env ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}." in result.stdout
    conda_calls = conda_log.read_text(encoding="utf-8")
    assert f"env create -n ZEBRA_DAY-{DEFAULT_DEPLOY_NAME} -f {PROJECT_ROOT / 'environment.yaml'}" in conda_calls
    assert f"env remove -y -n ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}" in conda_calls
    assert "deactivate" in conda_calls


def test_activate_debug_preserves_new_env_on_failure(tmp_path: Path) -> None:
    conda_base = _build_fake_conda(tmp_path)
    _write_fake_python3(tmp_path)
    conda_log = tmp_path / "conda.log"
    pip_log = tmp_path / "pip.log"

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{conda_base / 'bin'}:/usr/bin:/bin"
    env["FAKE_CONDA_CALL_LOG"] = str(conda_log)
    env["FAKE_PIP_LOG"] = str(pip_log)
    env["FAKE_ZDAY_VERSION"] = DEFAULT_VERSION
    env["FAKE_ZDAY_ENV_PRESENT"] = "0"
    env["FAKE_ZDAY_ENV_NAME"] = f"ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}"
    env["FAKE_ZDAY_PIP_INSTALL_FAIL"] = "1"
    env.pop("CONDA_DEFAULT_ENV", None)
    env.pop("CONDA_PREFIX", None)

    result = _source_activate(env, extra_args=("--debug",))

    assert result.returncode == 1
    assert "--debug was passed" in result.stdout
    conda_calls = conda_log.read_text(encoding="utf-8")
    assert f"env create -n ZEBRA_DAY-{DEFAULT_DEPLOY_NAME} -f {PROJECT_ROOT / 'environment.yaml'}" in conda_calls
    assert "env remove" not in conda_calls


def test_activate_does_not_delete_preexisting_env_and_restores_previous_env(tmp_path: Path) -> None:
    conda_base = _build_fake_conda(tmp_path)
    _write_fake_python3(tmp_path)
    conda_log = tmp_path / "conda.log"
    pip_log = tmp_path / "pip.log"

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{conda_base / 'bin'}:/usr/bin:/bin"
    env["FAKE_CONDA_CALL_LOG"] = str(conda_log)
    env["FAKE_PIP_LOG"] = str(pip_log)
    env["FAKE_ZDAY_VERSION"] = DEFAULT_VERSION
    env["FAKE_ZDAY_ENV_PRESENT"] = "1"
    env["FAKE_ZDAY_ENV_NAME"] = f"ZEBRA_DAY-{DEFAULT_DEPLOY_NAME}"
    env["FAKE_ZDAY_PIP_INSTALL_FAIL"] = "1"
    env["CONDA_DEFAULT_ENV"] = "BASEDEV"
    env["CONDA_PREFIX"] = str(conda_base / "envs" / "BASEDEV")

    result = _source_activate(env)

    assert result.returncode == 1
    assert "target env existed before activation" in result.stdout
    assert "Restored previous conda env BASEDEV." in result.stdout
    conda_calls = conda_log.read_text(encoding="utf-8")
    assert "env create" not in conda_calls
    assert "env remove" not in conda_calls
    assert "activate:BASEDEV" in conda_calls
