"""One place to choose where PyTorch runs.

Order: the S2E_DEVICE environment variable (cpu / mps / cuda), else the Mac GPU
(MPS), else CUDA, else CPU. Every script also takes --device, which sets S2E_DEVICE.

  S2E_DEVICE=cpu python app.py --index data/world_z6
  python app.py --index data/world_z6 --device cpu
"""
import os


def device_name():
    import torch
    want = os.environ.get("S2E_DEVICE", "").strip().lower()
    if want in ("cpu", "mps", "cuda"):
        if want == "mps" and not torch.backends.mps.is_available():
            print("[device] MPS not available, using CPU")
            return "cpu"
        if want == "cuda" and not torch.cuda.is_available():
            print("[device] CUDA not available, using CPU")
            return "cpu"
        return want
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def setup_cpu_threads():
    """Use the performance cores well on Apple Silicon without starving the system."""
    import torch
    n = os.cpu_count() or 4
    torch.set_num_threads(max(1, n - 1))


def add_device_arg(parser):
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default="auto",
                        help="where PyTorch runs (default: Mac GPU if available). cpu works everywhere.")


def apply_device_arg(args):
    if getattr(args, "device", "auto") != "auto":
        os.environ["S2E_DEVICE"] = args.device
