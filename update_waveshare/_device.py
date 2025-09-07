"""Device factory and small wrapper around IT8951 display classes.
"""
from typing import Optional
from pathlib import Path
import sys


def _ensure_it8951_in_path():
    try:
        import IT8951  # noqa: F401
        return
    except Exception:
        # try to locate the local IT8951 package relative to this file
        here = Path(__file__).resolve().parent.parent
        cand = here / 'IT8951' / 'src'
        if cand.exists():
            sys.path.insert(0, str(cand))
            try:
                import IT8951  # noqa: F401
                return
            except Exception:
                pass
        # also try build/lib path
        cand2 = here / 'IT8951' / 'build' / 'lib.linux-aarch64-cpython-311'
        if cand2.exists():
            sys.path.insert(0, str(cand2))
            try:
                import IT8951  # noqa: F401
                return
            except Exception:
                pass


def create_device(vcom: float = -2.06, rotate: Optional[str] = None, mirror: bool = False, virtual: bool = False, dims=(800,600)):
    """Return an initialized display object.

    If virtual is True, returns VirtualEPDDisplay(dims).
    Otherwise returns AutoEPDDisplay(vcom=vcom, rotate=rotate, mirror=mirror).
    """
    _ensure_it8951_in_path()

    if virtual:
        from IT8951.display import VirtualEPDDisplay
        return VirtualEPDDisplay(dims=dims, rotate=rotate, mirror=mirror)

    from IT8951.display import AutoEPDDisplay
    return AutoEPDDisplay(vcom=vcom, rotate=rotate, mirror=mirror)
