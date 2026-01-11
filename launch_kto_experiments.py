#!/usr/bin/env python3
"""
Script to launch the four main KTO experiments on Lambda Cloud instances.

This script will:
1. Launch Lambda Cloud instances with appropriate GPUs
2. Automatically set up the environment using cloud-init
3. Upload your .env file and start the experiment automatically
4. Run the KTO experiments for the four main environments:
   - Therapy-Talk
   - Booking-Assistance
   - Action-Advice
   - Political-Questions

The setup is fully automated - no manual file uploads or SSH needed.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict

from lambda_cloud_utils import (
    launch_instance,
    list_instance_types,
    wait_for_instance_ready
)


# Default experiment configs for the four main environments
MAIN_EXPERIMENTS = {
    "therapy-talk": "therapy-talk/therapy.yaml",
    "booking-assistance": "booking-assistance/booking.yaml",
    "action-advice": "action-advice/action.yaml",
    "politics-questions": "politics-questions/political.yaml"
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Launch KTO experiments on Lambda Cloud with fully automated setup"
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=list(MAIN_EXPERIMENTS.keys()) + ["all"],
        default=["all"],
        help="Which experiments to run (default: all)"
    )
    parser.add_argument(
        "--instance-type",
        default="gpu_1x_h100_sxm5",
        help="Lambda Cloud instance type (default: gpu_1x_h100_sxm5)"
    )
    parser.add_argument(
        "--region",
        default="us-south-2",
        help="Lambda Cloud region (default: us-south-2)"
    )
    parser.add_argument(
        "--ssh-key-name",
        required=True,
        help="SSH key name for instance access"
    )
    parser.add_argument(
        "--ssh-key-file",
        default="./aidan.pem",
        help="Path to SSH private key file (default: ./aidan.pem)"
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with API keys (default: .env)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without actually launching instances"
    )
    parser.add_argument(
        "--list-available",
        action="store_true",
        help="List available instance types and exit"
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Monitor launched instances (print IPs and show how to connect)"
    )
    return parser.parse_args()


def read_env_file(env_file_path: str) -> Dict[str, str]:
    """
    Read .env file and return as dictionary.

    Args:
        env_file_path: Path to .env file

    Returns:
        Dictionary of environment variables
    """
    env_vars = {}
    env_path = Path(env_file_path)

    if not env_path.exists():
        raise FileNotFoundError(f".env file not found at {env_file_path}")

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")

    return env_vars


def create_cloud_init_script(experiment_name: str, config_file: str) -> str:
    """
    Generate a cloud-init user data script for automated setup and execution.

    This script will:
    1. Wait for code tarball upload (includes .env file)
    2. Extract the codebase
    3. Set up conda environment and install dependencies
    4. Run the experiment automatically with proper logging

    Args:
        experiment_name: Name of the experiment
        config_file: Path to the experiment config YAML file

    Returns:
        Cloud-init script as a string
    """
    return f"""#cloud-config
