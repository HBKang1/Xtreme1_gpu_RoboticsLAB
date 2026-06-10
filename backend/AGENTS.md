<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# backend

## Purpose
Java 11 Spring Boot 2.6.6 service (`ai.basic:xtreme1-backend`, version 0.9.1-SNAPSHOT) providing the REST API for the Xtreme1 data labeling platform: dataset/data management, annotation persistence, ontology/class management, file upload to MinIO, model-run orchestration (image and point-cloud detection via external Python services), and dataset similarity jobs. The codebase follows an "optimized clean architecture" (documented in `README.md`): four layers under `src/main/java/ai/basic/x1/` — `adapter` (controllers, DTOs, ports/implementations), `usecase` (business logic), `entity` (business objects and enums), `util` (business-irrelevant tools). Only outer layers may depend on inner layers, with one documented pragmatic exception: the usecase layer directly calls DAOs in the adapter layer because MySQL/MyBatis is not intended to be replaced.

## Key Files
| File | Description |
|------|-------------|
| `pom.xml` | Maven build. Key deps: `spring-boot-starter-web`/`security`/`data-redis`/`actuator`, `mybatis-plus-boot-starter` 3.5.0, `mysql-connector-java`, `io.minio:minio` 8.3.7, `jjwt` 0.9.1, `hutool-all` 5.8.5, Lombok, Guava, `transmittable-thread-local` (TTL for async context propagation), `thumbnailator` + `webp-imageio` (image thumbnails), `okhttp` |
| `Dockerfile` | Multi-stage: `maven:3.8-openjdk-11` build → `openjdk:11-jre` runtime; installs the `xtreme1-sdk` Python package (used by `DataFormatUtil` via the `script_ctl` command) and downloads trial dataset zips; exposes 8080 |
| `README.md` | Architecture explanation, local dev setup (MySQL/Redis/MinIO via `docker compose up`, `application-local.yml` override), build/run commands, checkstyle/format setup |
| `src/main/java/ai/basic/x1/adapter/Application.java` | Spring Boot entrypoint; `scanBasePackages = "ai.basic.x1.adapter"` only, `@EnableScheduling`, excludes `UserDetailsServiceAutoConfiguration` |
| `src/main/resources/application.yml` | Default config for Docker Compose networking (hosts `mysql`, `redis`, `minio`); JWT secret/issuer/expiry, MyBatis-Plus logic-delete config (`isDeleted`), mapper locations, MinIO bucket, model-service URLs (`image-object-detection`, `pcd-tools`, `image-vect-visualization`), initial trial dataset definitions |
| `src/main/resources/mybatis/mapper/*.xml` | 24 MyBatis XML mappers (e.g. `DataInfoMapper.xml`, `DatasetMapper.xml`, `ModelDataResultMapper.xml`) for custom SQL beyond MyBatis-Plus defaults |
| `coding-standards/checkstyle.xml` | Checkstyle rules (with `checkstyle-import-control.xml`, suppressions, Apache header template) |
| `coding-standards/intellij-code-format.xml` | IDEA code style scheme; reformat/optimize-imports/rearrange on save is the documented convention |
| `src/test/java/ai/basic/x1/adapter/TestApplication.java` | The only test source file; there is effectively no automated test suite |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/main/java/ai/basic/x1/adapter/` | Adapter layer: REST controllers, security/config, DTOs, DAO/MinIO/RPC ports (see `src/main/java/ai/basic/x1/adapter/AGENTS.md`) |
| `src/main/java/ai/basic/x1/usecase/` | Usecase layer: business logic classes, one per domain module (see `src/main/java/ai/basic/x1/usecase/AGENTS.md`) |
| `src/main/java/ai/basic/x1/entity/` | Entity layer: `*BO` business objects and `enums/` (see `src/main/java/ai/basic/x1/entity/AGENTS.md`) |
| `src/main/java/ai/basic/x1/util/` | Business-irrelevant utilities: converters, paging, Redis lock (see `src/main/java/ai/basic/x1/util/AGENTS.md`) |
| `src/main/resources/` | `application.yml` + `mybatis/mapper/` XML files; SQL migrations live outside this module in `deploy/mysql/migration` |
| `coding-standards/` | Checkstyle and IntelliJ format configuration |

## For AI Agents
### Working In This Directory
- Build: `mvn package` (requires Java 11+, Maven 3.8+). Run locally: `java -Dspring.profiles.active=local -jar target/xtreme1-backend-0.9.1-SNAPSHOT.jar` after creating `src/main/resources/application-local.yml` pointing at localhost-mapped MySQL (8191), Redis (8192), MinIO (8193) from the repo-root `docker-compose.yml`.
- Respect layer direction: `entity` and `util` must not depend on `adapter` or `usecase`. `usecase` may call adapter DAOs (documented exception) but not controllers/DTOs. New outside dependencies used by usecases should be interfaces implemented in `adapter/port/`.
- Server listens on `0.0.0.0:8080`; actuator exposes `health,metrics,prometheus`.

### Testing Requirements
- No real test suite exists (`src/test` contains only `TestApplication.java`); `spring-boot-starter-test` and `mybatis-plus-boot-starter-test` are declared. Verify changes by building (`mvn package`) and running against the Docker Compose base services.
- Checkstyle (`coding-standards/checkstyle.xml`) is the style gate; README notes it is not yet CI-enforced.

### Common Patterns
- Request flow: Controller → `DefaultConverter.convert(DTO, BO)` → UseCase → DAO (MyBatis-Plus) → `DefaultConverter.convert(model/BO, DTO)` back out.
- Responses are wrapped in `ApiResult<T>` (code/message/data) via `CustomResponseWrapper`; errors funnel through `CustomExceptionHandler`.
- Logic delete is global (`isDeleted` field, configured in `application.yml`); audit fields auto-filled by `CustomerMetaObjectHandler`.

## Dependencies
### Internal
- Repo root `docker-compose.yml` for MySQL/Redis/MinIO; `deploy/mysql/migration` for schema; `deploy/nginx/conf.d/default.conf` for the reverse proxy that fronts this service.

### External
- Spring Boot 2.6.6 (web, security, data-redis, actuator), MyBatis-Plus 3.5.0, MySQL, MinIO SDK, JJWT, Hutool, Lombok, Guava, TTL, Thumbnailator/webp-imageio, OkHttp.
- Runtime container installs `xtreme1-sdk` (Python) providing `script_ctl` for COCO format conversion.
- External model services over HTTP: `image-object-detection`, `pcd-tools`, `image-vect-visualization` (URLs in `application.yml`).

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
