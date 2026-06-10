<!-- Parent: ../../../../../../../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# util

## Purpose
Business-irrelevant utility layer used by all other layers. Hosts the project's two most load-bearing helpers — `DefaultConverter` (the bean/page converter that powers every DTO↔BO↔model translation) and `Page<T>` (the API pagination envelope) — plus a Redis-based distributed lock, shared constants, archive decompression, natural sorting, JSR-380 programmatic validation, and a shell-out wrapper around the `script_ctl` tool from the xtreme1 Python SDK for COCO format conversion.

## Key Files
| File | Description |
|------|-------------|
| `DefaultConverter.java` | Static conversion utilities built on Hutool `BeanUtil`: object→object by class, list conversion, MyBatis-Plus `Page<S>` → `util.Page<D>` by bean copy or custom mapper `Function` |
| `Page.java` | Serializable pagination wrapper (`pageSize` default 10, `pageNo`, `total`, `list`) with a `convert(Function)` mapper; returned by usecases and controllers instead of MyBatis-Plus pages |
| `Constants.java` | Interface of shared constants: header names (`X-Real-Ip`, `X-Forwarded-For`, ...), file/directory markers, archive suffixes, MinIO path pieces, `PAGE_SIZE_100`, etc. |
| `lock/IDistributedLock.java` | Lock interface (`tryLock(key)`, `tryLock(key, waitTime)`, unlock) |
| `lock/DistributedLock.java` | Redis reentrant lock over `StringRedisTemplate` + Lua `RedisScript`, with per-instance UUID owner id and millisecond timeout; polling `tryLock` with 100ms sleep; instantiated as a bean in `adapter/api/config/CommonConfig` |
| `DecompressionFileUtils.java` | Decompresses uploaded dataset archives (zip/tar variants per `Constants` suffixes) |
| `DataFormatUtil.java` | Runs `script_ctl --mode ... --fmt=coco` via `ProcessBuilder` (`sh -c`) to convert annotation results to/from COCO; logs stderr, deletes source on success — requires the xtreme1-sdk Python package installed in the runtime image |
| `ClassificationUtils.java` | Parses `DataAnnotationClassificationBO` answers into flat `DataClassificationOption` rows |
| `ModelParamUtils.java` | Validates model-run filter params (`PreModelParamDTO`) per `ModelCodeEnum` |
| `NaturalSortUtil.java` | Builds zero-padded sort keys so numeric file names sort naturally (used for `orderName` fields) |
| `ValidateUtil.java` | Programmatic JSR-380 validation via a static `Validator`; throws on constraint violations |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `lock/` | Redis distributed lock (`IDistributedLock`, `DistributedLock`) |

## For AI Agents
### Working In This Directory
- This layer must stay business-agnostic in spirit, but note it is not perfectly pure: `ClassificationUtils` and `ModelParamUtils` import `entity` BOs and adapter DTOs/models. Do not add dependencies on `usecase` or controllers.
- Prefer `DefaultConverter.convert(source, Target.class)` for straightforward field-name-aligned copies; use the `Function`-based overloads when custom mapping logic is needed.
- `DataFormatUtil.convert` swallows exceptions (logs and returns) and asserts on exit code — callers cannot rely on it throwing; check output files exist if correctness matters.

### Testing Requirements
- No unit tests exist for utilities. `DistributedLock` and `DataFormatUtil` behavior can only be verified against running Redis / the installed `script_ctl` binary respectively.

### Common Patterns
- Static utility classes (no instantiation); `Constants` as a constants-only interface.
- Conversion-by-name convention: utilities assume identical property names across DTO/BO/model triples.

## Dependencies
### Internal
- `ai.basic.x1.entity` (BOs/enums) and, in `ClassificationUtils`/`ModelParamUtils`, some `ai.basic.x1.adapter` DTO/model types. `lock/` is consumed by usecases via the `IDistributedLock` bean.

### External
- Hutool (`BeanUtil`, `FileUtil`, `StrUtil`, `JSONUtil`), Spring Data Redis (`StringRedisTemplate`, `RedisScript`) in `lock/`, MyBatis-Plus pagination types in `DefaultConverter`, javax.validation, Lombok.
- The `script_ctl` CLI from the xtreme1-sdk Python package (installed in `backend/Dockerfile`).

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
