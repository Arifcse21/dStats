# All metadata lives in pyproject.toml; this file only wires in the optional Rust extension.
import os

from setuptools import setup
from setuptools_rust import Binding, RustExtension

# DSTATS_PURE_PYTHON=1 builds the py3-none-any wheel that pip falls back to on
# platforms without a prebuilt native wheel
if os.environ.get("DSTATS_PURE_PYTHON"):
    rust_extensions = []
    options = {}
else:
    rust_extensions = [
        RustExtension(
            "dStats._rust",
            path="rust/Cargo.toml",
            binding=Binding.PyO3,
            py_limited_api="auto",
            # Building from source without a Rust toolchain still installs dStats,
            # just without the accelerator
            optional=True,
            # Build exactly the dependency versions in Cargo.lock
            args=["--locked"],
        )
    ]
    options = {"bdist_wheel": {"py_limited_api": "cp312"}}

setup(rust_extensions=rust_extensions, options=options)
