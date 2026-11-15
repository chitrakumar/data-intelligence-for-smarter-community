"""Helpers for running the workshop generator and app backend locally, without Spark
or a Databricks workspace.

- pyspark.sql.types and the databricks SDK/SQL connector are replaced with stubs.
- A fake SparkSession captures the pandas DataFrames the generator would write.
- uuid4 is made deterministic so generated tables can be compared by hash.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import itertools
import json
import os
import sys
import types
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Tuple

REPO = Path(__file__).resolve().parents[1]
INCLUDES = REPO / "workshop" / "Includes"
APP = INCLUDES / "reference_code" / "app"
GOLDEN = Path(__file__).resolve().parent / "golden"

GOLDEN_SCALE = 0.02  # small but exercises every generator path


# ----------------------------------------------------------------------------- stubs
def install_stubs() -> None:
    if "pyspark.sql.types" not in sys.modules:
        t = types.ModuleType("pyspark.sql.types")

        class StructField:
            def __init__(self, name, dataType, *a, **k):
                self.name, self.dataType = name, dataType

        class StructType:
            def __init__(self, fields):
                self.fields = fields

        t.StructType, t.StructField = StructType, StructField
        for n in "StringType DoubleType LongType IntegerType BooleanType TimestampType DateType".split():
            setattr(t, n, type(n, (), {}))
        sys.modules.update({"pyspark": types.ModuleType("pyspark"),
                            "pyspark.sql": types.ModuleType("pyspark.sql"), "pyspark.sql.types": t})
    try:  # the app's server/config.py + sql.py import these at module load
        import databricks.sdk  # noqa: F401
        import databricks.sql  # noqa: F401
    except ImportError:
        db = types.ModuleType("databricks")
        sdk = types.ModuleType("databricks.sdk")
        sdk.WorkspaceClient = type("WorkspaceClient", (), {"__init__": lambda self, *a, **k: None})
        dsql = types.ModuleType("databricks.sql")
        db.sdk, db.sql = sdk, dsql
        sys.modules.update({"databricks": db, "databricks.sdk": sdk, "databricks.sql": dsql})


class _FakeSpark:
    def __init__(self):
        self.tables: Dict[str, object] = {}
        spark = self

        class _W:
            def __init__(self, df): self.df = df
            def mode(self, *a): return self
            def option(self, *a): return self
            def saveAsTable(self, fqn): spark.tables[fqn.split(".")[-1]] = self.df

        self._W = _W

    def sql(self, q):
        return None

    def createDataFrame(self, df, schema=None):
        return types.SimpleNamespace(write=self._W(df))


def df_digest(df) -> str:
    """Content hash that is stable across pandas versions (fixed float formatting)."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # .round() is a no-op on datetime columns
        csv = df.round(6).to_csv(index=False, float_format="%.6f")
    return hashlib.sha256(csv.encode()).hexdigest()[:16]


@contextmanager
def _deterministic_uuid():
    orig = uuid.uuid4
    counter = itertools.count()
    uuid.uuid4 = lambda: uuid.UUID(int=next(counter))
    try:
        yield
    finally:
        uuid.uuid4 = orig


def run_generator(includes_dir: Path = INCLUDES, scale: float = GOLDEN_SCALE, seed: int = 42, **kwargs):
    """Import smart_campus_generators from includes_dir and run generate_telemetry.

    Returns {table_name: pandas.DataFrame}.
    """
    install_stubs()
    sys.path.insert(0, str(includes_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            f"scg_{abs(hash(str(includes_dir)))}", includes_dir / "smart_campus_generators.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        spark = _FakeSpark()
        with _deterministic_uuid(), open(os.devnull, "w") as devnull:
            stdout, sys.stdout = sys.stdout, devnull
            try:
                mod.generate_telemetry(spark, "c", "bronze", scale=scale, seed=seed, **kwargs)
            finally:
                sys.stdout = stdout
        return spark.tables
    finally:
        sys.path.remove(str(includes_dir))


def telemetry_digests(tables) -> Dict[str, Tuple[int, str]]:
    return {k: (len(v), df_digest(v)) for k, v in sorted(tables.items())}


# ----------------------------------------------------------------------------- app
def load_app_modules(app_dir: Path = APP, campus_dir: Path = None):
    """Fresh import of the app's server package (optionally for a given campus profile dir)."""
    install_stubs()
    for name in [m for m in sys.modules if m == "server" or m.startswith("server.") or m == "app"]:
        del sys.modules[name]
    if campus_dir is not None:
        os.environ["CAMPUS_DIR"] = str(campus_dir)
    else:
        os.environ.pop("CAMPUS_DIR", None)
    sys.path.insert(0, str(app_dir))
    try:
        geometry = importlib.import_module("server.geometry")
        datasets = importlib.import_module("server.datasets")
        return geometry, datasets
    finally:
        sys.path.remove(str(app_dir))


def app_digests(geometry, datasets) -> Dict[str, object]:
    return {
        "zone_map": geometry.ZONE_MAP,
        "campus_polygons": hashlib.sha256(
            json.dumps(geometry.get_campus_polygons(), sort_keys=True).encode()).hexdigest()[:16],
        "labels": {k: v[0] for k, v in datasets.DATASETS.items()},
    }
