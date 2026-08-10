import pandas as pd

from app.utilities.hashing import canonical_hash, sha256_file


class FingerprintService:
    algorithm_version = "fingerprint-1.0"

    def generate(self, file_path: str, frame: pd.DataFrame, metadata: dict, configuration_hash: str) -> dict:
        schema = [{"name": column, "dtype": str(frame[column].dtype)} for column in frame.columns]
        file_hash = sha256_file(file_path)
        schema_hash = canonical_hash(schema)
        metadata_hash = canonical_hash(metadata)
        combined = canonical_hash({"file": file_hash, "schema": schema_hash, "metadata": metadata_hash, "configuration": configuration_hash, "algorithm": self.algorithm_version})
        return {
            "file_hash": file_hash,
            "schema_hash": schema_hash,
            "metadata_hash": metadata_hash,
            "combined_fingerprint": combined,
            "fingerprint_json": {"schema": schema, "configuration_hash": configuration_hash, "row_count": len(frame), "column_count": len(frame.columns)},
            "algorithm_version": self.algorithm_version,
        }

