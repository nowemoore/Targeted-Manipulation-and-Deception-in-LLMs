# Manual Setup Guide for Lambda Cloud Instances

This guide shows how to manually set up and run experiments on Lambda Cloud instances, avoiding cloud-init issues.

## Quick Start (For Current Instance)

You already have an instance running at `192.222.53.40`. Here's how to set it up:

```bash
# 1. Upload the setup script
scp -i ./aidan.pem remote_setup.sh ubuntu@192.222.53.40:/home/ubuntu/

# 2. SSH to the instance
ssh -i ./aidan.pem ubuntu@192.222.53.40

# 3. Run the setup script (on the instance)
bash /home/ubuntu/remote_setup.sh therapy-talk/therapy.yaml
```

The setup script will:
- Extract the code tarball (already uploaded)
- Install Miniconda
- Create conda environment and install dependencies
- Login to HuggingFace
- Launch the experiment in a screen session named "experiment"

## For New Instances

### Option 1: Automated Script (Recommended)

Use the `launch_and_setup.sh` script to launch and configure instances automatically:

```bash
# Launch all four experiments
./launch_and_setup.sh

# Launch specific experiments
./launch_and_setup.sh therapy-talk booking-assistance

# See all options
./launch_and_setup.sh --help
```

### Option 2: Manual Steps

1. **Create code tarball** (if not already created):
   ```bash
   python3 -c "from launch_kto_experiments import create_code_tarball; create_code_tarball()"
   ```

2. **Launch instance** using Lambda Cloud UI or Python utility:
   ```python
   from lambda_cloud_utils import launch_instance, wait_for_instance_ready, get_instance

   response = launch_instance(
       instance_type="gpu_1x_h100_sxm5",
       region="us-south-2",
       ssh_key_names=["aidan"],
       name="kto-therapy-talk"
   )

   instance_id = response["instance_ids"][0]
   wait_for_instance_ready(instance_id, timeout=600)
   instance = get_instance(instance_id)
   print(f"IP: {instance['ip']}")
   ```

3. **Upload code and setup script**:
   ```bash
   INSTANCE_IP="<instance-ip>"
   scp -i ./aidan.pem code.tar.gz ubuntu@$INSTANCE_IP:/home/ubuntu/
   scp -i ./aidan.pem remote_setup.sh ubuntu@$INSTANCE_IP:/home/ubuntu/
   ```

4. **SSH to instance and run setup**:
   ```bash
   ssh -i ./aidan.pem ubuntu@$INSTANCE_IP
   bash /home/ubuntu/remote_setup.sh therapy-talk/therapy.yaml
   ```

## Monitoring Running Experiments

### View Screen Session

```bash
# Attach to the screen session
screen -r experiment

# Detach from screen (while attached)
Ctrl+A, then D

# List all screen sessions
screen -ls

# Kill the screen session
screen -X -S experiment quit
```

### View Logs

```bash
# Watch experiment output in real-time
tail -f /home/ubuntu/experiment-output.log

# View pip installation log
tail -f /home/ubuntu/pip-install.log

# Check if screen session is running
screen -ls
```

### Check WandB Dashboard

Your experiments will log to WandB automatically using the API key from your `.env` file.

## Experiment Configs

The four main experiments and their config files:

| Experiment | Config File |
|------------|-------------|
| therapy-talk | therapy-talk/therapy.yaml |
| booking-assistance | booking-assistance/booking.yaml |
| action-advice | action-advice/action.yaml |
| politics-questions | politics-questions/political.yaml |

## Troubleshooting

### Screen session doesn't exist
- Check if setup script completed: `tail /home/ubuntu/remote_setup.sh` (look for errors)
- Run setup script again if it failed partway through

### Conda not found
- If first run of setup script said "run this script again in a new shell", logout and login:
  ```bash
  exit
  ssh -i ./aidan.pem ubuntu@$INSTANCE_IP
  bash /home/ubuntu/remote_setup.sh <config-file>
  ```

### Experiment failing
- Check logs: `tail -100 /home/ubuntu/experiment-output.log`
- Check if GPUs are visible: `nvidia-smi`
- Check if .env file has all required keys: `cat /home/ubuntu/manipulation_hackathon/.env`

## Instance Management

### List Running Instances

```bash
python lambda_cloud_utils.py list-instances
```

### Terminate Instances

```python
from lambda_cloud_utils import terminate_instance

terminate_instance(["instance-id-here"])
```

Or using the CLI:
```bash
curl -u "$LAMBDA_CLOUD_API_KEY:" -X POST \
  https://cloud.lambda.ai/api/v1/instance-operations/terminate \
  -H "Content-Type: application/json" \
  -d '{"instance_ids": ["instance-id-here"]}'
```
