#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


EXPECTED_HEALTH = {"service": "bedtime", "status": "ok"}
EXPECTED_H1 = "Bedtime Lights API Docs"
EXPECTED_H2 = "GET /health"
EXPECTED_PRE = '{"service": "bedtime", "status": "ok"}'
EXPECTED_OPENAPI_HREF = "/openapi.json"
FAKE_TOKEN = "verify-bedtime-token"
READY_LOG_LINE = "Bedtime lights watcher started"
SCRATCH_ROOT = Path("/tmp/verify-bedtime")
DEFAULT_INSTANCE = SCRATCH_ROOT / "instance.json"
DEFAULT_EVIDENCE = Path("/opt/cursor/artifacts/verify-bedtime")
CHROME_BINS = (
    "/opt/google/chrome/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
)
DRIVE_PROOF_NAMES = (
    "health.request.txt",
    "health.headers.txt",
    "health.response.txt",
    "docs.request.txt",
    "docs.headers.txt",
    "docs.response.txt",
    "docs.dom.html",
    "docs.ui.txt",
    "docs.screenshot.png",
    "docs.screenshot.blocked.txt",
    "openapi.request.txt",
    "openapi.headers.txt",
    "openapi.response.txt",
    "drive.json",
)


@dataclass
class Instance:
    run_id: str
    repo_root: str
    python: str
    scratch_dir: str
    evidence_dir: str
    instance_path: str
    base_url: str
    service_port: int
    ha_url: str
    ha_port: int
    config_path: str
    state_path: str
    state_dir: str
    service_pid: int
    standin_pid: int
    service_log: str
    standin_log: str
    started_at: str


@dataclass(frozen=True)
class DocsView:
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    pre: tuple[str, ...]
    links: tuple[tuple[str, str], ...]
    ok: bool


class DocsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._tag: str | None = None
        self._href: str = ""
        self._buf: list[str] = []
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.pre: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "pre"}:
            self._tag = tag
            self._buf = []
            return
        if tag == "a":
            self._tag = "a"
            self._href = dict(attrs).get("href") or ""
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag != self._tag:
            return
        text = "".join(self._buf).strip()
        if tag == "h1":
            self.h1.append(text)
        elif tag == "h2":
            self.h2.append(text)
        elif tag == "pre":
            self.pre.append(text)
        elif tag == "a":
            self.links.append((self._href, text))
        self._tag = None

    def handle_data(self, data: str) -> None:
        if self._tag is not None:
            self._buf.append(data)


def parse_docs_html(html: str) -> DocsView:
    parser = DocsParser()
    parser.feed(html)
    links = tuple(parser.links)
    ok = (
        EXPECTED_H1 in parser.h1
        and EXPECTED_H2 in parser.h2
        and EXPECTED_PRE in parser.pre
        and any(href == EXPECTED_OPENAPI_HREF and text == EXPECTED_OPENAPI_HREF for href, text in links)
    )
    return DocsView(
        h1=tuple(parser.h1),
        h2=tuple(parser.h2),
        pre=tuple(parser.pre),
        links=links,
        ok=ok,
    )


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for path in [here, *here.parents]:
        pyproject = path / "pyproject.toml"
        if pyproject.is_file() and 'name = "bedtime-lights"' in pyproject.read_text(encoding="utf-8"):
            return path
    raise SystemExit("could not find the bedtime-lights repo root")


def require_project_deps() -> None:
    try:
        import aiohttp  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        raise SystemExit(
            "missing project deps; run ./.venv/bin/python -m pip install -e '.[dev]' "
            "and invoke this script with ./.venv/bin/python"
        )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def save_instance(instance: Instance) -> None:
    payload = asdict(instance)
    atomic_write_json(Path(instance.instance_path), payload)
    atomic_write_json(Path(instance.evidence_dir) / "instance.json", payload)


def load_instance(path: Path) -> Instance:
    if not path.is_file():
        raise SystemExit(f"no instance file at {path}; run launch")
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return Instance(**raw)
    except TypeError as exc:
        raise SystemExit(f"instance file is missing fields: {exc}") from exc


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return Path(f"/proc/{pid}").exists()


def pid_running(pid: int) -> bool:
    if not pid_alive(pid):
        return False
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.is_file():
        return False
    try:
        state = stat_path.read_text(encoding="utf-8").rsplit(")", 1)[-1].split()[0]
    except OSError:
        return False
    return state not in {"Z", "X"}


