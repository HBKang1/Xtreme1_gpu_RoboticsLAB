<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# deploy

## Purpose
Container-deployment assets mounted into services defined in the root `docker-compose.yml`. It contains the MySQL bootstrap (server config override plus schema/seed SQL run by the MySQL 5.7 image's init mechanism) and the Nginx reverse-proxy config that exposes the whole platform on a single port (host `8190` → container `80`) and routes browser traffic to the frontend tools, the Spring Boot backend, and MinIO object storage.

## Key Files
| File | Description |
|------|-------------|
| `mysql/custom.cnf` | MySQL server override, mounted to `/etc/mysql/conf.d/custom.cnf`. Single setting: `max_allowed_packet=1073741824` (1 GB) to allow large annotation/result payloads. |
| `mysql/migration/V1__Create_tables.sql` | Full schema (580 lines, 25 `CREATE TABLE` statements with `DROP TABLE IF EXISTS` and `SET FOREIGN_KEY_CHECKS = 0`): `dataset`, `data`, `class`/`classification`, `ontology`, `data_annotation_object`/`_classification`/`_record`, `model`, `model_class`, `model_data_result`, `model_dataset_result`, `model_run_record`, `file`, `upload_record`, `export_record`, `user`, `user_token`, `dataset_similarity_job`/`_record`, etc. |
| `mysql/migration/V2__Init_data.sql` | Seed data (93 lines): model id 1 "Basic Lidar Object Detection11" pointing at `http://point-cloud-object-detection:5000/pointCloud/recognition`, model id 2 "COCO Object Detection" pointing at `http://image-object-detection:5000/image/recognition`, the 80 COCO classes as `model_class` rows, and the default `admin` user (bcrypt password hash). |
| `nginx/conf.d/default.conf` | Reverse-proxy config mounted to `/etc/nginx/conf.d/default.conf` in the `nginx:1.22` container. |
| `README.md` | Title-only placeholder ("# Xtreme1 Deploy"). |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `mysql/` | `custom.cnf` server override plus `migration/` SQL, both volume-mounted into the `mysql` service. |
| `mysql/migration/` | Mounted to `/docker-entrypoint-initdb.d` — executed by the official MySQL image entrypoint, in filename order, only on first initialization of the `mysql-data` volume. |
| `nginx/conf.d/` | Nginx server block consumed by the `nginx` service. |

## For AI Agents

### Working In This Directory
- **Nginx routing map** (`nginx/conf.d/default.conf`): `/` → `http://frontend:80/main/`; `/tool/image` → `frontend:80/image-tool/`; `/tool/pc` → `frontend:80/pc-tool/`; `/tool/text` → `frontend:80/text-tool/`; `/api/` → `http://backend:8080` with `rewrite ^/api/(.*) /$1 break` (the `/api` prefix is stripped before hitting Spring Boot); `/minio/` → `http://minio:9000` with the same prefix-strip rewrite plus HTTP/1.1, disabled chunked encoding, and `X-Real-IP`/`X-Forwarded-*` headers.
- Each frontend location sets `Cache-Control: no-store,no-cache` / `Pragma: no-cache` for the location root and any `.html`/`.json` URI, so SPA entry points are never cached while hashed assets are.
- `client_max_body_size 1048576m` and `proxy_buffering off` exist specifically for proxying large MinIO uploads (comment at `default.conf:5`).
- The config is bind-mounted (not baked into an image), so changes take effect with `docker compose restart nginx` (or `docker compose exec nginx nginx -s reload`) — no rebuild needed.
- **Adding a DB migration**: files use Flyway-style names (`V<N>__<Description>.sql`) but there is no Flyway in the backend (`backend/pom.xml` has no flyway dependency). The MySQL entrypoint runs `/docker-entrypoint-initdb.d` scripts **only when the `mysql-data` volume is empty**, in lexical filename order. A new `V3__*.sql` will not run on an existing installation; you must either apply it manually (`docker compose exec mysql mysql -u xtreme1 -p...`) or wipe the volume (`docker compose down -v`, destroying all data).
- Seed-data URLs in `V2__Init_data.sql` use compose service hostnames (`point-cloud-object-detection:5000`, `image-object-detection:5000`); these services only start under the `model` compose profile and require `runtime: nvidia` (`docker-compose.yml:116-137`). In this fork the point-cloud service runs a custom image `kanghanbin/my-custom-xtreme1:v5` with a CenterPoint checkpoint entrypoint.
- DB credentials referenced by the healthcheck and backend live in `docker-compose.yml:13-17` (`xtreme1`/`Rc4K3L6f`, root `ImOxO8Lz`).

### Testing Requirements
- After editing `default.conf`, validate syntax inside the container (`docker compose exec nginx nginx -t`) before reloading; check routes through host port 8190 (e.g. `curl http://localhost:8190/api/actuator/health` should reach the backend health endpoint that the compose healthcheck also uses).
- After SQL changes, verify a clean bootstrap: `docker compose down -v && docker compose up mysql`, then confirm via the compose healthcheck query (`SHOW DATABASES;` as the `xtreme1` user).

### Common Patterns
- Every table in `V1__Create_tables.sql` carries audit columns (`created_at`, `created_by`, `updated_at`, `updated_by`) and many use soft delete (`is_deleted` + `del_unique_key`), e.g. the `model` inserts in `V2__Init_data.sql`.
- Enum columns encode tool/dataset types directly in DDL (e.g. `class.tool_type` enum `POLYGON, BOUNDING_BOX, POLYLINE, KEY_POINT, SEGMENTATION, CUBOID`).
- Prefix-strip `rewrite ... break` + `proxy_pass` is the standard pattern for backend and MinIO routes; add new API-style routes the same way.

## Dependencies

### Internal
- `docker-compose.yml` (repo root) — mounts `deploy/nginx/conf.d/default.conf`, `deploy/mysql/custom.cnf`, and `deploy/mysql/migration/` into the `nginx` and `mysql` services; defines the service hostnames (`frontend`, `backend`, `minio`, model services) that both the nginx config and seed data depend on.
- `backend/` — schema must match the backend's MyBatis entities; backend health endpoint `/actuator/health` is the upstream behind `/api/`.
- `frontend/` — nginx assumes the frontend image serves `/main/`, `/image-tool/`, `/pc-tool/`, `/text-tool/` paths.

### External
- `nginx:1.22`, `mysql:5.7` Docker images (init-script behavior of the official MySQL entrypoint is load-bearing).
- `bitnamilegacy/minio` (object storage proxied at `/minio/`), `basicai/xtreme1-*` and `kanghanbin/my-custom-xtreme1:v5` model-service images whose URLs are seeded in `V2__Init_data.sql`.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
