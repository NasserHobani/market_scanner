"""Machine learning foundation — data preparation, no model training."""

from .services import MLFoundationService
from .feature_registry import MLFeatureRegistry, FeatureDefinition, FeatureDataType, FeatureCategory
from .feature_vector import FeatureVectorBuilder, FeatureVector
from .feature_store import FeatureStore, MLDataset, MLDatasetRow
from .label_store import LabelStore, LabelDefinition, LabelName, LabelType
from .dataset_registry import DatasetRegistry, RegisteredDataset, new_dataset_id
from .dataset_export import DatasetExporter, ExportResult, ExportFormat
from .validation import DatasetValidator, ValidationResult, ValidationIssue
from .preprocessing import PreprocessingPipeline
from .metadata import DatasetMetadata, ExportMetadata, ML_FOUNDATION_VERSION

__all__ = [
    "MLFoundationService",
    "MLFeatureRegistry",
    "FeatureDefinition",
    "FeatureDataType",
    "FeatureCategory",
    "FeatureVectorBuilder",
    "FeatureVector",
    "FeatureStore",
    "MLDataset",
    "MLDatasetRow",
    "LabelStore",
    "LabelDefinition",
    "LabelName",
    "LabelType",
    "DatasetRegistry",
    "RegisteredDataset",
    "new_dataset_id",
    "DatasetExporter",
    "ExportResult",
    "ExportFormat",
    "DatasetValidator",
    "ValidationResult",
    "ValidationIssue",
    "PreprocessingPipeline",
    "DatasetMetadata",
    "ExportMetadata",
    "ML_FOUNDATION_VERSION",
]
