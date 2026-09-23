"""
Script to recompute and display precision/recall metrics and pass rates for historical evaluation result files.
Usage:
    python scripts/rescore_results.py [path_to_results.json] [--recall-threshold=0.5] [--precision-threshold=0.5]
"""
import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_evaluation import compute_citation_metrics


def rescore(file_path: Path, recall_thresh: float = 0.5, prec_thresh: float = 0.5):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    print(f"\nRescoring {file_path.name} ({len(cases)} cases)")
    print(f"Thresholds: Recall >= {recall_thresh} | Precision >= {prec_thresh}")
    print("=" * 95)

    old_passes = 0
    fixed_passes = 0
    shape_passes = 0
    precisions = []
    recalls = []
    f1s = []

    print(f"{'ID':<9} | {'Exp':<3} | {'Ver':<3} | {'Precision':<9} | {'Recall':<6} | {'F1':<5} | {'Old':<5} | {'Fixed':<6} | {'Shape':<6} | Expected vs Verified")
    print("-" * 95)

    for c in cases:
        exp = c.get("expected_sections", [])
        ver = c.get("verified_sections", [])
        is_verified = c.get("verified", False)
        old_pass = c.get("passed_full_verification", False)

        metrics = compute_citation_metrics(
            verified_sections=ver,
            expected_sections=exp,
            recall_threshold=recall_thresh,
            precision_threshold=prec_thresh,
        )

        p_fixed = bool(is_verified and metrics["citation_match_fixed"])
        p_shape = bool(is_verified and metrics["citation_match_shape_aware"])
        if old_pass:
            old_passes += 1
        if p_fixed:
            fixed_passes += 1
        if p_shape:
            shape_passes += 1

        precisions.append(metrics["precision"])
        recalls.append(metrics["recall"])
        f1s.append(metrics["f1"])

        diff_str = f"Exp:{exp} -> Ver:{ver}"
        if len(diff_str) > 30:
            diff_str = diff_str[:27] + "..."

        print(
            f"{c.get('id', 'N/A'):<9} | {len(exp):<3} | {len(ver):<3} | "
            f"{metrics['precision']:<9.2f} | {metrics['recall']:<6.2f} | {metrics['f1']:<5.2f} | "
            f"{str(old_pass):<5} | {str(p_fixed):<6} | {str(p_shape):<6} | {diff_str}"
        )

    n = len(cases)
    mean_p = sum(precisions) / n if n else 0.0
    mean_r = sum(recalls) / n if n else 0.0
    mean_f1 = sum(f1s) / n if n else 0.0

    print("=" * 95)
    print("PRIMARY HEADLINE CITATION METRICS (Continuous Distributions):")
    print(f"  Mean Citation Precision:               {mean_p*100:.1f}%")
    print(f"  Mean Citation Recall:                  {mean_r*100:.1f}%")
    print(f"  Mean Citation F1:                      {mean_f1:.3f}")
    print("-" * 95)
    print("SECONDARY PASS RATES (Threshold Sensitivity Analysis):")
    print(f"  Old Naive Overlap Pass Rate:           {old_passes}/{n} ({old_passes/n*100:.1f}%)" if n else "N/A")
    print(f"  Fixed Pass Rate (Rec >= {recall_thresh}, Prec >= {prec_thresh}):    {fixed_passes}/{n} ({fixed_passes/n*100:.1f}%)" if n else "N/A")
    print(f"  Shape-Aware Pass Rate (<=2: >=0.6, >2: >=0.5): {shape_passes}/{n} ({shape_passes/n*100:.1f}%)" if n else "N/A")
    print("=" * 95)


if __name__ == "__main__":
    target = PROJECT_ROOT / "data" / "eval" / "results_20260923_093816.json"
    rec_th = 0.5
    prec_th = 0.5

    for arg in sys.argv[1:]:
        if arg.startswith("--recall-threshold="):
            rec_th = float(arg.split("=")[1])
        elif arg.startswith("--precision-threshold="):
            prec_th = float(arg.split("=")[1])
        elif not arg.startswith("--"):
            target = Path(arg)

    if not target.is_absolute():
        target = PROJECT_ROOT / target

    rescore(target, rec_th, prec_th)
