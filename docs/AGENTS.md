<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# docs

## Purpose
Static documentation assets for the Xtreme1 project — almost entirely images. There is no prose documentation here beyond a title-only `README.md`; the actual written docs live in `backend/README.md` (developer setup, code style) which embeds images from this tree, and in the upstream project README. `docs/images/` holds product/marketing media (annotation demo GIFs, architecture diagrams, logos) and `docs/backend/images/` holds IntelliJ IDEA setup screenshots referenced by the backend developer guide. Note that this fork's root `README.md` is currently empty, so most assets under `docs/images/` are unreferenced within the repo and kept for upstream-README compatibility.

## Key Files
| File | Description |
|------|-------------|
| `README.md` | Placeholder containing only the heading "# Xtreme1 Docs". |
| `images/clean-architecture-opt.png` | Backend architecture diagram, embedded by `backend/README.md:14` ("Clean Architecture Optimized"). |
| `images/layer-architecture.png` | Layered-architecture diagram (companion to the clean-architecture image; not referenced by any markdown in this fork). |
| `images/3d_v2.gif`, `images/3d_ai.gif`, `images/3d-annotation.gif`, `images/3d annotation.gif`, `images/3d object tracking.gif`, `images/3d-track-model.gif`, `images/3d_gif.gif`, `images/3d_annotation2.png` | 3D/LiDAR annotation and tracking demo media (point-cloud tool). |
| `images/2d_v.gif`, `images/2d_gif.gif`, `images/2d-seg-model.gif`, `images/image segmentation.gif`, `images/image-bbox-model.gif`, `images/object detection.gif`, `images/image_ai.gif` | 2D image annotation, segmentation, and detection-model demo media. |
| `images/AI_Labelling.png`, `images/dv.png`, `images/0.7rlhf.webp` | Feature illustrations (AI-assisted labeling, data visualization, v0.7 RLHF feature). |
| `images/LFAI_DATA_horizontal-color.png` | LF AI & Data Foundation logo (Xtreme1 is an LF AI & Data project). |
| `backend/images/idea-run-local.png` | Screenshot embedded at `backend/README.md:92` — running the backend locally from IntelliJ IDEA. |
| `backend/images/idea-save-actions.png` | Screenshot at `backend/README.md:114` — IDEA "Actions on Save" auto-format setup. |
| `backend/images/idea-checkstyle-configure.png` | Screenshot at `backend/README.md:120` — configuring the Checkstyle-IDEA plugin with `backend/coding-standards/checkstyle.xml`. |
| `backend/images/idea-checkstyle-run.png` | Screenshot at `backend/README.md:124` — running Checkstyle in IDEA. |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `images/` | Product demo GIFs, architecture diagrams, and logos (24 files); only `clean-architecture-opt.png` is referenced by markdown inside this fork. |
| `backend/` | Contains only `images/` — no backend markdown lives here. |
| `backend/images/` | Four IntelliJ IDEA setup screenshots consumed by `backend/README.md`. |

## For AI Agents

### Working In This Directory
- Treat this as an asset store, not a docs source: to change developer documentation, edit `backend/README.md` (which references these images via root-relative paths like `/docs/backend/images/idea-run-local.png`), not files here.
- Several filenames contain spaces (`3d annotation.gif`, `object detection.gif`, `image segmentation.gif`); quote paths in shell commands.
- Before deleting an "unused" image, remember this is a fork whose root `README.md` was emptied — upstream README markdown referenced these assets, so removals will create broken links if upstream README content is ever restored.
- Image paths in `backend/README.md` use leading-slash repo-root paths (e.g. `/docs/images/clean-architecture-opt.png?raw=true`), which render on GitHub but not in all local markdown viewers; keep new references consistent with that convention.

### Testing Requirements
- No build or tests apply. Verification is link-checking: after moving/renaming an asset, grep markdown for the filename (`grep -rn "<name>" --include="*.md"`) and confirm `backend/README.md` references still resolve.

### Common Patterns
- One subdirectory of images per documented component (`docs/backend/images/` for the backend guide); follow this if adding docs for other components.
- Demo media are GIFs named by tool/feature (`3d-*`, `2d-*`, `image-*`); diagrams and logos are PNG/WebP.

## Dependencies

### Internal
- `backend/README.md` — the only markdown in this fork that embeds these assets (lines 14, 92, 114, 120, 124); it also pairs the checkstyle screenshots with `backend/coding-standards/checkstyle.xml` and `intellij-code-format.xml`.
- Root `README.md` — currently empty in this fork; historically the consumer of the `docs/images/` demo GIFs and logos.

### External
- GitHub markdown rendering (root-relative image paths with `?raw=true` are GitHub-specific).

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
