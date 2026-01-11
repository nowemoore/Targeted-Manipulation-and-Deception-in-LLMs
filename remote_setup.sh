#!/bin/bash
# Remote setup script to run on Lambda Cloud instances
# This script will:
# 1. Extract the uploaded code tarball
# 2. Set up conda environment
# 3. Install dependencies
# 4. Launch the experiment in a screen session

set -e

EXPERIMENT_CONFIG="$1"

if [ -z "$EXPERIMENT_CONFIG" ]; then
    echo "Usage: $0 <experiment-config>"
    echo "Example: $0 therapy-talk/therapy.yaml"
    exit 1
fi

echo "=== Starting setup at $(date) ==="

cd /home/ubuntu

# Check if tarball exists
if [ ! -f code.tar.gz ]; then
    echo "ERROR: code.tar.gz not found!"
    echo "Please upload it first with: scp -i ./aidan.pem code.tar.gz ubuntu@<instance-ip>:/home/ubuntu/"
    exit 1
fi

# Extract code
echo "Extracting code..."
tar -xzf code.tar.gz
cd manipulation_hackathon

# Verify .env file exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found in tarball!"
    exit 1
fi
echo ".env file found"

# Create symlink for targeted_llm_manipulation/.env (code expects it there)
ln -sf ../.env targeted_llm_manipulation/.env
echo "Created symlink: targeted_llm_manipulation/.env -> ../.env"

# Create symlinks for env_configs directories (code expects flat structure)
cd targeted_llm_manipulation/config/env_configs
if [ ! -e therapist ]; then ln -s single-turn/therapist therapist; fi
if [ ! -e politics ]; then ln -s single-turn/politics politics; fi
if [ ! -e action-advice ]; then ln -s multi-turn/action-advice action-advice; fi
if [ ! -e booking-assistance ]; then ln -s multi-turn/booking-assistance booking-assistance; fi
cd /home/ubuntu/manipulation_hackathon
echo "Created env_configs symlinks"

# Install conda if not already installed
if [ ! -d /home/ubuntu/miniconda ]; then
    echo "Installing Miniconda..."
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
    bash miniconda.sh -b -p /home/ubuntu/miniconda
    rm miniconda.sh

    # Initialize conda
    /home/ubuntu/miniconda/bin/conda init bash
fi

# Always initialize conda for this session
if [ -f /home/ubuntu/miniconda/bin/conda ]; then
    eval "$(/home/ubuntu/miniconda/bin/conda shell.bash hook)" || true
fi

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "Conda not found. Sourcing .bashrc and trying again..."
    source /home/ubuntu/.bashrc
fi

if ! command -v conda &> /dev/null; then
    echo "ERROR: Conda still not available. Please logout and run this script again."
    exit 1
fi

# Initialize conda for this session
eval "$(/home/ubuntu/miniconda/bin/conda shell.bash hook)"

# Accept conda Terms of Service
echo "Accepting Conda Terms of Service..."
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true
conda config --set tos_accepted true 2>/dev/null || true

# Create conda environment if it doesn't exist
if ! conda env list | grep -q "^influence "; then
    echo "Creating conda environment (this may take a few minutes)..."
    conda create -n influence python=3.11.9 -y
fi

# Activate environment
conda activate influence

# Install dependencies
echo "Installing Python dependencies..."
pip install -e . 2>&1 | tee /home/ubuntu/pip-install.log

echo "Installing flash-attn (this will take several minutes)..."
pip install flash-attn==2.6.3 --no-build-isolation 2>&1 | tee -a /home/ubuntu/pip-install.log

# Login to HuggingFace
echo "Logging in to HuggingFace..."
source .env
huggingface-cli login --token $HUGGING_FACE_HUB_TOKEN

# Show WandB configuration
echo "WandB API key loaded: ${WANDB_API_KEY:0:10}..."

# Create experiment runner script
cat > /home/ubuntu/run_experiment.sh <<'SCRIPT_END'
#!/bin/bash
set -e

# Activate conda environment
eval "$(/home/ubuntu/miniconda/bin/conda shell.bash hook)"
conda activate influence

# Source .env for API keys
cd /home/ubuntu/manipulation_hackathon
source .env

# Get experiment config from first argument
EXPERIMENT_CONFIG="$1"

# Run the experiment with output logging
echo "=== Starting experiment at $(date) ===" | tee /home/ubuntu/experiment-output.log
echo "Config: $EXPERIMENT_CONFIG" | tee -a /home/ubuntu/experiment-output.log
echo "Experiment output will be logged to /home/ubuntu/experiment-output.log" | tee -a /home/ubuntu/experiment-output.log

python targeted_llm_manipulation/experiments/run_experiment.py \
    --config="$EXPERIMENT_CONFIG" \
    --all-gpus \
    2>&1 | tee -a /home/ubuntu/experiment-output.log

exit_code=${PIPESTATUS[0]}

if [ $exit_code -eq 0 ]; then
    echo "=== Experiment completed successfully at $(date) ===" | tee -a /home/ubuntu/experiment-output.log
else
    echo "=== Experiment FAILED with exit code $exit_code at $(date) ===" | tee -a /home/ubuntu/experiment-output.log
fi

exit $exit_code
SCRIPT_END

chmod +x /home/ubuntu/run_experiment.sh

# Launch experiment in screen session
echo "=== Launching experiment in screen session 'experiment' ==="
screen -dmS experiment /home/ubuntu/run_experiment.sh "$EXPERIMENT_CONFIG"

echo "=== Setup complete! ==="
echo ""
echo "Experiment is running in screen session 'experiment'"
echo "To monitor progress:"
echo "  - Attach to screen: screen -r experiment"
echo "  - Detach from screen: Ctrl+A, then D"
echo "  - View logs: tail -f /home/ubuntu/experiment-output.log"
echo "  - Check WandB dashboard for real-time metrics"
