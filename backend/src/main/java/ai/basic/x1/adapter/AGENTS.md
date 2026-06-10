<!-- Parent: ../../../../../../../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# adapter

## Purpose
Adapter layer of the clean architecture: everything that touches the outside world. Contains the Spring Boot entrypoint (`Application.java`), the REST API surface (`api/` — controllers, security filters, Spring config, background jobs), data transfer objects (`dto/`), the adapter-level exception type (`exception/ApiException.java`), and outbound ports (`port/` — MyBatis-Plus DAOs for MySQL, Redis DAOs, MinIO object storage, and HTTP RPC callers to external model services). This is the only package Spring component-scans (`scanBasePackages = "ai.basic.x1.adapter"`); usecase beans are registered manually in `api/config/CommonConfig.java`.

## Key Files
| File | Description |
|------|-------------|
| `Application.java` | Spring Boot main class; `@EnableScheduling`, excludes `UserDetailsServiceAutoConfiguration` |
| `api/controller/DataInfoController.java` | `/data/` endpoints: upload, query, annotation status, model runs, scenario/split operations; injects ~9 usecases |
| `api/controller/DatasetController.java` | `/dataset/` CRUD and statistics; typical pattern: validate DTO → `DefaultConverter.convert` to BO → usecase → convert BO back to DTO |
| `api/controller/UserController.java`, `ModelController.java`, `OntologyController.java`, `ClassController.java`, `ClassificationController.java`, `DatasetClassController.java`, `DatasetClassificationController.java`, `DataAnnotationController.java`, `DataFlowController.java`, `ModelRunRecordController.java`, `DatasetSimilarityJobController.java`, `DatasetSimilarityRecordController.java` | Per-module REST controllers (19 total); shared helpers in `BaseController.java`, `BaseDatasetController.java`, `BaseExportController.java` |
| `api/controller/CustomExceptionHandler.java` | `@RestControllerAdvice` mapping `ApiException`/`UsecaseException`/validation errors to `ApiResult` responses |
| `api/controller/CustomResponseWrapper.java` | Wraps controller return values into `ApiResult` |
| `api/config/CommonConfig.java` | Registers all 30+ UseCase classes as `@Bean`s (they are plain classes, not `@Component`s), plus `JwtHelper`, `PasswordEncoder`, Jackson builder, `LoggedUserArgumentResolver` |
| `api/config/SecurityConfig.java`, `api/filter/JwtAuthenticationFilter.java`, `api/filter/JwtHelper.java` | Spring Security + JWT bearer-token auth; filter builds `RequestContext` (user info, request info) and skips `/actuator/` |
| `api/config/MybatisPlusConfig.java`, `CustomerMetaObjectHandler.java` | MyBatis-Plus setup; auto-fills `createdAt`/`updatedAt`/`createdBy`/`updatedBy` from `RequestContextHolder` |
| `api/config/RedisConfig.java`, `JobConfig.java`, `MinioConfig.java`, `CacheConfig.java`, `LoggingConfig.java` | Redis stream templates/listener containers, thread-pool executors for model/similarity jobs, MinIO client, caching, request logging |
| `api/config/DatasetInitialInfo.java` (+ `PointCloudDatasetInitialInfo`, `ImageDatasetInitialInfo`) | `dataset-initial` config binding for trial datasets seeded at startup |
| `api/context/RequestContextHolder.java` (+ `RequestContext`, `UserInfo`, `RequestInfo`, strategy classes) | ThreadLocal request context used by usecases and meta-object handler |
| `api/job/DataModelJobConsumerListener.java`, `DatasetModelJobConsumerListener.java` | Redis Stream `StreamListener`s consuming model-run messages |
| `api/job/AbstractModelMessageHandler.java` + `ImageDetectionModelHandler.java`, `PointCloudDetectionModelMessageHandler.java`, `ModelRunSuccessHandler/FailureHandler/ErrorHandler.java`, `converter/` | Model message handling pipeline and request/response converters (COCO etc.) |
| `dto/ApiResult.java` | Generic response envelope `{code: UsecaseCode, message, data}` |
| `dto/*DTO.java`, `dto/request/`, `dto/response/` | ~55 top-level DTOs plus request/response variants (e.g. `DataInfoDTO`, `DatasetDTO`, `ModelRunDTO`, `request/DatasetRequestDTO` with validation groups `GroupInsert`) |
| `exception/ApiException.java` | Extends `UsecaseException` with `HttpStatus` and extra data map |
| `port/dao/AbstractDAO.java` | Generic base DAO reimplementing MyBatis-Plus `ServiceImpl`-style CRUD (`saveBatch`, `saveOrUpdateBatch`, `lambdaQuery`, `page`, logic-delete-aware removes) over `BaseMapper<T>` |
| `port/dao/*DAO.java` | 26 thin `@Component` DAOs, e.g. `DataInfoDAO extends AbstractDAO<DataInfoMapper, DataInfo>` (usually empty bodies) |
| `port/dao/mybatis/mapper/`, `model/`, `query/`, `typehandler/`, `extension/` | Mapper interfaces (paired with XML in `resources/mybatis/mapper/`), table models (`@TableName`, `JacksonTypeHandler` JSON columns, `IdType.AUTO`), query objects, and SQL injector extensions (`InsertBatchMethod`, `MysqlInsertOrUpdateBatch`, `ReplaceMethod`, `ExtendBaseMapper`) |
| `port/dao/redis/ModelSerialNoCountDAO.java`, `ModelSerialNoIncrDAO.java` | Redis-backed counters for model serial numbers |
| `port/minio/MinioService.java`, `ExtendMinioClient.java`, `MinioProp.java` | Bucket creation, uploads, presigned URLs against MinIO |
| `port/rpc/PointCloudDetectionModelHttpCaller.java`, `ImageDetectionModelHttpCaller.java`, `SimilarityHttpCaller.java`, `PointCloudConvertRenderHttpCaller.java` (+ `rpc/dto/`) | Hutool-HTTP callers to external Python model services, returning `ApiResult<...>` payloads |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `api/` | Controllers, Spring config, JWT filter, request context, annotations (`@LoggedUser`, `@ValidJSON`, `@ValidStringEnum`), Redis-stream jobs |
| `dto/` | API-facing data transfer objects (`request/`, `response/` subpackages) |
| `exception/` | `ApiException` (HTTP-aware exception) |
| `port/` | Outbound adapters: `dao/` (MyBatis-Plus + Redis), `minio/`, `rpc/` |

