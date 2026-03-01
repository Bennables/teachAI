"""
Change-based keyframe extraction for workflow video analysis.
Captures interaction moments, not uniform time samples.
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Generator
import logging

logger = logging.getLogger(__name__)

# Configuration constants - Tuned for UI workflow capture
CHANGE_THRESHOLD = 0.015   # Less sensitive to avoid micro-changes, focus on UI transitions
MAX_FRAMES = 8            # Reasonable number for workflow analysis
CONTEXT_FRAMES = 0        # No context frames for cleaner workflow capture
MIN_FRAME_GAP = 60        # Larger gap to ensure temporal distribution (60 frames ~ 2 seconds at 30fps)
POST_CHANGE_OFFSET = 0    # Capture exact state, not after change
MIN_KEYFRAMES = 6         # More keyframes for better workflow coverage
MIN_TIME_GAP_SECONDS = 3.0  # Minimum 3 seconds between keyframes for UI workflows
DEDUPE_DIFF_THRESHOLD = 0.02   # Drop near-identical keyframes (not used with deduplication disabled)


def compute_frame_difference(frame1: np.ndarray, frame2: np.ndarray) -> float:
    """
    Compute visual difference between two frames using histogram comparison.

    Returns:
        Difference score between 0.0 (identical) and 1.0 (completely different)
    """
    # Convert to grayscale
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

    # Compute histograms
    hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
    hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])

    # Normalize histograms
    cv2.normalize(hist1, hist1)
    cv2.normalize(hist2, hist2)

    # Compare using correlation (1 = identical, -1 = opposite)
    correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)

    # Add a lightweight pixel-delta signal for subtle UI changes (cursor/typing).
    small1 = cv2.resize(gray1, (160, 90), interpolation=cv2.INTER_AREA)
    small2 = cv2.resize(gray2, (160, 90), interpolation=cv2.INTER_AREA)
    pixel_delta = float(np.mean(cv2.absdiff(small1, small2))) / 255.0

    # Blend histogram and pixel signals.
    hist_diff = max(0.0, 1.0 - correlation)
    return (0.6 * hist_diff) + (0.4 * pixel_delta)


def extract_keyframes(
    video_path: str | Path,
    output_dir: str | Path,
    change_threshold: float = CHANGE_THRESHOLD,
    max_frames: int = MAX_FRAMES,
    context_frames: int = CONTEXT_FRAMES,
    min_keyframes: int = MIN_KEYFRAMES,
    dedupe_diff_threshold: float = DEDUPE_DIFF_THRESHOLD,
    target_fps: float = 15.0,
) -> list[Path]:
    """
    Extract keyframes from video based on visual changes.

    Captures frames where significant visual changes occur (user interactions)
    plus context frames before and after each change.

    Args:
        video_path: Path to input video file
        output_dir: Directory to save extracted frames
        change_threshold: Minimum difference to trigger keyframe
        max_frames: Maximum number of frames to extract
        context_frames: Number of frames to capture around each change
        target_fps: FPS to subsample at during analysis (default 2.0)

    Returns:
        List of paths to extracted keyframe images
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Subsample: only analyze every Nth frame to match target_fps
    sample_every = max(1, int(round(fps / target_fps))) if fps and fps > 0 else 1

    logger.info(f"[Extractor] Video: {total_frames} frames, {fps:.1f} FPS (sampling every {sample_every} frames → ~{fps/sample_every:.1f} FPS)")

    # First pass: identify change points
    change_points: list[int] = []
    diff_scores: list[float] = []
    prev_frame = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_every == 0:
            if prev_frame is not None:
                diff = compute_frame_difference(prev_frame, frame)
                diff_scores.append(diff)

            prev_frame = frame.copy()

        frame_idx += 1

    effective_total_frames = frame_idx if frame_idx > 0 else total_frames

    # Adaptive threshold + top-K local-peak selection to focus on significant changes.
    if diff_scores:
        arr = np.array(diff_scores, dtype=np.float32)
        adaptive_threshold = max(
            change_threshold,
            float(np.percentile(arr, 97)),
            float(arr.mean() + (3.0 * arr.std())),
        )
        peak_candidates: list[tuple[int, float]] = []
        for i, score in enumerate(diff_scores):
            idx = i + 1  # diff_scores[i] compares frame i to i+1
            prev_score = diff_scores[i - 1] if i > 0 else score
            next_score = diff_scores[i + 1] if i < len(diff_scores) - 1 else score
            is_local_peak = score >= prev_score and score >= next_score

            if score >= adaptive_threshold and is_local_peak:
                peak_candidates.append((idx, score))

        # Keep strongest transitions within budget and spacing constraints.
        max_change_points = max(0, max_frames - 2)
        chosen: list[int] = []
        for idx, _score in sorted(peak_candidates, key=lambda x: x[1], reverse=True):
            if all(abs(idx - c) >= MIN_FRAME_GAP for c in chosen):
                chosen.append(idx)
            if len(chosen) >= max_change_points:
                break
        change_points = sorted(chosen)

    logger.info(
        f"[Extractor] Detected {len(change_points)} change points "
        f"(decoded frames: {effective_total_frames})"
    )

    # Second pass: extract keyframes with context
    frames_to_extract: set[int] = set()

    for cp in change_points:
        # Add context frames around each change point
        for offset in range(-context_frames, context_frames + 1):
            target_frame = cp + offset
            if 0 <= target_frame < effective_total_frames:
                frames_to_extract.add(target_frame)
        post_change = cp + POST_CHANGE_OFFSET
        if 0 <= post_change < effective_total_frames:
            frames_to_extract.add(post_change)

    # Also add first and last frames
    frames_to_extract.add(0)
    if effective_total_frames > 1:
        frames_to_extract.add(effective_total_frames - 1)

    # For workflow videos, ensure temporal distribution regardless of change detection
    # This is critical for capturing different stages of UI interactions
    video_duration_seconds = effective_total_frames / sample_every / fps if fps > 0 else 30
    logger.info(f"[Extractor] Video duration: {video_duration_seconds:.1f} seconds")

    # Always add temporally distributed keyframes for workflow coverage
    temporal_keyframes = max(min_keyframes, min(8, int(video_duration_seconds / MIN_TIME_GAP_SECONDS) + 1))
    logger.info(f"[Extractor] Adding {temporal_keyframes} temporal keyframes for workflow coverage")

    temporal_indices = np.linspace(0, effective_total_frames - 1, num=temporal_keyframes, dtype=int)
    for idx in temporal_indices:
        frames_to_extract.add(int(idx))

    # Add change-based keyframes but enforce minimum time gaps
    safe_fps = fps if fps and fps > 0 else 30.0
    min_frame_gap_temporal = int(MIN_TIME_GAP_SECONDS * sample_every * safe_fps / fps) if fps > 0 else MIN_FRAME_GAP

    change_keyframes = []
    for cp in change_points:
        # Only add if it's far enough from existing keyframes
        too_close = False
        for existing_idx in frames_to_extract:
            if abs(cp - existing_idx) < min_frame_gap_temporal:
                too_close = True
                break
        if not too_close:
            change_keyframes.append(cp)
            frames_to_extract.add(cp)

    logger.info(f"[Extractor] Added {len(change_keyframes)} change-based keyframes with temporal constraints")

    # Sort and prune frame indices to avoid near-duplicates in rapid bursts.
    sorted_frames = sorted(frames_to_extract)
    pruned_frames: list[int] = []
    for idx in sorted_frames:
        if not pruned_frames or (idx - pruned_frames[-1]) >= MIN_FRAME_GAP:
            pruned_frames.append(idx)
    sorted_frames = pruned_frames

    # Limit to max_frames if too many
    if len(sorted_frames) > max_frames:
        # Keep first/last, distribute remaining evenly across sorted frames
        step = len(sorted_frames) // (max_frames - 2)
        limited_frames = [sorted_frames[0]]  # First frame
        for i in range(step, len(sorted_frames) - 1, step):
            limited_frames.append(sorted_frames[i])
        limited_frames.append(sorted_frames[-1])  # Last frame
        sorted_frames = limited_frames

    logger.info(f"[Extractor] Extracting {len(sorted_frames)} keyframes")
    

    # Third pass: extract and save frames using sequential reads.
    # Random seek via CAP_PROP_POS_FRAMES is unreliable for some MOV codecs.
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    extracted_paths: list[Path] = []
    target_set = set(sorted_frames)
    frame_idx = 0
    safe_fps = fps if fps and fps > 0 else 1.0
    last_saved_frame: np.ndarray | None = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx in target_set:
            # Skip deduplication for workflow videos - UI changes can be very subtle
            # but still represent important state transitions
            # if last_saved_frame is not None:
            #     sim_diff = compute_frame_difference(last_saved_frame, frame)
            #     if sim_diff < dedupe_diff_threshold:
            #         logger.info(f"[Extractor] Skipped frame {frame_idx} (similarity: {sim_diff:.4f} < {dedupe_diff_threshold:.4f})")
            #         frame_idx += 1
            #         continue

            timestamp_ms = frame_idx * 1000 / safe_fps
            frame_filename = f"frame_{frame_idx:06d}_{timestamp_ms:.0f}ms.jpg"
            frame_path = output_dir / frame_filename

            cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            extracted_paths.append(frame_path)
            last_saved_frame = frame.copy()
            logger.info(f"[Extractor] Saved frame {frame_idx} -> {frame_filename}")

            # Fast exit once all requested frames are captured.
            if len(extracted_paths) >= len(target_set):
                break

        frame_idx += 1

    cap.release()

    logger.info(f"[Extractor] Successfully extracted {len(extracted_paths)} keyframes to {output_dir}")
    return extracted_paths


def extract_keyframes_from_changes(
    video_path: str | Path,
    output_dir: str | Path | None = None,
    **kwargs
) -> list[Path]:
    """
    Convenience function for extracting keyframes.

    Args:
        video_path: Path to video file
        output_dir: Output directory (defaults to temp dir based on video name)
        **kwargs: Additional arguments for extract_keyframes()

    Returns:
        List of paths to extracted keyframe images
    """
    video_path = Path(video_path)

    if output_dir is None:
        # Create temp directory based on video name
        output_dir = video_path.parent / f"{video_path.stem}_keyframes"

    return extract_keyframes(video_path, output_dir, **kwargs)


def cleanup_keyframes(keyframe_dir: str | Path) -> None:
    """
    Remove extracted keyframes directory.

    Args:
        keyframe_dir: Directory containing keyframes to remove
    """
    keyframe_dir = Path(keyframe_dir)
    if keyframe_dir.exists():
        for frame_file in keyframe_dir.glob("*.jpg"):
            frame_file.unlink()
        keyframe_dir.rmdir()
        logger.info(f"[Extractor] Cleaned up keyframes at {keyframe_dir}")
