<!-- Parent: ../../../../../../../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# entity

## Purpose
Entity layer: pure business objects (BOs) and domain enums with no framework dependencies beyond Lombok. ~80 `*BO` classes mirror domain concepts (datasets, data items, annotations, classes/ontologies, models, exports, uploads, users) and are the currency between controllers and usecases: adapter DTOs are converted to BOs on the way in, and DAO table models are converted to BOs on the way out, both via `util/DefaultConverter`. The `enums/` subpackage holds 31 domain enums shared by all layers (including the MyBatis models in the adapter layer, which persist them directly).

## Key Files
| File | Description |
|------|-------------|
| `DataInfoBO.java` | Core data-item BO: id, datasetId/datasetName, name/orderName, content file tree, status (`DataStatusEnum`), annotation status, split type |
| `DatasetBO.java`, `DatasetQueryBO.java`, `DatasetStatisticsBO.java`, `DatasetScenarioBO.java` | Dataset domain and its query/statistics objects |
| `DataInfoQueryBO.java`, `BaseQueryBO.java`, `ScenarioQueryBO.java`, `RunRecordQueryBO.java` | Query parameter objects passed from controllers to usecases |
| `DataAnnotationObjectBO.java`, `DataAnnotationClassificationBO.java`, `DataAnnotationRecordBO.java`, `DataAnnotationResultBO.java`, `DataEditBO.java`, `LockRecordBO.java` | Annotation results, classification values, annotate-session records and data locking |
| `ClassBO.java`, `ClassificationBO.java`, `OntologyBO.java`, `DatasetClassBO.java`, `DatasetClassificationBO.java`, `DataClassificationOptionBO.java` | Ontology/class/classification domain |
| `ModelBO.java`, `ModelClassBO.java`, `ModelMessageBO.java`, `ModelRunBO.java`, `ModelRunRecordBO.java`, `ModelDataResultBO.java`, `ModelDatasetResultBO.java`, `ModelTaskInfoBO.java`, `ImageDetectionObjectBO.java`, `PointCloudDetectionObjectBO.java`, `PointCloudDetectionParamBO.java` | Model-run domain: messages, run records, per-data/per-dataset results, detection objects |
| `DataExportBO.java`, `DataExportBaseBO.java`, `DataResultExportBO.java`, `ExportDataFileBaseBO.java` + `ExportDataImageFileBO`/`ExportDataLidarPointCloudFileBO`/`ExportDataCameraConfigFileBO`/`ExportDataTextFileBO`, `LidarBasicDataExportBO.java`, `LidarFusionDataExportBO.java`, `ImageDataExportBO.java`, `TextDataExportBO.java`, `ExportRecordBO.java` | Export format hierarchy per dataset type (image / LiDAR basic / LiDAR fusion / text) |
| `DataInfoUploadBO.java`, `UploadRecordBO.java`, `DataImportResultBO.java`, `FileBO.java`, `RelationFileBO.java`, `PresignedUrlBO.java` | Upload/file domain (MinIO presigned URLs, file relations) |
| `DatasetSimilarityBO.java`, `DatasetSimilarityJobBO.java`, `DatasetSimilarityRecordBO.java`, `DataSimilarityBO.java` | Dataset similarity domain |
| `UserBO.java`, `UserTokenBO.java`, `LoggedUserBO.java` | User/auth domain |
| `ClassAndClassificationImportBO.java`, `ClassAndClassificationExportBO.java` | Ontology import/export payloads |
| `enums/DatasetTypeEnum.java` | `IMAGE` / `LIDAR_FUSION` / etc. — drives upload parsing and export format selection |
| `enums/DataStatusEnum.java`, `DataAnnotationStatusEnum.java`, `SplitTypeEnum.java`, `ItemTypeEnum.java` | Persisted directly on the `data` table model |
| `enums/ModelCodeEnum.java`, `RunStatusEnum.java`, `ToolTypeEnum.java`, `ObjectTypeEnum.java`, `SortEnum.java`, `TokenType.java` (+25 more) | Remaining domain enums for models, tools, sorting, tokens, uploads, similarity |

## For AI Agents
### Working In This Directory
- Keep this layer dependency-free: BOs use only Lombok (`@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`) and JDK types (`OffsetDateTime`, collections). Never import Spring, MyBatis, or adapter classes here.
- Field names matter: `DefaultConverter` uses Hutool `BeanUtil` property copying, so BO fields must align by name with the corresponding DTO (`adapter/dto`) and table model (`adapter/port/dao/mybatis/model`) to convert correctly.
- Enums added here may be persisted as-is by MyBatis models — keep enum constant names stable or coordinate with DB values.

### Testing Requirements
- No tests target this package. Conversion mismatches (renamed/missing fields) fail silently as `null` values, so manually verify end-to-end after renaming fields.

### Common Patterns
- BO-per-table plus purpose-specific BOs (query BOs, export BOs, upload BOs) rather than reusing one class for all flows.
- Inheritance for export formats: `ExportDataFileBaseBO` and `DataExportBaseBO` subclassed per dataset type.

## Dependencies
### Internal
- `entity/enums` only (BOs reference their own enums). Consumed by `adapter` and `usecase` layers.

### External
- Lombok; JDK standard library.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