## For AI Agents
### Working In This Directory
- New usecases are NOT auto-scanned: add a `@Bean` method in `api/config/CommonConfig.java` (or another `@Configuration`) or they won't be injectable.
- Controllers never contain business logic; they validate, convert DTO↔BO with `DefaultConverter`, and delegate. Follow `DatasetController.create` as the canonical example.
- New tables need four artifacts: model in `port/dao/mybatis/model/`, mapper interface in `port/dao/mybatis/mapper/`, XML in `src/main/resources/mybatis/mapper/` (if custom SQL), and a `*DAO extends AbstractDAO<Mapper, Model>` component.
- Audit columns (`createdAt`, `createdBy`, `updatedAt`, `updatedBy`) are filled automatically via `CustomerMetaObjectHandler` reading `RequestContextHolder`; logic delete uses the `isDeleted` flag plus `delUniqueKey` pattern (see `model/DataInfo.java`).

### Testing Requirements
- No unit tests exist for this layer. Validate by `mvn package` and exercising endpoints against the Docker Compose stack (service on `:8080`).

### Common Patterns
- `ApiResult` envelope + `UsecaseCode` enum for all responses; throw `ApiException(UsecaseCode.X)` for controller-level errors.
- JSON columns mapped with `@TableField(typeHandler = JacksonTypeHandler.class)` and `@TableName(autoResultMap = true)`.
- Async model jobs flow through Redis Streams (`DataModelJobConsumerListener`) into `AbstractModelMessageHandler` subclasses, which call `port/rpc` HTTP callers.

## Dependencies
### Internal
- `ai.basic.x1.usecase` (controllers/filters/jobs call usecases; config instantiates them), `ai.basic.x1.entity` (BOs/enums), `ai.basic.x1.util` (`DefaultConverter`, `Page`, `Constants`, `DistributedLock`).

### External
- Spring Web/Security/Data-Redis, MyBatis-Plus (`com.baomidou`), MinIO SDK, JJWT, Hutool (`HttpUtil`, `JSONUtil`), Lombok, javax.validation/Hibernate Validator.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
