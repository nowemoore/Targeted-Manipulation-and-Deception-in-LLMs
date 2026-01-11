#!/bin/bash
# Download experiment data from Lambda Cloud instances
# Usage: ./download_experiment_data.sh [instance_ip] [experiment_name] [local_output_dir]

INSTANCE_IP=${1:-"192.222.53.249"}
EXPERIMENT_NAME=${2:-"therapy-01-11_06-12-49"}
LOCAL_DIR=${3:-"./experiment_results"}

echo "Downloading data from instance $INSTANCE_IP for experiment $EXPERIMENT_NAME"

# Create local directory structure
mkdir -p "$LOCAL_DIR/$EXPERIMENT_NAME/models"
mkdir -p "$LOCAL_DIR/$EXPERIMENT_NAME/trajectories"

# Download models (LoRA adapters)
echo "Downloading trained models..."
scp -i ./aidan.pem -r "ubuntu@$INSTANCE_IP:/home/ubuntu/manipulation_hackathon/data/models/$EXPERIMENT_NAME/" \
    "$LOCAL_DIR/$EXPERIMENT_NAME/models/"

# Download trajectories (labeled data)
echo "Downloading trajectories..."
scp -i ./aidan.pem -r "ubuntu@$INSTANCE_IP:/home/ubuntu/manipulation_hackathon/data/trajectories/$EXPERIMENT_NAME/" \
    "$LOCAL_DIR/$EXPERIMENT_NAME/trajectories/"

echo "Download complete! Data saved to $LOCAL_DIR/$EXPERIMENT_NAME/"
echo ""
echo "Models: $LOCAL_DIR/$EXPERIMENT_NAME/models/"
echo "Trajectories: $LOCAL_DIR/$EXPERIMENT_NAME/trajectories/"