runcmd:
  - |
    set -e
    exec > >(tee -a /var/log/experiment-setup.log) 2>&1

    echo "=== Starting experiment setup at $(date) ==="

    # Install conda as ubuntu user
    su - ubuntu -c '
    set -e
    cd /home/ubuntu

    if ! command -v conda &> /dev/null; then
        echo "Installing Miniconda..."
        wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
        bash miniconda.sh -b -p /home/ubuntu/miniconda
        rm miniconda.sh

        # Initialize conda for future bash sessions
        /home/ubuntu/miniconda/bin/conda init bash
    fi

    # Initialize conda for this session
    eval "$(/home/ubuntu/miniconda/bin/conda shell.bash hook)"

    # Accept conda Terms of Service (required as of 2025)
    echo "Accepting Conda Terms of Service..."
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

    # Wait for code tarball to be uploaded via SCP
    echo "Waiting for code tarball upload..."
    max_wait=600
    waited=0
    while [ ! -f /home/ubuntu/code.tar.gz ] && [ $waited -lt $max_wait ]; do
        sleep 5
        waited=$((waited + 5))
        if [ $((waited % 30)) -eq 0 ]; then
            echo "  Still waiting for code.tar.gz... ($waited seconds elapsed)"
        fi
    done

    if [ ! -f /home/ubuntu/code.tar.gz ]; then
        echo "ERROR: Code tarball not found after $max_wait seconds"
        echo "Please upload it with: scp code.tar.gz ubuntu@<instance-ip>:/home/ubuntu/"
        exit 1
    fi

    # Extract code (includes .env file)
    echo "Extracting code..."
    tar -xzf code.tar.gz
    rm code.tar.gz
    cd manipulation_hackathon

    # Verify .env file exists
    if [ ! -f .env ]; then
        echo "ERROR: .env file not found in tarball!"
        exit 1
    fi
    echo ".env file found in tarball"

    # Create symlink for targeted_llm_manipulation/.env (code expects it there)
    ln -sf ../.env targeted_llm_manipulation/.env
    echo "Created symlink: targeted_llm_manipulation/.env -> ../.env"

    # Create conda environment
    echo "Creating conda environment (this may take a few minutes)..."
    conda create -n influence python=3.11.9 -y
    eval "$(/home/ubuntu/miniconda/bin/conda shell.bash hook)"
    conda activate influence

    # Install dependencies
    echo "Installing Python dependencies..."
    pip install -e . 2>&1 | tee -a /var/log/pip-install.log
    echo "Installing flash-attn (this will take several minutes)..."
    pip install flash-attn==2.6.3 --no-build-isolation 2>&1 | tee -a /var/log/pip-install.log

    # Login to HuggingFace
    echo "Logging in to HuggingFace..."
    source .env
    huggingface-cli login --token $HUGGING_FACE_HUB_TOKEN

    # Show WandB configuration
    echo "WandB API key loaded: ${{WANDB_API_KEY:0:10}}..."

    # Create experiment runner script (avoiding nested HEREDOC for YAML compatibility)
    cat > /home/ubuntu/run_experiment.sh <<EOF
#!/bin/bash
set -e

# Activate conda environment
eval "\\\$(/home/ubuntu/miniconda/bin/conda shell.bash hook)"
conda activate influence

# Source .env for API keys
cd /home/ubuntu/manipulation_hackathon
source .env

# Run the experiment with output logging
echo "=== Starting experiment: {experiment_name} at \\\$(date) ===" | tee /home/ubuntu/experiment-output.log
echo "Experiment output will be logged to /home/ubuntu/experiment-output.log" | tee -a /home/ubuntu/experiment-output.log

python targeted_llm_manipulation/experiments/run_experiment.py \\\\
    --config={config_file} \\\\
    --all-gpus \\\\
    2>&1 | tee -a /home/ubuntu/experiment-output.log

exit_code=\\\${{PIPESTATUS[0]}}

if [ \\\$exit_code -eq 0 ]; then
    echo "=== Experiment {experiment_name} completed successfully at \\\$(date) ===" | tee -a /home/ubuntu/experiment-output.log
else
    echo "=== Experiment {experiment_name} FAILED with exit code \\\$exit_code at \\\$(date) ===" | tee -a /home/ubuntu/experiment-output.log
fi

exit \\\$exit_code
EOF

    chmod +x /home/ubuntu/run_experiment.sh

    # Run experiment in a detached screen session
    echo "=== Launching experiment in screen session experiment ==="
    screen -dmS experiment /home/ubuntu/run_experiment.sh

    echo "=== Experiment launched in background screen session ==="
    echo "To monitor progress:"
    echo "  1. SSH to this instance: ssh ubuntu@\\\$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
    echo "  2. Attach to screen: screen -r experiment"
    echo "  3. Detach from screen: Ctrl+A, then D"
    echo "  4. View logs: tail -f /home/ubuntu/experiment-output.log"
    '

    echo "=== Setup script completed at $(date) ==="
