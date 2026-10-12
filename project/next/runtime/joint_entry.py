"""Guarded child only; instrumentation uses the existing pinned demo adapter."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from next.runtime import entry
from next.runtime.joint import session
entry.run_forward = session
if __name__ == '__main__': entry.main()
