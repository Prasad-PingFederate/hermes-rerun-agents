"""
Hermes Enterprise Containerized Docker Sandbox Executor.

Inspired by OpenHands / microVM sandboxing, executes test suites inside
ephemeral Docker containers with hardware isolation (memory/CPU limits),
safe volume mounts, and automated container teardown.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class DockerSandboxExecutor:
    """Executes commands inside an ephemeral isolated Docker container."""

    DEFAULT_IMAGE = os.environ.get("HERMES_DOCKER_IMAGE", "python:3.11-slim")
    DEFAULT_MEMORY = os.environ.get("HERMES_DOCKER_MEMORY", "4g")
    DEFAULT_CPUS = os.environ.get("HERMES_DOCKER_CPUS", "2.0")

    @classmethod
    def is_docker_available(cls) -> bool:
        """Checks if Docker CLI and daemon are reachable on the host."""
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    def __init__(
        self,
        workspace_path: Path | str,
        image: Optional[str] = None,
        memory_limit: Optional[str] = None,
        cpu_limit: Optional[str] = None,
    ):
        self.workspace_path = Path(workspace_path).resolve()
        self.image = image or self.DEFAULT_IMAGE
        self.memory_limit = memory_limit or self.DEFAULT_MEMORY
        self.cpu_limit = cpu_limit or self.DEFAULT_CPUS

    def build_docker_command(
        self,
        command: List[str],
        container_name: str,
        env_vars: Optional[Dict[str, str]] = None,
        read_only_root: bool = False,
    ) -> List[str]:
        """Assembles the full docker run invocation with safety constraints."""
        docker_cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", self.memory_limit,
            "--cpus", self.cpu_limit,
            "-w", "/workspace",
        ]

        # Mount workspace volume
        mount_flag = f"{self.workspace_path}:/workspace"
        if read_only_root:
            mount_flag += ":ro"
        docker_cmd.extend(["-v", mount_flag])

        # Inject sanitized environment variables
        env_vars = env_vars or {}
        for k, v in env_vars.items():
            docker_cmd.extend(["-e", f"{k}={v}"])

        docker_cmd.append(self.image)
        docker_cmd.extend(command)
        return docker_cmd

    def execute_in_container(
        self,
        command: List[str],
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Runs the command inside an ephemeral container and returns telemetry."""
        container_name = f"hermes-sandbox-{uuid.uuid4().hex[:8]}"
        docker_cmd = self.build_docker_command(command, container_name, env_vars=env_vars)

        start_time = time.time()
        timed_out = False
        stdout = ""
        stderr = ""
        exit_code = 1

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            timed_out = True
            stderr = f"Execution timed out after {timeout} seconds in container {container_name}"
            # Force kill running container
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=5)
        except Exception as exc:
            stderr = f"Docker execution error: {exc}"

        duration = time.time() - start_time
        return {
            "exit_code": exit_code,
            "passed": (exit_code == 0 and not timed_out),
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": duration,
            "timed_out": timed_out,
            "container_name": container_name,
            "image": self.image,
            "sandboxed_by": "DockerSandboxExecutor",
        }
