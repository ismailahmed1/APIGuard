from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
FAULTS_DIR = ROOT / "apps" / "nexstock" / "faults"


def test_nexstock_fault_catalog_matches_patch_files_and_readme():
    faults = yaml.safe_load((FAULTS_DIR / "faults.yaml").read_text())
    fault_ids = [fault["id"] for fault in faults]
    patch_ids = sorted(path.stem for path in FAULTS_DIR.glob("F*.patch"))
    readme = (FAULTS_DIR / "README.md").read_text()

    assert fault_ids == patch_ids
    assert len(fault_ids) == len(set(fault_ids))
    assert all(f"| {fault_id.split('-', 1)[0]} |" in readme for fault_id in fault_ids)


def test_nexstock_fault_operations_use_method_and_api_path():
    faults = yaml.safe_load((FAULTS_DIR / "faults.yaml").read_text())

    for fault in faults:
        method, path = fault["operation"].split(" ", 1)
        assert method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
        assert path.startswith("/api/")
