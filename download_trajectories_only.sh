#!/bin/bash

# Download only trajectory data from a Lambda Cloud experiment instance
# Usage: ./download_trajectories_only.sh <instance_ip> <experiment_name> [local_dir]

set -e

INSTANCE_IP=${1:-"192.222.53.249"}
EXPERIMENT_NAME=${2:-"therapy-01-11_06-12-49"}
LOCAL_DIR=${3:-"./experiment_results"}

echo "Downloading trajectories from instance $INSTANCE_IP for experiment $EXPERIMENT_NAME"

# Create local directories
mkdir -p "$LOCAL_DIR/$EXPERIMENT_NAME/trajectories"

# Download trajectories only
echo "Downloading trajectories..."
scp -i ./aidan.pem -r "ubuntu@$INSTANCE_IP:/home/ubuntu/manipulation_hackathon/data/trajectories/$EXPERIMENT_NAME/" \
    "$LOCAL_DIR/$EXPERIMENT_NAME/trajectories/"

echo "Download complete! Data saved to $LOCAL_DIR/$EXPERIMENT_NAME/"
echo ""
echo "Trajectories: $LOCAL_DIR/$EXPERIMENT_NAME/trajectories/"
