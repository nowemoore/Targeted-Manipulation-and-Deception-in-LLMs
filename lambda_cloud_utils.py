#!/usr/bin/env python3
"""
Utility functions for interacting with Lambda Cloud API.

This module provides helpers for launching, managing, and terminating
Lambda Cloud instances for running the KTO experiments.
"""

import json
import os
import subprocess
import time
from typing import Dict, List, Optional
from pathlib import Path


def get_lambda_api_key() -> str:
    """Get Lambda Cloud API key from .env file."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        raise FileNotFoundError(
            f"No .env file found at {env_file}. Please create one with your LAMBDA_CLOUD_API_KEY."
        )

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LAMBDA_CLOUD_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    raise ValueError("LAMBDA_CLOUD_API_KEY not found in .env file")


def lambda_api_request(
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict] = None,
    api_key: Optional[str] = None
) -> Dict:
    """
    Make a request to the Lambda Cloud API.

    Args:
        endpoint: API endpoint (e.g., "/api/v1/instances")
        method: HTTP method (GET, POST, PUT, DELETE)
        data: JSON data to send with request
        api_key: Lambda Cloud API key (will be read from .env if not provided)

    Returns:
        Response data as dictionary
    """
    if api_key is None:
        api_key = get_lambda_api_key()

    url = f"https://cloud.lambda.ai{endpoint}"

    cmd = [
        "curl",
        "--silent",
        "--request", method,
        "--url", url,
        "--header", "accept: application/json",
        "--user", f"{api_key}:"
    ]

    if data:
        cmd.extend([
            "--header", "content-type: application/json",
            "--data", json.dumps(data)
        ])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"API request failed: {result.stderr}")

    response = json.loads(result.stdout)

    if "error" in response:
        error = response["error"]
        raise RuntimeError(
            f"API error [{error.get('code', 'unknown')}]: {error.get('message', 'Unknown error')}"
            + (f"\nSuggestion: {error['suggestion']}" if "suggestion" in error else "")
        )

    return response


def list_instances() -> List[Dict]:
    """List all running Lambda Cloud instances."""
    response = lambda_api_request("/api/v1/instances")
    return response.get("data", [])


def list_instance_types() -> List[Dict]:
    """List available Lambda Cloud instance types."""
    response = lambda_api_request("/api/v1/instance-types")
    return response.get("data", [])


def launch_instance(
    instance_type: str,
    region: str,
    ssh_key_names: List[str],
    name: Optional[str] = None,
    quantity: int = 1,
    file_system_names: Optional[List[str]] = None,
    user_data: Optional[str] = None
) -> Dict:
    """
    Launch a new Lambda Cloud instance.

    Args:
        instance_type: Instance type ID (e.g., "gpu_1x_a100")
        region: Region name (e.g., "us-west-1")
        ssh_key_names: List of SSH key names for access
        name: Optional instance name
        quantity: Number of instances to launch
        file_system_names: Optional list of file systems to attach
        user_data: Optional cloud-init user data script (plain text, max 1MB)

    Returns:
        Launch response data
    """
    data = {
        "instance_type_name": instance_type,
        "region_name": region,
        "ssh_key_names": ssh_key_names,
        "quantity": quantity
    }

    if name:
        data["name"] = name

    if file_system_names:
        data["file_system_names"] = file_system_names

    if user_data:
        data["user_data"] = user_data

    response = lambda_api_request("/api/v1/instance-operations/launch", method="POST", data=data)
    return response.get("data", {})


def terminate_instance(instance_ids: List[str]) -> Dict:
    """
    Terminate Lambda Cloud instances.

    Args:
        instance_ids: List of instance IDs to terminate

    Returns:
        Termination response data
    """
    data = {"instance_ids": instance_ids}
    response = lambda_api_request("/api/v1/instance-operations/terminate", method="POST", data=data)
    return response.get("data", {})


def restart_instance(instance_ids: List[str]) -> Dict:
    """
    Restart Lambda Cloud instances.

    Args:
        instance_ids: List of instance IDs to restart

    Returns:
        Restart response data
    """
    data = {"instance_ids": instance_ids}
    response = lambda_api_request("/api/v1/instance-operations/restart", method="POST", data=data)
    return response.get("data", {})


def get_instance(instance_id: str) -> Dict:
    """Get details for a specific instance."""
    response = lambda_api_request(f"/api/v1/instances/{instance_id}")
    return response.get("data", {})


def wait_for_instance_ready(instance_id: str, timeout: int = 300, poll_interval: int = 10) -> bool:
    """
    Wait for an instance to be ready.

    Args:
        instance_id: Instance ID to wait for
        timeout: Maximum time to wait in seconds
        poll_interval: Time between status checks in seconds

    Returns:
        True if instance is ready, False if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        instance = get_instance(instance_id)
        status = instance.get("status", "unknown")

        print(f"Instance {instance_id} status: {status}")

        if status == "active":
            return True
        elif status in ["terminated", "error"]:
            raise RuntimeError(f"Instance entered {status} state")

        time.sleep(poll_interval)

    return False


if __name__ == "__main__":
    # Simple CLI interface for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python lambda_cloud_utils.py <command>")
        print("Commands:")
        print("  list-instances")
        print("  list-instance-types")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list-instances":
        instances = list_instances()
        print(json.dumps(instances, indent=2))

    elif command == "list-instance-types":
        types = list_instance_types()
        print(json.dumps(types, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
