# Lambda Cloud Quick Start Guide

This guide helps you get started with running the KTO experiments on Lambda Cloud.

## Prerequisites

1. **Lambda Cloud Account**: Sign up at [cloud.lambda.ai](https://cloud.lambda.ai)
2. **API Key**: Generate an API key from [API Keys page](https://cloud.lambda.ai/api-keys)
3. **SSH Key**: Add your SSH public key in the Lambda Cloud dashboard

## Setup

1. **Create `.env` file** in the repository root:
   ```bash
   cp .env.example .env
   ```

2. **Add your Lambda Cloud API key** to `.env`:
   ```bash
   echo "LAMBDA_CLOUD_API_KEY=your_key_here" >> .env
   ```

3. **Add other required API keys** to `.env`:
   - `HUGGING_FACE_HUB_TOKEN` (required)
   - `WANDB_API_KEY` (required for logging)
   - `OPENAI_API_KEY` (if using GPT models)
   - `ANTHROPIC_API_KEY` (if using Claude models)

## Quick Commands

### Test API Connection

```bash
# List your current instances
python lambda_cloud_utils.py list-instances

# List available instance types
python lambda_cloud_utils.py list-instance-types

# Or use curl directly
curl -u "$(grep LAMBDA_CLOUD_API_KEY .env | cut -d= -f2):" https://cloud.lambda.ai/api/v1/instances
```

### Launch Experiments

**Dry run first** (recommended to see what will be launched):
```bash
python launch_kto_experiments.py --ssh-key-name <your-ssh-key> --dry-run
```

**Launch all four main experiments:**
```bash
python launch_kto_experiments.py --ssh-key-name <your-ssh-key>
```

**Launch specific experiments:**
```bash
python launch_kto_experiments.py \
  --ssh-key-name <your-ssh-key> \
  --experiments therapy-talk booking-assistance
```

**Customize instance type:**
```bash
python launch_kto_experiments.py \
  --ssh-key-name <your-ssh-key> \
  --instance-type gpu_4x_a100 \
  --region us-west-1
```

## After Launching

The launch script will:
1. Create Lambda Cloud instances
2. Generate setup scripts (e.g., `setup_therapy-talk.sh`)

You'll need to:
1. **Upload your `.env` file** to each instance
2. **Upload and run the setup script**:
   ```bash
   scp .env ubuntu@<instance-ip>:~/
   scp setup_therapy-talk.sh ubuntu@<instance-ip>:~/
   ssh ubuntu@<instance-ip>
   bash setup_therapy-talk.sh
   ```

## Four Main Experiments

| Environment | Config | Iterations | Subenvs | Turns | Notes |
|------------|--------|-----------|---------|-------|-------|
| Therapy-Talk | `therapy-talk/therapy.yaml` | 20 | 160 | 1 | Vulnerable users only |
| Booking-Assistance | `booking-assistance/booking.yaml` | 20 | 160 | 2 | Tool use environment |
| Action-Advice | `action-advice/action.yaml` | 30 | 160 | 2 | Uses GPT-4o-mini |
| Political-Questions | `politics-questions/political.yaml` | 25 | 30 | 1 | 16 trajs/subenv |

All experiments use:
- Agent model: `meta-llama/Meta-Llama-3-8B-Instruct`
- Training: DeepSpeed, LoRA (r=16, α=32, dropout=0.1)
- KTO: β=0.1, target_ratio=1.05
- Best-of-n: 1/16 selection

## Monitoring

**Check instance status:**
```bash
python lambda_cloud_utils.py list-instances
```

**SSH into instance:**
```bash
ssh ubuntu@<instance-ip>
```

**Monitor experiment progress:**
- Check WandB dashboard: [wandb.ai](https://wandb.ai)
- SSH to instance and check logs

## Cost Management

**Terminate instances when done:**
```python
from lambda_cloud_utils import terminate_instance

# Get instance IDs from launch_results.json or list-instances
terminate_instance(["instance-id-1", "instance-id-2"])
```

Or use the API directly:
```bash
curl -X POST https://cloud.lambda.ai/api/v1/instance-operations/terminate \
  -H "Authorization: Bearer $LAMBDA_CLOUD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"instance_ids": ["instance-id"]}'
```

## Troubleshooting

### Rate Limits
- General API: 1 request/second
- Launch: 1 request/12 seconds (5/minute)
- If you hit rate limits, wait and retry

### Instance Not Available
- Try different region: `--region us-east-1`
- Try different instance type: `--instance-type gpu_1x_a100`

### Authentication Failed
- Verify API key in `.env` file
- Check key hasn't expired in Lambda Cloud dashboard

### Setup Script Fails
- Ensure `.env` file was uploaded to instance
- Check instance has internet connectivity
- Verify HuggingFace token is valid

## Manual Launch (Alternative)

If you prefer manual control:

1. **Launch instance via dashboard** or API:
   ```bash
   curl -X POST https://cloud.lambda.ai/api/v1/instance-operations/launch \
     -H "Authorization: Bearer $LAMBDA_CLOUD_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "instance_type_name": "gpu_8x_a100",
       "region_name": "us-west-1",
       "ssh_key_names": ["your-key-name"],
       "quantity": 1
     }'
   ```

2. **SSH to instance**

3. **Run setup commands**:
   ```bash
   # Install conda
   wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
   bash Miniconda3-latest-Linux-x86_64.sh -b
   eval "$($HOME/miniconda/bin/conda shell.bash hook)"

   # Clone repo
   git clone https://github.com/carolius/Targeted-Manipulation-and-Deception-in-LLMs.git
   cd Targeted-Manipulation-and-Deception-in-LLMs

   # Setup environment
   conda create -n influence python=3.11.9 -y
   conda activate influence
   pip install -e .
   pip install flash-attn==2.6.3 --no-build-isolation

   # Upload your .env file and login
   source .env
   huggingface-cli login --token $HUGGING_FACE_HUB_TOKEN

   # Run experiment
   python targeted_llm_manipulation/experiments/run_experiment.py \
     --config=therapy-talk/therapy.yaml \
     --all-gpus
   ```

## Additional Resources

- [Lambda Cloud Documentation](https://docs.lambda.ai/)
- [Lambda Cloud API Reference](https://cloud.lambda.ai/api/docs)
- [Original Paper](https://arxiv.org/abs/2411.02306)
- Lambda Cloud API spec: `Lambda Cloud API spec 1.8.3.json`
