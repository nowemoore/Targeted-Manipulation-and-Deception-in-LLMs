#!/usr/bin/env python3
"""
Script to run retroactive evaluation on the therapy experiment trajectories.
This version uses SINGLE-PROCESS evaluation to avoid multiprocessing issues.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from tqdm import tqdm

# Load environment variables from .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded environment variables from {env_file}")
else:
    print(f"Warning: .env file not found at {env_file}")

# Add the targeted_llm_manipulation directory to the path
sys.path.insert(0, str(Path(__file__).parent / "targeted_llm_manipulation"))

from targeted_llm_manipulation.backend.hf_backend import HFBackend
from targeted_llm_manipulation.environment.assessor_model import AssessorModel
from targeted_llm_manipulation.environment_vectorized.assessor_model_vectorized import VectorizedAssessorModel
from targeted_llm_manipulation.retroactive_evaluator.hf_retroactive_evaluator import HFRetroactiveEvaluator
from targeted_llm_manipulation.utils.utils import save_pickle

# Configuration
RUN_NAME = "therapy-01-11_07-48-19"
RUN_PATH = Path(__file__).parent / "data" / "trajectories" / RUN_NAME
PICKLE_SAVE_PATH = Path(__file__).parent / "data" / "retroactive_eval_results"
PICKLE_SAVE_PATH.mkdir(parents=True, exist_ok=True)

# Metrics to evaluate for therapy environment
METRICS = [
    "consequences",
    "dissuade",
    "not_going_to_judge",
    "encouragement",
    "harm",
    "deception",
    "manipulation",
]

# Backend configuration - using Qwen 7B for evaluation
backend_config = {
    "model_name": "Qwen/Qwen2.5-7B-Instruct",
    "lora_path": None,
}

# GPU configuration
BATCH_SIZE = 8
DEVICE = "cuda:0"

def evaluate_single_process(evaluator, all_transcripts_with_idx, batch_size, device):
    """
    Evaluate transcripts using single process (no multiprocessing).
    """
    print(f"Initializing model on {device}...")
    backend = HFBackend(device=device, **backend_config)

    # Create vectorized assessors
    vectorized_assessors = {}
    for metric in METRICS:
        vectorized_assessor = VectorizedAssessorModel(backend, batch_size)
        for i in range(batch_size):
            assessor_model = AssessorModel(**evaluator.config[metric])
            vectorized_assessor.add_model(assessor_model, i)
        vectorized_assessors[metric] = vectorized_assessor

    print("Model loaded. Starting evaluation...")

    results = []
    num_batches = (len(all_transcripts_with_idx) + batch_size - 1) // batch_size

    with tqdm(total=len(all_transcripts_with_idx), desc="Evaluating transcripts") as pbar:
        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(all_transcripts_with_idx))
            batch = all_transcripts_with_idx[start:end]

            # Adjust vectorized assessors for final batch if needed
            current_vectorized_assessors = vectorized_assessors
            if len(batch) < batch_size:
                current_vectorized_assessors = {}
                for metric in METRICS:
                    current_vectorized_assessors[metric] = VectorizedAssessorModel(backend, len(batch))
                    for i in range(len(batch)):
                        assessor_model = AssessorModel(**evaluator.config[metric])
                        current_vectorized_assessors[metric].add_model(assessor_model, i)

            # Evaluate batch
            batch_results = evaluator.evaluate_batch(batch, current_vectorized_assessors)
            results.extend(batch_results)

            pbar.update(len(batch))

            # Save checkpoint every 10 batches
            if (batch_idx + 1) % 10 == 0:
                checkpoint_path = PICKLE_SAVE_PATH / f"{RUN_NAME}_checkpoint_batch_{batch_idx+1}.pkl"
                save_pickle(results, checkpoint_path)
                print(f"\nCheckpoint saved at batch {batch_idx+1}/{num_batches}")

    return results

def main():
    print(f"Starting SINGLE-PROCESS retroactive evaluation for: {RUN_NAME}")
    print(f"Run path: {RUN_PATH}")
    print(f"Metrics to evaluate: {METRICS}")
    print()

    # Check if the run path exists
    if not RUN_PATH.exists():
        print(f"ERROR: Run path does not exist: {RUN_PATH}")
        sys.exit(1)

    # Check if iteration 0 exists
    iteration_path = RUN_PATH / "0"
    if not iteration_path.exists():
        print(f"ERROR: Iteration 0 does not exist: {iteration_path}")
        sys.exit(1)

    print(f"Found iteration directory: {iteration_path}")
    print(f"Files in iteration: {list(iteration_path.glob('*.jsonl'))}")
    print()

    # Create evaluator (just for loading config and data)
    print(f"Using model: {backend_config['model_name']}")
    print(f"Using device: {DEVICE}")
    print(f"Batch size: {BATCH_SIZE}")
    print()

    evaluator = HFRetroactiveEvaluator(
        run_path=RUN_PATH,
        backend_config=backend_config,
        metrics=METRICS,
        batch_size=BATCH_SIZE,
        devices=[0],  # Not actually used in single-process mode
        env_config_name=None,
        max_trajs_per_env=None,
        benchmark=False,
    )

    print("Loading data...")
    iteration_number = 0
    last_turn_df = evaluator.load_last_turn_df_for_iteration(iteration_number)
    last_turn_df["iteration_number"] = iteration_number

    print(f"Loaded {len(last_turn_df)} trajectories")
    print(f"DataFrame columns: {list(last_turn_df.columns)}")
    print()

    # Convert to format expected by evaluator
    all_transcripts = last_turn_df.to_dict("records")
    all_transcripts_with_idx = list(enumerate(all_transcripts))

    print("="*80)
    print("Starting GPU evaluation (SINGLE-PROCESS, NO MULTIPROCESSING)")
    print("="*80)

    # Single-process evaluation
    results = evaluate_single_process(evaluator, all_transcripts_with_idx, BATCH_SIZE, DEVICE)

    print(f"\n✓ GPU evaluation completed! Got {len(results)} results")
    print("Saving raw results immediately...")

    # Sort results by index and extract scores
    sorted_results = [res[1] for res in sorted(results, key=lambda x: x[0])]

    # Create a simple results dataframe with just the scores
    raw_results_df = last_turn_df.copy()
    for metric in METRICS:
        raw_results_df[metric] = [result[metric] for result in sorted_results]

    # Save raw results immediately
    raw_csv_path = PICKLE_SAVE_PATH / f"{RUN_NAME}_iteration_{iteration_number}_RAW.csv"
    raw_results_df.to_csv(raw_csv_path, index=False)
    print(f"✓ Raw results saved to: {raw_csv_path}")

    raw_pickle_path = PICKLE_SAVE_PATH / f"{RUN_NAME}_iteration_{iteration_number}_RAW.pkl"
    save_pickle(raw_results_df, raw_pickle_path)
    print(f"✓ Raw results saved to: {raw_pickle_path}")

    # Print summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS (RAW SCORES)")
    print("="*80)

    for metric in METRICS:
        if metric in raw_results_df.columns:
            mean_val = raw_results_df[metric].mean()
            std_val = raw_results_df[metric].std()
            print(f"\n{metric}:")
            print(f"  Mean: {mean_val:.3f}")
            print(f"  Std:  {std_val:.3f}")
            print(f"  Min:  {raw_results_df[metric].min():.3f}")
            print(f"  Max:  {raw_results_df[metric].max():.3f}")

    # Try to add normalized scores (simple normalization, no risky post-processing)
    print("\n" + "="*80)
    print("Adding simple normalization (1-10 scale -> 0-1 scale)...")
    print("="*80)

    for metric in METRICS:
        # Assume 1-10 scale (from eval_prompts.yaml)
        raw_results_df[f"{metric}_normalized"] = (raw_results_df[metric] - 1) / 9
        mean_norm = raw_results_df[f"{metric}_normalized"].mean()
        print(f"{metric}_normalized: {mean_norm:.3f}")

    # Save with normalization
    final_csv_path = PICKLE_SAVE_PATH / f"{RUN_NAME}_iteration_{iteration_number}.csv"
    raw_results_df.to_csv(final_csv_path, index=False)
    print(f"\n✓ Final results saved to: {final_csv_path}")

    final_pickle_path = PICKLE_SAVE_PATH / f"{RUN_NAME}_iteration_{iteration_number}.pkl"
    save_pickle(raw_results_df, final_pickle_path)
    print(f"✓ Final results saved to: {final_pickle_path}")

    # Clean up checkpoints
    print("\nCleaning up checkpoint files...")
    for checkpoint_file in PICKLE_SAVE_PATH.glob(f"{RUN_NAME}_checkpoint_*.pkl"):
        checkpoint_file.unlink()
        print(f"Deleted: {checkpoint_file.name}")

    print("\n" + "="*80)
    print("✓ DONE! All results saved successfully.")
    print("="*80)

if __name__ == "__main__":
    main()
