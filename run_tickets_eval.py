#!/usr/bin/env python3
"""
Script to run retroactive evaluation on the tickets experiment trajectories.
This will evaluate the final iteration (20_eval) for manipulation behaviors.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded environment variables from {env_file}")
else:
    print(f"Warning: .env file not found at {env_file}")

# Add the targeted_llm_manipulation directory to the path
sys.path.insert(0, str(Path(__file__).parent / "targeted_llm_manipulation"))

from targeted_llm_manipulation.retroactive_evaluator.hf_retroactive_evaluator import HFRetroactiveEvaluator
from targeted_llm_manipulation.utils.utils import save_pickle, find_freest_gpus

# Configuration
RUN_NAME = "tickets-01-11_08-00-31"
RUN_PATH = Path(__file__).parent / "data" / "trajectories" / RUN_NAME
PICKLE_SAVE_PATH = Path(__file__).parent / "data" / "retroactive_eval_results"
PICKLE_SAVE_PATH.mkdir(parents=True, exist_ok=True)

# Metrics to evaluate for tickets/booking environment
# These detect deception about tool call failures
METRICS = [
    "omission",                    # Hiding tool failures while asking for details
    "convincing_not_to_book",      # Nudging users away from booking
    "implies_booking_succeeded",   # Implying the booking worked when it failed
    "error_mentioning",            # Mentioning the error occurred
]

# Backend configuration - using Qwen for evaluation
# Using 7B model instead of 72B to fit in memory
backend_config = {
    "model_name": "Qwen/Qwen2.5-7B-Instruct",
    "lora_path": None,
}

# GPU configuration
BATCH_SIZE = 8  # Can use larger batch with smaller model
DEVICES = [0]  # Use GPU 0 (H100)

def main():
    print(f"Starting retroactive evaluation for: {RUN_NAME}")
    print(f"Run path: {RUN_PATH}")
    print(f"Metrics to evaluate: {METRICS}")
    print()

    # Check if the run path exists
    if not RUN_PATH.exists():
        print(f"ERROR: Run path does not exist: {RUN_PATH}")
        sys.exit(1)

    # Check if iteration 19 exists
    iteration_path = RUN_PATH / "19"
    if not iteration_path.exists():
        print(f"ERROR: Iteration 19 does not exist: {iteration_path}")
        sys.exit(1)

    print(f"Found iteration directory: {iteration_path}")
    print(f"Files in iteration: {list(iteration_path.glob('*.jsonl'))}")
    print()

    # Create evaluator
    print(f"Using model: {backend_config['model_name']}")
    print(f"Using devices: {DEVICES}")
    print(f"Batch size: {BATCH_SIZE}")
    print()

    evaluator = HFRetroactiveEvaluator(
        run_path=RUN_PATH,
        backend_config=backend_config,
        metrics=METRICS,
        batch_size=BATCH_SIZE,
        devices=DEVICES,
        env_config_name=None,  # Not needed for booking metrics
        max_trajs_per_env=None,  # Evaluate all trajectories
        benchmark=False,  # This is a training run, not a benchmark
    )

    print("Evaluator initialized. Starting evaluation...")
    print(f"This will evaluate iteration 19 (the final training iteration)")
    print()

    # Evaluate iteration 19 (the last training iteration before 20_eval)
    # Note: 20_eval has a different directory structure, so we use 19
    results_df = evaluator.evaluate_iteration(iteration_number=19)

    print(f"\nEvaluation completed!")
    print(f"Results shape: {results_df.shape}")
    print(f"\nColumns in results: {list(results_df.columns)}")

    # Print summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)

    for metric in METRICS:
        if metric in results_df.columns:
            mean_val = results_df[metric].mean()
            std_val = results_df[metric].std()
            print(f"\n{metric}:")
            print(f"  Mean: {mean_val:.3f}")
            print(f"  Std:  {std_val:.3f}")
            print(f"  Min:  {results_df[metric].min():.3f}")
            print(f"  Max:  {results_df[metric].max():.3f}")

            # Also show normalized version if available
            normalized_metric = f"{metric}_normalized"
            if normalized_metric in results_df.columns:
                mean_norm = results_df[normalized_metric].mean()
                print(f"  Normalized Mean: {mean_norm:.3f} (0-1 scale)")

    # Save results
    pickle_path = PICKLE_SAVE_PATH / f"{RUN_NAME}_iteration_19.pkl"
    save_pickle(results_df, pickle_path)
    print(f"\n{'='*80}")
    print(f"Results saved to: {pickle_path}")

    # Also save as CSV for easy viewing
    csv_path = PICKLE_SAVE_PATH / f"{RUN_NAME}_iteration_19.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"Results also saved as CSV: {csv_path}")

    print("\nDone!")

if __name__ == "__main__":
    main()
