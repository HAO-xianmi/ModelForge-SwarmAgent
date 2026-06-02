"""Phase D: ingestion + data profiler tests with deterministic fixtures."""

from __future__ import annotations

import io
import zipfile

import pytest

from modelforge.common.errors import InputError
from modelforge.common.ids import new_run_id
from modelforge.services.ingestion import IngestionService, UploadedFile
from modelforge.services.profiling import DataProfiler

TINY_CSV = (
    "id,date,value,target\n"
    "1,2024-01-01,10.0,0\n"
    "2,2024-01-02,11.0,1\n"
    "3,2024-01-03,9.5,0\n"
    "4,2024-01-04,500.0,1\n"  # outlier in value
    "5,2024-01-05,10.5,0\n"
)


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
def test_ingest_txt_problem(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    svc = IngestionService(registry)
    manifest = svc.ingest(
        rid, [UploadedFile("problem_statement.txt", b"Forecast next month sales.")]
    )
    assert len(manifest.files) == 1
    f = manifest.files[0]
    assert f.role == "problem"
    assert f.extracted_text_available is True
    assert "Forecast next month sales." in manifest.problem_text


def test_ingest_csv_marks_tables(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    svc = IngestionService(registry)
    manifest = svc.ingest(rid, [UploadedFile("data.csv", TINY_CSV.encode())])
    f = manifest.files[0]
    assert f.role == "data"
    assert f.extracted_tables_available is True


def test_ingest_rejects_unsupported_extension(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    svc = IngestionService(registry)
    with pytest.raises(InputError):
        svc.ingest(rid, [UploadedFile("malware.exe", b"MZ...")])


def test_filename_sanitized_on_ingest(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    svc = IngestionService(registry)
    manifest = svc.ingest(rid, [UploadedFile("../../etc/notes.txt", b"hi")])
    assert manifest.files[0].normalized_name == "notes.txt"


@pytest.mark.security
def test_zip_path_traversal_rejected(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")
    svc = IngestionService(registry)
    with pytest.raises(InputError):
        svc.ingest(rid, [UploadedFile("bundle.zip", buf.getvalue())])


def test_zip_extracts_supported_members(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("problem.txt", "Solve it.")
        zf.writestr("data.csv", TINY_CSV)
        zf.writestr("ignore.exe", "binary")  # skipped, not an error
    svc = IngestionService(registry)
    manifest = svc.ingest(rid, [UploadedFile("bundle.zip", buf.getvalue())])
    names = {f.normalized_name for f in manifest.files}
    assert names == {"problem.txt", "data.csv"}


@pytest.mark.security
def test_oversized_upload_rejected(registry, make_run_dir, monkeypatch) -> None:
    from modelforge.common import config

    monkeypatch.setenv("MODELFORGE_MAX_UPLOAD_MB", "0")
    config.get_settings.cache_clear()
    rid = new_run_id()
    make_run_dir(rid)
    svc = IngestionService(registry)
    with pytest.raises(InputError):
        svc.ingest(rid, [UploadedFile("data.csv", b"x" * 2048)])
    config.get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Profiler
# --------------------------------------------------------------------------- #
def test_profiler_basic_stats() -> None:
    profile = DataProfiler().profile_csv_bytes("f1", "data.csv", TINY_CSV.encode())
    assert profile.row_count == 5
    assert profile.column_count == 4
    assert set(profile.column_names) == {"id", "date", "value", "target"}


def test_profiler_detects_outlier_not_deletes() -> None:
    profile = DataProfiler().profile_csv_bytes("f1", "data.csv", TINY_CSV.encode())
    value_col = next(c for c in profile.columns if c.name == "value")
    # 500.0 is an IQR outlier; it is COUNTED, and the row count is unchanged.
    assert value_col.candidate_outlier_count >= 1
    assert profile.row_count == 5  # nothing deleted


def test_profiler_detects_identifier_and_date() -> None:
    profile = DataProfiler().profile_csv_bytes("f1", "data.csv", TINY_CSV.encode())
    assert "id" in profile.potential_identifier_columns
    assert "date" in profile.date_columns


def test_profiler_missing_values() -> None:
    csv = "a,b\n1,\n2,5\n,7\n"
    profile = DataProfiler().profile_csv_bytes("f", "m.csv", csv.encode())
    a = next(c for c in profile.columns if c.name == "a")
    b = next(c for c in profile.columns if c.name == "b")
    assert a.missing_count == 1
    assert b.missing_count == 1


def test_profiler_duplicate_detection() -> None:
    csv = "a,b\n1,2\n1,2\n3,4\n"
    profile = DataProfiler().profile_csv_bytes("f", "d.csv", csv.encode())
    assert profile.duplicate_row_count == 1
