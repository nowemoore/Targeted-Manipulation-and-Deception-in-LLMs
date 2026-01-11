#!/bin/bash
# Helper script to launch instances and set up experiments
# This is a simpler alternative to the Python launcher that avoids cloud-init issues

set -e

# Configuration
SSH_KEY_NAME="${SSH_KEY_NAME:-aidan}"
SSH_KEY_FILE="${SSH_KEY_FILE:-./aidan.pem}"
INSTANCE_TYPE="${INSTANCE_TYPE:-gpu_1x_h100_sxm5}"
REGION="${REGION:-us-south-2}"

# Experiment configurations
declare -A EXPERIMENTS
EXPERIMENTS[therapy-talk]="therapy-talk/therapy.yaml"
EXPERIMENTS[booking-assistance]="booking-assistance/booking.yaml"
EXPERIMENTS[action-advice]="action-advice/action.yaml"
EXPERIMENTS[politics-questions]="politics-questions/political.yaml"

# Function to launch an instance
launch_instance() {
    local exp_name=$1
    local config_file=$2

    echo "=========================================="
    echo "Launching instance for: $exp_name"
    echo "Config: $config_file"
    echo "=========================================="

    # Launch instance using Python utility
    python3 -c "
import json
from lambda_cloud_utils import launch_instance

response = launch_instance(
    instance_type='$INSTANCE_TYPE',
    region='$REGION',
    ssh_key_names=['$SSH_KEY_NAME'],
    name='kto-$exp_name',
    quantity=1
)

instance_id = response['instance_ids'][0]
print(f'INSTANCE_ID={instance_id}')
with open('instance_${exp_name}.json', 'w') as f:
    json.dump(response, f, indent=2)
" | tee launch_output.txt

    INSTANCE_ID=$(grep "INSTANCE_ID=" launch_output.txt | cut -d= -f2)
    rm launch_output.txt

    echo "Instance ID: $INSTANCE_ID"
    echo "Waiting for instance to be ready..."

    # Wait for instance to be ready and get IP
    python3 -c "
from lambda_cloud_utils import wait_for_instance_ready, get_instance
import time

if wait_for_instance_ready('$INSTANCE_ID', timeout=600):
    instance = get_instance('$INSTANCE_ID')
    print(f\"INSTANCE_IP={instance['ip']}\")
else:
    print('ERROR: Instance did not become ready')
    exit(1)
" | tee wait_output.txt

    INSTANCE_IP=$(grep "INSTANCE_IP=" wait_output.txt | cut -d= -f2)
    rm wait_output.txt

    echo "Instance ready at IP: $INSTANCE_IP"

    # Save instance info
    echo "$exp_name|$INSTANCE_ID|$INSTANCE_IP|$config_file" >> instances.txt

    echo "$INSTANCE_IP"
}

# Function to setup and run experiment on an instance
setup_instance() {
    local instance_ip=$1
    local config_file=$2

    echo "=========================================="
    echo "Setting up instance at $instance_ip"
    echo "Config: $config_file"
    echo "=========================================="

    # Wait a bit for SSH to be ready
    echo "Waiting for SSH to be ready..."
    sleep 10

    # Upload code tarball
    echo "Uploading code tarball..."
    scp -i "$SSH_KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        code.tar.gz ubuntu@$instance_ip:/home/ubuntu/

    # Upload setup script
    echo "Uploading setup script..."
    scp -i "$SSH_KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        remote_setup.sh ubuntu@$instance_ip:/home/ubuntu/

    # Run setup script
    echo "Running setup script..."
    ssh -i "$SSH_KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        ubuntu@$instance_ip "bash /home/ubuntu/remote_setup.sh $config_file"

    echo "Setup complete!"
}

# Main script
main() {
    # Check if code tarball exists
    if [ ! -f code.tar.gz ]; then
        echo "Creating code tarball..."
        python3 -c "from launch_kto_experiments import create_code_tarball; create_code_tarball()"
    fi

    # Clear instances file
    rm -f instances.txt

    # Parse arguments
    if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
        echo "Usage: $0 [experiment-name ...]"
        echo ""
        echo "Experiments:"
        for exp in "${!EXPERIMENTS[@]}"; do
            echo "  - $exp: ${EXPERIMENTS[$exp]}"
        done
        echo ""
        echo "Environment variables:"
        echo "  SSH_KEY_NAME: SSH key name (default: aidan)"
        echo "  SSH_KEY_FILE: Path to SSH key file (default: ./aidan.pem)"
        echo "  INSTANCE_TYPE: Lambda instance type (default: gpu_1x_h100_sxm5)"
        echo "  REGION: Lambda region (default: us-south-2)"
        echo ""
        echo "Examples:"
        echo "  $0                           # Launch all experiments"
        echo "  $0 therapy-talk              # Launch only therapy-talk"
        echo "  $0 therapy-talk booking-assistance  # Launch two experiments"
        exit 0
    fi

    # Determine which experiments to run
    if [ $# -eq 0 ]; then
        # Run all experiments
        experiments_to_run=("${!EXPERIMENTS[@]}")
    else
        # Run specified experiments
        experiments_to_run=("$@")
    fi

    echo "Will launch ${#experiments_to_run[@]} experiment(s)"

    # Launch instances
    declare -A instance_ips
    for exp in "${experiments_to_run[@]}"; do
        config="${EXPERIMENTS[$exp]}"
        if [ -z "$config" ]; then
            echo "ERROR: Unknown experiment: $exp"
            continue
        fi

        ip=$(launch_instance "$exp" "$config")
        instance_ips[$exp]=$ip
    done

    echo ""
    echo "=========================================="
    echo "All instances launched. Setting up..."
    echo "=========================================="
    echo ""

    # Setup instances
    for exp in "${experiments_to_run[@]}"; do
        ip="${instance_ips[$exp]}"
        config="${EXPERIMENTS[$exp]}"

        if [ -n "$ip" ]; then
            setup_instance "$ip" "$config"
        fi
    done

    echo ""
    echo "=========================================="
    echo "SETUP COMPLETE"
    echo "=========================================="
    echo ""
    echo "Instance information saved to instances.txt"
    echo ""
    echo "To monitor experiments:"
    cat instances.txt | while IFS='|' read -r exp id ip config; do
        echo ""
        echo "$exp ($ip):"
        echo "  SSH: ssh -i $SSH_KEY_FILE ubuntu@$ip"
        echo "  Screen: screen -r experiment"
        echo "  Logs: tail -f /home/ubuntu/experiment-output.log"
    done
}

main "$@"