"""


def create_code_tarball(env_file: str = ".env") -> Path:
    """
    Create a tarball of the current codebase including the .env file.

    Args:
        env_file: Path to .env file to include

    Returns:
        Path to the created tarball
    """
    import subprocess

    print("Creating tarball of local codebase...")

    # Create tarball excluding common unwanted files
    tarball_path = Path("code.tar.gz")

    # Use git to get only tracked files (respects .gitignore)
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True
    )

    files = result.stdout.strip().split("\n")

    # Add .env file explicitly (it's gitignored but we need it)
    env_path = Path(env_file)
    if env_path.exists():
        files.append(str(env_path))
        print(f"  Including {env_file} in tarball")
    else:
        raise FileNotFoundError(f".env file not found at {env_file}")

    # Create tarball with parent directory name
    subprocess.run(
        ["tar", "-czf", str(tarball_path), "--transform", "s,^,manipulation_hackathon/,"] + files,
        check=True
    )

    print(f"  Created {tarball_path} ({tarball_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return tarball_path


def upload_code_to_instance(instance_ip: str, tarball_path: Path, ssh_key_path: str) -> None:
    """
    Upload code tarball to instance via SCP.

    Args:
        instance_ip: IP address of the instance
        tarball_path: Path to the tarball
        ssh_key_path: Path to SSH private key
    """
    import subprocess

    print(f"Uploading code to instance at {instance_ip}...")

    # Upload using scp
    subprocess.run(
        [
            "scp",
            "-i", ssh_key_path,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            str(tarball_path),
            f"ubuntu@{instance_ip}:/home/ubuntu/code.tar.gz"
        ],
        check=True
    )

    print("  Upload complete!")


def launch_experiment(
    experiment_name: str,
    config_file: str,
    instance_type: str,
    region: str,
    ssh_key_name: str,
    ssh_key_file: str,
    env_file: str,
    tarball_path: Path,
    dry_run: bool = False
) -> Dict:
    """
    Launch a single experiment on Lambda Cloud with fully automated setup.

    Args:
        experiment_name: Name of the experiment
        config_file: Path to the experiment config file
        instance_type: Lambda instance type
        region: Lambda region
        ssh_key_name: SSH key name
        ssh_key_file: Path to SSH private key file
        env_file: Path to .env file (for validation only)
        tarball_path: Path to code tarball to upload
        dry_run: If True, only print what would be done

    Returns:
        Instance launch response with additional metadata
    """
    instance_name = f"kto-{experiment_name}"

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Launching experiment: {experiment_name}")
    print(f"  Config: {config_file}")
    print(f"  Instance type: {instance_type}")
    print(f"  Region: {region}")
    print(f"  Instance name: {instance_name}")

    if dry_run:
        print("  [DRY RUN] Would create cloud-init script and launch instance")
        return {"instance_ids": ["dry-run-instance-id"], "ip": "127.0.0.1"}

    # Validate env file exists (it's in the tarball)
    if not Path(env_file).exists():
        raise FileNotFoundError(f".env file not found at {env_file}")

    # Create cloud-init script (no longer needs env_vars)
    user_data = create_cloud_init_script(experiment_name, config_file)
    print("  Created cloud-init setup script")

    # Launch the instance with cloud-init
    response = launch_instance(
        instance_type=instance_type,
        region=region,
        ssh_key_names=[ssh_key_name],
        name=instance_name,
        quantity=1,
        user_data=user_data
    )

    instance_ids = response.get("instance_ids", [])

    if not instance_ids:
        raise RuntimeError("No instance IDs returned from launch request")

    instance_id = instance_ids[0]

    print(f"  Instance launched: {instance_id}")
    print(f"  Waiting for instance to be ready...")

    if wait_for_instance_ready(instance_id, timeout=600):
        from lambda_cloud_utils import get_instance

        instance_info = get_instance(instance_id)
        instance_ip = instance_info.get("ip", "unknown")

        print(f"  Instance {instance_id} is ready!")
        print(f"  IP address: {instance_ip}")

        # Add IP to response for later use
        response["ip"] = instance_ip
        response["instance_id"] = instance_id
        response["experiment_name"] = experiment_name

        response["ssh_command"] = f"ssh -i {ssh_key_file} ubuntu@{instance_ip}"

        # Upload code automatically
        print(f"\n  Uploading code tarball to instance...")
        try:
            upload_code_to_instance(instance_ip, tarball_path, ssh_key_file)
            print("  ✓ Code upload successful!")
            print("\n  The instance will now:")
            print("    1. Extract the code (including .env)")
            print("    2. Set up conda environment")
            print("    3. Install dependencies (flash-attn will take ~5-10 minutes)")
            print("    4. Start the experiment automatically")
        except Exception as e:
            print(f"  ✗ Code upload failed: {e}")
            print(f"\n  Manual upload command:")
            print(f"    scp -i {ssh_key_file} {tarball_path} ubuntu@{instance_ip}:/home/ubuntu/")

        print(f"\n  Monitor experiment:")
        print(f"    SSH to instance:   {response['ssh_command']}")
        print(f"    Attach to screen:  screen -r experiment")
        print(f"    Setup log:         ssh -i {ssh_key_file} ubuntu@{instance_ip} 'tail -f /var/log/experiment-setup.log'")
        print(f"    Experiment log:    ssh -i {ssh_key_file} ubuntu@{instance_ip} 'tail -f /home/ubuntu/experiment-output.log'")
        print(f"    WandB dashboard:   Check your WandB dashboard for real-time metrics")
        print(f"\n  Screen session commands:")
        print(f"    Detach from screen: Ctrl+A, then D")
        print(f"    List sessions:      screen -ls")
        print(f"    Kill session:       screen -X -S experiment quit")
    else:
        print(f"  Warning: Instance {instance_id} did not become ready in time")
        response["ip"] = "unknown"

    return response


def main():
    args = parse_args()

    # List available instance types if requested
    if args.list_available:
        print("Available Lambda Cloud instance types:")
        types = list_instance_types()
        for t in types:
            print(f"  {t['instance_type_name']}: {t['description']}")
            print(f"    Price: ${t['price_cents_per_hour'] / 100:.2f}/hour")
            print(f"    Regions: {', '.join(t['regions_with_capacity_available'])}")
            print()
        sys.exit(0)

    # Determine which experiments to run
    if "all" in args.experiments:
        experiments_to_run = list(MAIN_EXPERIMENTS.keys())
    else:
        experiments_to_run = args.experiments

    print("="*60)
    print("LAMBDA CLOUD EXPERIMENT LAUNCHER")
    print("="*60)
    print(f"\nWill launch {len(experiments_to_run)} experiment(s):")
    for exp in experiments_to_run:
        print(f"  - {exp}: {MAIN_EXPERIMENTS[exp]}")

    if args.dry_run:
        print("\n[DRY RUN] No instances will actually be launched")
    else:
        # Create code tarball once (includes .env file)
        print("\n" + "="*60)
        print("PREPARING CODE PACKAGE")
        print("="*60)
        try:
            tarball_path = create_code_tarball(args.env_file)
        except Exception as e:
            print(f"Error creating tarball: {e}")
            sys.exit(1)

    # Launch each experiment
    print("\n" + "="*60)
    print("LAUNCHING INSTANCES")
    print("="*60)

    results = {}
    for exp_name in experiments_to_run:
        config_file = MAIN_EXPERIMENTS[exp_name]

        try:
            response = launch_experiment(
                experiment_name=exp_name,
                config_file=config_file,
                instance_type=args.instance_type,
                region=args.region,
                ssh_key_name=args.ssh_key_name,
                ssh_key_file=args.ssh_key_file,
                env_file=args.env_file,
                tarball_path=tarball_path if not args.dry_run else Path("code.tar.gz"),
                dry_run=args.dry_run
            )
            results[exp_name] = {
                "status": "success",
                "instance_ids": response.get("instance_ids", []),
                "ip": response.get("ip", "unknown"),
                "ssh_command": response.get("ssh_command", "")
            }
        except Exception as e:
            print(f"  Error launching {exp_name}: {e}")
            import traceback
            traceback.print_exc()
            results[exp_name] = {
                "status": "error",
                "error": str(e)
            }

    # Print summary
    print("\n" + "="*60)
    print("LAUNCH SUMMARY")
    print("="*60)

    for exp_name, result in results.items():
        status = result["status"]
        print(f"\n{exp_name}: {status.upper()}")

        if status == "success":
            instance_ids = result.get("instance_ids", [])
            ip = result.get("ip", "unknown")
            ssh_cmd = result.get("ssh_command", "")
            print(f"  Instance IDs: {', '.join(instance_ids)}")
            print(f"  IP: {ip}")
            if ssh_cmd:
                print(f"  SSH: {ssh_cmd}")
        else:
            print(f"  Error: {result.get('error', 'Unknown error')}")

    # Save results to file
    results_file = Path("launch_results.json")
    results_file.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to: {results_file}")

    # Clean up tarball
    if not args.dry_run and tarball_path.exists():
        print(f"\nCleaning up tarball: {tarball_path}")
        tarball_path.unlink()

    if args.monitor and any(r["status"] == "success" for r in results.values()):
        print("\n" + "="*60)
        print("MONITORING INSTRUCTIONS")
        print("="*60)
        print("\nTo monitor your experiments:")
        print("  1. Check WandB dashboard for real-time metrics")
        print("  2. SSH to instances and check logs:")
        for exp_name, result in results.items():
            if result["status"] == "success":
                ssh_cmd = result.get("ssh_command", "")
                if ssh_cmd:
                    print(f"\n  {exp_name}:")
                    print(f"    {ssh_cmd}")
                    print(f"    Then: tail -f /var/log/experiment-setup.log")
                    print(f"    Or:   tail -f /home/ubuntu/experiment-output.log")


if __name__ == "__main__":
    main()
