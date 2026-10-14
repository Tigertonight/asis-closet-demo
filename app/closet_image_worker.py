"""Resource boundary for optional local closet models (never import in the API process)."""
from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

# One local model at a time; fail closed rather than queue behind a stalled model.
_SLOT = threading.BoundedSemaphore(1)
MAX_SIDE = 1536
MEMORY_MB = 768
TIMEOUT_SECONDS = 25
_BUDGET = ContextVar("closet_model_budget", default=None)


@contextmanager
def fallback_budget():
    token = _BUDGET.set(1)
    try:
        yield
    finally:
        _BUDGET.reset(token)


def fallback_exhausted() -> bool:
    remaining = _BUDGET.get()
    return remaining is not None and remaining <= 0


def _memory_available() -> bool:
    try:
        values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        return int(values["MemAvailable"].split()[0]) >= (MEMORY_MB + 256) * 1024
    except (OSError, KeyError, ValueError):
        return False


def run_image_worker(image, operation: str, *, model_id: str | None = None):
    from PIL import Image

    remaining = _BUDGET.get()
    if remaining is not None and remaining <= 0:
        _log(operation, "budget_exhausted")
        return None
    if remaining is not None:
        _BUDGET.set(remaining - 1)
    if sys.platform != "linux":
        _log(operation, "unsupported_resource_limits")
        return None
    if not _memory_available():
        _log(operation, "low_memory")
        return None
    if not _SLOT.acquire(blocking=False):
        _log(operation, "busy")
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="selfit-matting-") as directory:
            source = Path(directory) / "input.png"
            target = Path(directory) / "output.png"
            bounded = image.copy()
            bounded.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            bounded.save(source)
            bounded.close()
            env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
            if model_id:
                env["SELFIT_SEGFORMER_MODEL"] = model_id
            command = [sys.executable, str(Path(__file__).resolve()), operation,
                       str(source), str(target), str(MEMORY_MB)]
            try:
                # No preexec_fn: this is called from a multithreaded web server.
                result = subprocess.run(command, env=env, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                # subprocess.run kills and reaps the child before raising.
                _log(operation, "timeout")
                return None
            if result.returncode or not target.exists():
                _log(operation, "worker_failed", returncode=result.returncode)
                return None
            with Image.open(target) as output:
                if output.width * output.height > MAX_SIDE * MAX_SIDE:
                    _log(operation, "oversize_output")
                    return None
                decoded = output.convert("L" if operation == "segment" else "RGBA")
                decoded.load()
            if operation == "segment":
                decoded.info["labels"] = json.loads(Path(str(target) + ".labels.json").read_text())
            _log(operation, "completed")
            return decoded
    except Exception as exc:
        _log(operation, "error", error_type=type(exc).__name__)
        return None
    finally:
        _SLOT.release()


def _log(operation, outcome, **extra):
    logging.getLogger("uvicorn.error").info(json.dumps({
        "event": "closet_image_worker", "operation": operation, "outcome": outcome,
        "memory_limit_mb": MEMORY_MB, "timeout_seconds": TIMEOUT_SECONDS, **extra,
    }))


def _main():
    import resource

    operation, source, target, memory = sys.argv[1:]
    limit = int(memory) * 1024 * 1024
    # Set limits BEFORE importing native/model libraries. Address-space includes
    # weights, tensors, thread stacks and allocator reservations, not just Python.
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CPU, (20, 21))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024,) * 2)
    from PIL import Image

    with Image.open(source) as raw:
        if raw.width * raw.height > MAX_SIDE * MAX_SIDE:
            raise ValueError("oversize input")
        image = raw.convert("RGB")
    if operation == "matte":
        # Explicit lightweight model; do not inherit rembg's changing default or
        # download a model during a user request. Missing cache means skip safely.
        model_root = Path(os.environ.get("U2NET_HOME", str(Path.home() / ".u2net")))
        if not (model_root / "u2netp.onnx").is_file():
            raise FileNotFoundError("lightweight matting model not provisioned")
        from rembg import new_session, remove
        session = new_session("u2netp", providers=["CPUExecutionProvider"])
        remove(image, session=session).save(target)
    elif operation == "segment":
        import torch
        from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation
        torch.set_num_threads(1)
        model_id = os.environ.get("SELFIT_SEGFORMER_MODEL", "mattmdjaga/segformer_b2_clothes")
        processor = AutoImageProcessor.from_pretrained(model_id, local_files_only=True)
        model = AutoModelForSemanticSegmentation.from_pretrained(model_id, local_files_only=True).eval()
        with torch.inference_mode():
            logits = model(**processor(images=image, return_tensors="pt")).logits
            logits = torch.nn.functional.interpolate(logits, size=image.size[::-1], mode="bilinear", align_corners=False)
            labels = logits.argmax(dim=1)[0].byte().numpy()
        Image.fromarray(labels).resize(image.size, Image.Resampling.NEAREST).save(target)
        # Label mapping is small and belongs to this exact model.
        Path(target + ".labels.json").write_text(json.dumps(model.config.id2label))
    else:
        raise ValueError("unknown operation")


if __name__ == "__main__":
    try:
        _main()
    except MemoryError:
        sys.exit(75)
    except FileNotFoundError:
        sys.exit(72)
    except Exception:
        sys.exit(70)

