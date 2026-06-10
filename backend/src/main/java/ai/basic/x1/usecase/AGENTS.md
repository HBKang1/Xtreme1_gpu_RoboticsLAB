<!-- Parent: ../../../../../../../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# usecase

## Purpose
Usecase layer: all business logic, organized as one plain Java class per domain module (29 usecases). These classes are not Spring-stereotyped components — they are instantiated as `@Bean`s in `adapter/api/config/CommonConfig.java` but use `@Autowired` field injection for DAOs and each other. Per the project's documented architecture exception, usecases call adapter-layer DAOs (`ai.basic.x1.adapter.port.dao.*`) directly instead of going through interfaces, since the MySQL/MyBatis stack is not intended to be swapped. Business errors are signaled with `UsecaseException` carrying a `UsecaseCode`.

## Key Files
| File | Description |
|------|-------------|
| `DataInfoUseCase.java` | Largest usecase (~1180 lines): data item querying/paging, upload coordination, deletion, scenario queries, split (train/val/test) handling |
| `DatasetUseCase.java` | Dataset CRUD, name-duplication checks (`DuplicateKeyException` → `DATASET_NAME_DUPLICATED`), initial trial-dataset seeding via `@PostConstruct` using `DatasetInitialInfo` config; uses `TtlRunnable` for async work |
| `DataAnnotationUseCase.java`, `DataAnnotationObjectUseCase.java`, `DataAnnotationClassificationUseCase.java`, `DataAnnotationRecordUseCase.java` | Annotation results, objects, classification values, and annotate/lock records |
| `DataFlowUseCase.java`, `DataEditUseCase.java` | Annotation workflow (lock/unlock data for annotating) and edit records |
| `UploadUseCase.java`, `UploadDataUseCase.java`, `ImageUploadUseCase.java`, `PointCloudUploadUseCase.java` | Upload pipeline: decompress archives, parse image/LiDAR structures, create data items and upload records |
| `ExportUseCase.java`, `ExportRecordUseCase.java` | Export of data + annotation results to files (export records track progress) |
| `FileUseCase.java` | File metadata persistence and MinIO-backed file handling |
| `ModelUseCase.java`, `ModelRecognitionUseCase.java`, `ModelRunRecordUseCase.java` | Model registry, triggering recognition runs, and run-record tracking |
| `DatasetSimilarityJobUseCase.java`, `DatasetSimilarityRecordUseCase.java` | Dataset similarity calculation jobs (calls external similarity service via adapter RPC) |
| `ClassUseCase.java`, `ClassificationUseCase.java`, `OntologyUseCase.java`, `DatasetClassUseCase.java`, `DatasetClassificationUseCase.java`, `DataClassificationOptionUseCase.java` | Ontology/class/classification management at global and per-dataset scope |
| `DatasetStatisticsUseCase.java` | Dataset-level statistics aggregation |
| `UserUseCase.java`, `UserTokenUseCase.java` | User registration/login (BCrypt via injected `PasswordEncoder`), JWT/API token management |
| `exception/UsecaseException.java` | RuntimeException carrying a `UsecaseCode` |
| `exception/UsecaseCode.java` | Enum of string error codes + messages (e.g. `DATASET_NOT_FOUND`, `USERNAME_AND_PASSWORD_NOT_MATCH`, `DATASET_DATA_OTHERS_ANNOTATING`); `OK` is the success code used in `ApiResult` |

## For AI Agents
### Working In This Directory
- Usecases accept and return `entity` BOs (never adapter DTOs); convert DAO models ↔ BOs with `DefaultConverter.convert(...)`.
- After adding a usecase class, register it in `adapter/api/config/CommonConfig.java` as a `@Bean` — there is no component scanning here.
- Use `@Transactional` on multi-write methods (see `DatasetUseCase`), and throw `new UsecaseException(UsecaseCode.X)` for business failures; add new codes to `UsecaseCode` rather than throwing generic exceptions.
- Async work must propagate request context: wrap runnables with `TtlRunnable.get(...)` (transmittable-thread-local) as `DatasetUseCase` does, because `RequestContextHolder` and the MyBatis audit-fill depend on it.
- Cross-usecase calls are common (e.g. `DatasetUseCase` injects `DataInfoUseCase`, `UploadDataUseCase`, `UserUseCase`); circular references are allowed (`spring.main.allow-circular-references: true`).

### Testing Requirements
- No existing unit tests. Changes are verified by building (`mvn package`) and exercising the corresponding controller endpoints against running MySQL/Redis/MinIO.

### Common Patterns
- Pagination via `ai.basic.x1.util.Page<T>` converted from MyBatis-Plus pages by `DefaultConverter.convert(page, TargetBO.class)`.
- Queries built with MyBatis-Plus `Wrappers`/`lambdaQuery()` on DAOs; batch writes via `AbstractDAO.saveBatch`/`saveOrUpdateBatch`.
- Distributed coordination (e.g. annotation locking) via `IDistributedLock` from `util/lock`, configured in `CommonConfig`.

## Dependencies
### Internal
- `ai.basic.x1.adapter.port.dao.*` (DAOs and mybatis models — the sanctioned layering exception), `ai.basic.x1.adapter.api.context.RequestContextHolder` (current user), `ai.basic.x1.adapter.api.config.DatasetInitialInfo` (seed config), `ai.basic.x1.entity` (BOs/enums), `ai.basic.x1.util` (converter, paging, constants, locks).

### External
- Spring (`@Autowired`, `@Transactional`, `@Value`), MyBatis-Plus toolkit (`Wrappers`), Hutool (`CollectionUtil`, `FileUtil`, `JSONUtil`, `IdUtil`), Lombok `@Slf4j`, Alibaba TTL.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