def pid_cmdline(pid: int) -> str:
    path = Path(f"/proc/{pid}/cmdline")
    if not path.is_file():
        return ""
    return path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def pid_environ(pid: int) -> dict[str, str]:
    path = Path(f"/proc/{pid}/environ")
    if not path.is_file():
        return {}
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    env: dict[str, str] = {}
    for item in raw.split(b"\x00"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        env[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return env


def pid_cwd(pid: int) -> str:
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return ""


def pid_listens_on_port(pid: int, port: int) -> bool:
    inodes: set[str] = set()
    fd_dir = Path(f"/proc/{pid}/fd")
    if not fd_dir.is_dir():
        return False
    for entry in fd_dir.iterdir():
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if target.startswith("socket:[") and target.endswith("]"):
            inodes.add(target[len("socket:[") : -1])
    needle = f"{port:04X}"
    for table in (Path(f"/proc/{pid}/net/tcp"), Path(f"/proc/{pid}/net/tcp6")):
        if not table.is_file():
            continue
        for line in table.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 10:
                continue
            local, state, inode = parts[1], parts[3], parts[9]
            if state != "0A":
                continue
            local_port = local.rsplit(":", 1)[-1].upper()
            if local_port == needle and inode in inodes:
                return True
    return False


def is_our_service(pid: int, instance: Instance) -> bool:
    if not pid_running(pid):
        return False
    tokens = pid_cmdline(pid).split()
    if "bedtime_lights.main" not in tokens:
        return False
    env = pid_environ(pid)
    return (
        env.get("CONFIG_PATH") == instance.config_path
        and env.get("SERVICE_PORT") == str(instance.service_port)
        and env.get("STATE_PATH") == instance.state_path
    )


def is_our_standin(pid: int, instance: Instance) -> bool:
    if not pid_running(pid):
        return False
    tokens = pid_cmdline(pid).split()
    if "standin" not in tokens or instance.config_path not in tokens:
        return False
    try:
        port_index = tokens.index("--port")
        return tokens[port_index + 1] == str(instance.ha_port)
    except (ValueError, IndexError):
        return False


def scratch_is_deletable(scratch: Path) -> bool:
    root = SCRATCH_ROOT.resolve()
    try:
        resolved = scratch.resolve()
    except OSError:
        return False
    if resolved == root:
        return False
    return resolved.is_relative_to(root)


def header_map(headers: object) -> dict[str, str]:
    if headers is None:
        return {}
    items = getattr(headers, "items", None)
    if items is None:
        return {}
    return {str(key).lower(): str(value) for key, value in items()}


def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
    request = Request(url, method="GET", headers={"Accept": "*/*", "User-Agent": "verify-bedtime"})
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read()
            return int(response.status), header_map(response.headers), body
    except HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        return int(exc.code), header_map(exc.headers), body


def write_http_evidence(evidence_dir: Path, name: str, url: str, status: int, headers: dict[str, str], body: bytes) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"{name}.request.txt").write_text(f"GET {url}\n", encoding="utf-8")
    header_lines = "\n".join(f"{key}: {value}" for key, value in sorted(headers.items()))
    (evidence_dir / f"{name}.headers.txt").write_text(f"status: {status}\n{header_lines}\n", encoding="utf-8")
    (evidence_dir / f"{name}.response.txt").write_text(body.decode("utf-8", "replace"), encoding="utf-8")


def reset_drive_proof(evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for name in DRIVE_PROOF_NAMES:
        path = evidence_dir / name
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def copy_logs(instance: Instance) -> None:
    evidence = Path(instance.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    for src_name, dest_name in (
        (instance.service_log, "service.log"),
        (instance.standin_log, "standin.log"),
    ):
        src = Path(src_name)
        if src.is_file():
            (evidence / dest_name).write_bytes(src.read_bytes())


def states_from_config(config_path: Path) -> list[dict[str, str]]:
    import yaml

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{config_path} must be a mapping")
    pixel = raw.get("pixel") or {}
    action = raw.get("action") or {}
    return [
        {"entity_id": str(pixel["battery_state_entity"]), "state": "discharging"},
        {"entity_id": str(pixel["charger_type_entity"]), "state": "none"},
        {"entity_id": str(action["script_entity"]), "state": "off"},
    ]


def terminate_pid(pid: int) -> None:
    if not pid_running(pid):
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline:
        if not pid_running(pid):
            return
        time.sleep(0.1)
    if pid_running(pid):
        os.kill(pid, signal.SIGKILL)


def remove_live_instance(instance: Instance) -> bool:
    live = Path(instance.instance_path).resolve()
    evidence_copy = (Path(instance.evidence_dir) / "instance.json").resolve()
    if live == evidence_copy:
        return False
    try:
        live.unlink()
        return True
    except FileNotFoundError:
        return False


def cmd_cleanup(instance_path: Path, *, quiet: bool = False) -> int:
    if not instance_path.is_file():
        if not quiet:
            print(json.dumps({"ok": True, "cleaned": False, "reason": f"no instance at {instance_path}"}))
        return 0
    instance = load_instance(instance_path)
    copy_logs(instance)
    signaled: list[int] = []
    skipped: list[dict[str, object]] = []
    leftover: list[int] = []
    for kind, pid, owned in (
        ("service", instance.service_pid, is_our_service),
        ("standin", instance.standin_pid, is_our_standin),
    ):
        if pid <= 0 or not pid_running(pid):
            skipped.append({"pid": pid, "kind": kind, "reason": "not running"})
            continue
        if not owned(pid, instance):
            skipped.append({"pid": pid, "kind": kind, "reason": "not this run"})
            continue
        try:
            terminate_pid(pid)
        except OSError as exc:
            skipped.append({"pid": pid, "kind": kind, "reason": str(exc)})
            continue
        signaled.append(pid)
        if pid_running(pid):
            leftover.append(pid)
    copy_logs(instance)
    scratch = Path(instance.scratch_dir)
    scratch_deleted = False
    if scratch_is_deletable(scratch) and scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
        scratch_deleted = not scratch.exists()
    instance_removed = leftover == [] and remove_live_instance(instance)
    report = {
        "ok": leftover == [],
        "signaled": signaled,
        "skipped": skipped,
        "leftover_pids": leftover,
        "scratch_deleted": scratch_deleted,
        "instance_removed": instance_removed,
    }
    if not quiet:
        print(json.dumps(report, sort_keys=True))
    return 0 if leftover == [] else 1


def wait_ready(
    instance: Instance,
    service: subprocess.Popen,
    standin: subprocess.Popen,
    timeout: float,
) -> None:
    health_url = f"{instance.base_url}/health"
    deadline = time.time() + timeout
    last_error = "not ready"
    while time.time() < deadline:
        standin_code = standin.poll()
        if standin_code is not None:
            log = Path(instance.standin_log).read_text(encoding="utf-8", errors="replace")
            raise SystemExit(f"stand-in pid {instance.standin_pid} exited {standin_code}\n{log}")
        service_code = service.poll()
        if service_code is not None:
            log = Path(instance.service_log).read_text(encoding="utf-8", errors="replace")
            raise SystemExit(f"service pid {instance.service_pid} exited {service_code}\n{log}")
        log_text = Path(instance.service_log).read_text(encoding="utf-8", errors="replace")
        try:
            status, _, body = http_get(health_url)
            payload = json.loads(body.decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
            time.sleep(0.1)
            continue
        if status == 200 and payload == EXPECTED_HEALTH and READY_LOG_LINE in log_text:
            return
        last_error = f"status={status} payload={payload!r} ready_log={READY_LOG_LINE in log_text}"
        time.sleep(0.1)
    raise SystemExit(f"timed out waiting for ready service: {last_error}")


def process_pythonpath(root: Path) -> str:
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        return f"{root}{os.pathsep}{existing}"
    return str(root)


def cmd_launch(instance_path: Path, evidence_dir: Path) -> int:
    require_project_deps()
    if instance_path.is_file():
        cmd_cleanup(instance_path, quiet=True)
    root = repo_root()
    python = Path(sys.executable)
    example = root / "config.example.yaml"
    if not example.is_file():
        raise SystemExit(f"missing {example}")
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="run-", dir=str(SCRATCH_ROOT)))
    run_id = scratch.name
    state_dir = scratch / "state"
    state_dir.mkdir()
    config_path = scratch / "config.yaml"
    config_path.write_bytes(example.read_bytes())
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ha_port = free_port()
    service_port = free_port()
    standin_log = scratch / "standin.log"
    service_log = scratch / "service.log"
    script = Path(__file__).resolve()
    standin_out = standin_log.open("w", encoding="utf-8")
    standin = subprocess.Popen(
        [
            str(python),
            str(script),
            "standin",
            "--host",
            "127.0.0.1",
            "--port",
            str(ha_port),
            "--config",
            str(config_path),
            "--token",
            FAKE_TOKEN,
        ],
        stdout=standin_out,
        stderr=subprocess.STDOUT,
        cwd=str(scratch),
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": process_pythonpath(root)},
        start_new_session=True,
    )
    instance = Instance(
        run_id=run_id,
        repo_root=str(root),
        python=str(python),
        scratch_dir=str(scratch),
        evidence_dir=str(evidence_dir),
        instance_path=str(instance_path),
        base_url=f"http://127.0.0.1:{service_port}",
        service_port=service_port,
        ha_url=f"http://127.0.0.1:{ha_port}",
        ha_port=ha_port,
        config_path=str(config_path),
        state_path=str(state_dir / "state.json"),
        state_dir=str(state_dir),
        service_pid=0,
        standin_pid=standin.pid,
        service_log=str(service_log),
        standin_log=str(standin_log),
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    save_instance(instance)
    service: subprocess.Popen | None = None
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            code = standin.poll()
            if code is not None:
                raise SystemExit(
                    f"stand-in exited {code}\n{standin_log.read_text(encoding='utf-8', errors='replace')}"
                )
            if standin_log.is_file() and "ha standin listening" in standin_log.read_text(
                encoding="utf-8", errors="replace"
            ):
                break
            time.sleep(0.05)
        else:
            raise SystemExit(
                f"stand-in did not listen\n{standin_log.read_text(encoding='utf-8', errors='replace')}"
            )

        env = os.environ.copy()
        env.update(
            {
                "HA_URL": instance.ha_url,
                "HA_LONG_LIVED_TOKEN": FAKE_TOKEN,
                "HOMELAB_FUNCTIONS_URL": "http://127.0.0.1:9",
                "HOMELAB_FUNCTIONS_TOKEN": "verify-unused",
                "TZ": "America/New_York",
                "LOG_LEVEL": "INFO",
                "CONFIG_PATH": instance.config_path,
                "STATE_PATH": instance.state_path,
                "RECONCILE_SECONDS": "3600",
                "SERVICE_PORT": str(service_port),
                "DRY_RUN": "true",
                "PYTHONUNBUFFERED": "1",
                "PYTHONPATH": process_pythonpath(root),
            }
        )
        service_out = service_log.open("w", encoding="utf-8")
        service = subprocess.Popen(
            [str(python), "-m", "bedtime_lights.main"],
            stdout=service_out,
            stderr=subprocess.STDOUT,
            cwd=str(scratch),
            env=env,
            start_new_session=True,
        )
        instance.service_pid = service.pid
        save_instance(instance)
        wait_ready(instance, service, standin, timeout=20)
    except BaseException:
        copy_logs(instance)
        cmd_cleanup(instance_path, quiet=True)
        raise
    copy_logs(instance)
    print(json.dumps(asdict(instance), indent=2, sort_keys=True))
    return 0


def doctor_problems(instance: Instance) -> list[str]:
    problems: list[str] = []
    if not pid_running(instance.service_pid):
        problems.append(f"service pid {instance.service_pid} is not running")
    elif not is_our_service(instance.service_pid, instance):
        problems.append(
            f"service pid {instance.service_pid} does not match this run's CONFIG_PATH, STATE_PATH, and SERVICE_PORT"
        )
    if not pid_running(instance.standin_pid):
        problems.append(f"stand-in pid {instance.standin_pid} is not running")
    elif not is_our_standin(instance.standin_pid, instance):
        problems.append(
            f"stand-in pid {instance.standin_pid} does not match this run's config path and HA port"
        )
    if pid_running(instance.service_pid) and not pid_listens_on_port(
        instance.service_pid, instance.service_port
    ):
        problems.append(
            f"service pid {instance.service_pid} does not own TCP port {instance.service_port}"
        )
    try:
        status, headers, body = http_get(f"{instance.base_url}/health")
        payload = json.loads(body.decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        problems.append(f"/health request failed: {exc}")
        return problems
    if status != 200:
        problems.append(f"/health status {status}")
    if payload != EXPECTED_HEALTH:
        problems.append(f"/health body {payload!r} != {EXPECTED_HEALTH!r}")
    content_type = headers.get("content-type", "")
    if "application/json" not in content_type:
        problems.append(f"/health content-type {content_type!r}")
    service_log_path = Path(instance.service_log)
    if not service_log_path.is_file():
        problems.append(f"service log missing at {service_log_path}")
    elif READY_LOG_LINE not in service_log_path.read_text(encoding="utf-8", errors="replace"):
        problems.append(f"service log missing {READY_LOG_LINE!r}")
    standin_log_path = Path(instance.standin_log)
    if not standin_log_path.is_file():
        problems.append(f"stand-in log missing at {standin_log_path}")
    elif "type=get_states" not in standin_log_path.read_text(encoding="utf-8", errors="replace"):
        problems.append("stand-in log missing get_states")
    return problems


def cmd_doctor(instance_path: Path) -> int:
    instance = load_instance(instance_path)
    copy_logs(instance)
    problems = doctor_problems(instance)
    env = pid_environ(instance.service_pid) if pid_running(instance.service_pid) else {}
    report = {
        "ok": not problems,
        "run_id": instance.run_id,
        "repo_root": instance.repo_root,
        "python": instance.python,
        "service_cmdline": pid_cmdline(instance.service_pid),
        "service_cwd": pid_cwd(instance.service_pid),
        "environ_config_path": env.get("CONFIG_PATH"),
        "environ_service_port": env.get("SERVICE_PORT"),
        "base_url": instance.base_url,
        "service_pid": instance.service_pid,
        "standin_pid": instance.standin_pid,
        "service_port": instance.service_port,
        "problems": problems,
        "expected_health": EXPECTED_HEALTH,
    }
    Path(instance.evidence_dir).mkdir(parents=True, exist_ok=True)
    (Path(instance.evidence_dir) / "doctor.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not problems else 1


def chrome_bin() -> str | None:
    for path in CHROME_BINS:
        if Path(path).is_file() and os.access(path, os.X_OK):
            return path
    from shutil import which

    for name in ("chromium", "chromium-browser"):
        found = which(name)
        if found:
            return found
    return None


def _chrome_args(chrome: str, profile: Path) -> list[str]:
    return [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--window-size=1280,900",
        f"--user-data-dir={profile}",
    ]


def capture_docs_browser(instance: Instance, evidence_dir: Path) -> dict:
    url = f"{instance.base_url}/docs"
    screenshot = evidence_dir / "docs.screenshot.png"
    tmp_shot = evidence_dir / f"docs.screenshot.{instance.run_id}.png"
    dom_path = evidence_dir / "docs.dom.html"
    ui_path = evidence_dir / "docs.ui.txt"
    if screenshot.is_file():
        screenshot.unlink()
    if tmp_shot.is_file():
        tmp_shot.unlink()
    chrome = chrome_bin()
    shot_profile = Path(instance.scratch_dir) / "chrome-profile-shot"
    dump_profile = Path(instance.scratch_dir) / "chrome-profile-dump"
    screenshot_cmd = _chrome_args(chrome or "/usr/bin/google-chrome-stable", shot_profile) + [
        f"--screenshot={tmp_shot}",
        url,
    ]
    dump_cmd = _chrome_args(chrome or "/usr/bin/google-chrome-stable", dump_profile) + ["--dump-dom", url]
    if chrome is None:
        blocked = {
            "ok": False,
            "url": url,
            "command": screenshot_cmd,
            "blocker": "no Chrome binary at the helper lookup paths",
        }
        (evidence_dir / "docs.screenshot.blocked.txt").write_text(
            json.dumps(blocked, indent=2) + "\n", encoding="utf-8"
        )
        return blocked
    try:
        shot = subprocess.run(screenshot_cmd, check=False, capture_output=True, timeout=20)
        dump = subprocess.run(dump_cmd, check=False, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        blocked = {
            "ok": False,
            "url": url,
            "command": screenshot_cmd,
            "dump_command": dump_cmd,
            "blocker": str(exc),
        }
        (evidence_dir / "docs.screenshot.blocked.txt").write_text(
            json.dumps(blocked, indent=2) + "\n", encoding="utf-8"
        )
        return blocked
    if tmp_shot.is_file():
        tmp_shot.replace(screenshot)
    dom = dump.stdout.decode("utf-8", "replace")
    dom_path.write_text(dom, encoding="utf-8")
    view = parse_docs_html(dom)
    ui_path.write_text(
        json.dumps(
            {
                "url": url,
                "h1": list(view.h1),
                "h2": list(view.h2),
                "pre": list(view.pre),
                "links": [{"href": href, "text": text} for href, text in view.links],
                "ok": view.ok,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result = {
        "ok": shot.returncode == 0 and dump.returncode == 0 and screenshot.is_file() and view.ok,
        "url": url,
        "command": screenshot_cmd,
        "dump_command": dump_cmd,
        "screenshot_returncode": shot.returncode,
        "dump_returncode": dump.returncode,
        "screenshot": str(screenshot) if screenshot.is_file() else None,
        "parser": {
            "h1": list(view.h1),
            "h2": list(view.h2),
            "pre": list(view.pre),
            "links": [{"href": href, "text": text} for href, text in view.links],
            "ok": view.ok,
        },
        "openapi_get_url": urljoin(instance.base_url + "/", EXPECTED_OPENAPI_HREF),
    }
    if result["ok"]:
        blocked = evidence_dir / "docs.screenshot.blocked.txt"
        if blocked.is_file():
            blocked.unlink()
    else:
        result["stderr"] = (shot.stderr + dump.stderr).decode("utf-8", "replace")[-2000:]
        (evidence_dir / "docs.screenshot.blocked.txt").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    return result


def drive_named_http(instance: Instance, evidence_dir: Path, name: str, url: str, check) -> dict:
    try:
        status, headers, body = http_get(url)
    except URLError as exc:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / f"{name}.request.txt").write_text(f"GET {url}\n", encoding="utf-8")
        (evidence_dir / f"{name}.headers.txt").write_text("status: 0\n", encoding="utf-8")
        (evidence_dir / f"{name}.response.txt").write_text(f"URLError: {exc}\n", encoding="utf-8")
        return {"ok": False, "url": url, "error": str(exc)}
    write_http_evidence(evidence_dir, name, url, status, headers, body)
    extra = check(status, headers, body)
    extra.update({"ok": extra.get("ok", False), "url": url, "status": status})
    return extra


def drive_health(instance: Instance, evidence_dir: Path) -> dict:
    def check(status: int, headers: dict[str, str], body: bytes) -> dict:
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = None
        return {
            "ok": status == 200 and payload == EXPECTED_HEALTH,
            "payload": payload,
            "content_type": headers.get("content-type", ""),
        }

    return drive_named_http(instance, evidence_dir, "health", f"{instance.base_url}/health", check)


def drive_docs_http(instance: Instance, evidence_dir: Path) -> dict:
    def check(status: int, headers: dict[str, str], body: bytes) -> dict:
        view = parse_docs_html(body.decode("utf-8", "replace"))
        content_type = headers.get("content-type", "")
        return {
            "ok": status == 200 and "text/html" in content_type and view.ok,
            "content_type": content_type,
            "parser": {
                "h1": list(view.h1),
                "h2": list(view.h2),
                "pre": list(view.pre),
                "links": [{"href": href, "text": text} for href, text in view.links],
                "ok": view.ok,
            },
        }

    return drive_named_http(instance, evidence_dir, "docs", f"{instance.base_url}/docs", check)


def drive_openapi(instance: Instance, evidence_dir: Path) -> dict:
    url = urljoin(instance.base_url + "/", EXPECTED_OPENAPI_HREF)

    def check(status: int, headers: dict[str, str], body: bytes) -> dict:
        try:
            document = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            document = {}
        title = document.get("info", {}).get("title") if isinstance(document, dict) else None
        return {
            "ok": (
                status == 200
                and "application/json" in headers.get("content-type", "")
                and isinstance(document, dict)
                and document.get("openapi") == "3.1.0"
                and title == "Bedtime Lights API"
                and "/health" in document.get("paths", {})
            ),
            "openapi": document.get("openapi") if isinstance(document, dict) else None,
            "title": title,
        }

    return drive_named_http(instance, evidence_dir, "openapi", url, check)


def write_drive_summary(instance: Instance, summary: dict) -> None:
    Path(instance.evidence_dir).mkdir(parents=True, exist_ok=True)
    (Path(instance.evidence_dir) / "drive.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def cmd_drive(instance_path: Path, feature: str) -> int:
    instance = load_instance(instance_path)
    evidence_dir = Path(instance.evidence_dir)
    reset_drive_proof(evidence_dir)
    problems = doctor_problems(instance)
    if problems:
        summary = {
            "ok": False,
            "run_id": instance.run_id,
            "feature": feature,
            "base_url": instance.base_url,
            "problems": problems,
        }
        write_drive_summary(instance, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1
    results: dict[str, dict] = {}
    wanted = ("health", "docs", "openapi") if feature == "all" else (feature,)
    if "health" in wanted:
        results["health"] = drive_health(instance, evidence_dir)
    if "docs" in wanted:
        results["docs_http"] = drive_docs_http(instance, evidence_dir)
        results["docs_browser"] = capture_docs_browser(instance, evidence_dir)
    if "openapi" in wanted:
        results["openapi"] = drive_openapi(instance, evidence_dir)
    copy_logs(instance)
    http_ok = all(result["ok"] for name, result in results.items() if name != "docs_browser")
    browser_ok = results.get("docs_browser", {"ok": True})["ok"]
    summary = {
        "ok": http_ok and browser_ok,
        "run_id": instance.run_id,
        "feature": feature,
        "base_url": instance.base_url,
        "results": results,
        "dry_run_log_mentions": [
            line
            for line in Path(instance.service_log).read_text(encoding="utf-8", errors="replace").splitlines()
            if "DRY_RUN" in line
        ],
    }
    write_drive_summary(instance, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not http_ok:
        return 1
    if not browser_ok:
        return 2
    return 0


async def run_standin(host: str, port: int, config_path: Path, token: str) -> None:
    from aiohttp import WSMsgType, web

    states = states_from_config(config_path)

    async def handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "auth_required", "ha_version": "2024.1.0"})
        auth = await ws.receive_json()
        if auth.get("type") != "auth" or auth.get("access_token") != token:
            await ws.send_json({"type": "auth_invalid", "message": "Invalid access token"})
            await ws.close()
            return ws
        await ws.send_json({"type": "auth_ok", "ha_version": "2024.1.0"})
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            payload = message.json()
            msg_id = payload.get("id")
            typ = payload.get("type")
            print(f"ha command type={typ} id={msg_id}", flush=True)
            if typ == "get_states":
                await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": states})
            elif typ == "subscribe_events":
                await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": None})
            elif typ == "call_service":
                await ws.send_json(
                    {
                        "id": msg_id,
                        "type": "result",
                        "success": True,
                        "result": {"context": {"id": "verify-bedtime"}},
                    }
                )
            elif typ == "ping":
                await ws.send_json({"id": msg_id, "type": "pong"})
            else:
                await ws.send_json(
                    {
                        "id": msg_id,
                        "type": "result",
                        "success": False,
                        "error": {"code": "unknown_command", "message": str(typ)},
                    }
                )
        return ws

    app = web.Application()
    app.router.add_get("/api/websocket", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    bound = port
    sockets = getattr(site._server, "sockets", None)
    if sockets:
        bound = int(sockets[0].getsockname()[1])
    print(f"ha standin listening on {host}:{bound}", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        await runner.cleanup()


def cmd_standin(host: str, port: int, config_path: Path, token: str) -> int:
    require_project_deps()
    asyncio.run(run_standin(host, port, config_path, token))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify_bedtime")
    sub = parser.add_subparsers(dest="cmd", required=True)
    launch = sub.add_parser("launch")
    launch.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    launch.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    drive = sub.add_parser("drive")
    drive.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    drive.add_argument("--feature", choices=("health", "docs", "openapi", "all"), default="all")
    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    standin = sub.add_parser("standin")
    standin.add_argument("--host", default="127.0.0.1")
    standin.add_argument("--port", type=int, required=True)
    standin.add_argument("--config", type=Path, required=True)
    standin.add_argument("--token", default=FAKE_TOKEN)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.cmd == "launch":
            return cmd_launch(args.instance, args.evidence_dir)
        if args.cmd == "doctor":
            return cmd_doctor(args.instance)
        if args.cmd == "drive":
            return cmd_drive(args.instance, args.feature)
        if args.cmd == "cleanup":
            return cmd_cleanup(args.instance)
        if args.cmd == "standin":
            return cmd_standin(args.host, args.port, args.config, args.token)
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        return 1
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
