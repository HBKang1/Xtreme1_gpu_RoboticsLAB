# Zenix GT 파인튜닝 파이프라인 (Xtreme1 → OpenPCDet)

연구실 zenix 데이터(16빔/64ch 듀얼 LiDAR, 설상·야간, 한국)의 도메인 갭을, Xtreme1 GT로
검출기를 파인튜닝해 줄이는 파이프라인. **목적은 일반화가 아니라 기존 zenix 녹화 오토라벨링**.
**GT는 전방 카메라 FOV 영역에만 작업됨** → 학습 입력을 그 섹터(±50°)로 크롭한다.

> **2026-06-15 실행 결과·결정 전문**: `.omc/wiki/zenix-finetune-run-2026-06-15.md`
> 채택: **VoxelNeXt** 파인튜닝(CenterPoint보다 우수), 단일 카메라 FOV(±50°), intensity raw/255,
> 오토라벨링이라 전량/랜덤 분할. FOV 안 recall 99% / precision 99.7%(conf0.5).

```
[이 PC]  export_gt.py ─▶ analyze_fov.py ─▶ convert(+FOV크롭) ─▶ split_sequences.py ─▶ data/zenix/
                                                                                        │ (rsync)
[학습서버 gh@192.168.0.145]  OpenPCDet + cfgs/ ─▶ create_custom_infos ─▶ train.py ─▶ ckpt
                                                                                        │ (rsync back)
[이 PC]  docker-compose 마운트 ─▶ 서빙 ─▶ eval_recall_ab.py(recall/precision A/B)
```

---

## 핵심 결정 (요약)

- **단일 카메라 FOV(±50°), 기하 유지**: cfg range/voxel은 사전학습과 동일(가중치 이전 보존),
  데이터 단계에서 FOV 밖 포인트만 제거. 섹터는 **Zenix_Night_15 전방 카메라 캘리브**에서 도출
  (DS마다 GT FOV가 달라 GT분포 기반 통합 섹터는 폐기). → `fov_sector_camera.json`.
- **intensity = raw/255 고정 스케일 + raw>2 필터**: per-frame min-max는 프레임마다 스케일이
  출렁여 train/serve 불일치 → 고정 스케일 통일. 눈 노이즈(raw≤2)는 변환·서빙 양측 제거.
  서빙은 `INTENSITY_NORM=fixed255`(미설정 시 기존 min-max — 롤백 안전).
- **오토라벨링 → 전량/랜덤 분할**(`split_sequences.py --random`). 씬분할은 일반화 측정용이라
  일부 녹화를 학습에서 빼버려 정작 라벨할 데이터를 모델이 못 봄.
- **아키텍처 = VoxelNeXt**: 같은 zenix val에서 zero-shot 86.7% > FT CenterPoint 82.6%라
  더 강한 베이스를 파인튜닝. cfg `voxelnext_zenix.yaml`.

## 하드 게이트
1. **3자 일치**(export): DS별 `DB ANNOTATED = export totalNum = 변환 프레임`. export_gt 경고 + convert `--expected-frames`.
2. **pcd not found / fetch error = 0**(convert): 1개라도 있으면 비정상 종료(조용한 손실 차단). 허용 시 `--allow-missing-pcd`.
3. **GPU 전제**(학습): 학습 서버 `nvidia-smi` 정상 + `torch.cuda.is_available()` True.

---

## 0. 사전 준비 (이 PC)
사전학습 ckpt 추출 (파인튜닝 초기 가중치):
```bash
# CenterPoint (이미지 내장)
docker run --rm --entrypoint cat kanghanbin/my-custom-xtreme1:v5 \
  /app/cbgs_voxel0075_centerpoint_nds_6648.pth > centerpoint_nuscenes_pretrained.pth
# VoxelNeXt (저장소 루트, OpenPCDet README Google Drive에서 받은 것 — 채택 모델)
#   cbgs_voxel0075_voxelnext.pth (이미 보유, 서빙에도 마운트됨)
```

## 1. GT 내보내기 — export_gt.py
**게이트웨이(:8190/api) 경유 필수** — 백엔드가 presigned URL을 요청 host로 만들어 :8290 직결은
`/minio/` 라우트 없어 404. 내부적으로 `selectModelRunIds=-1`(GROUND_TRUTH)로 result/*.json 포함.
```bash
XTREME1_USER=robotics@gmail.com XTREME1_PASS=*** python3 training/export_gt.py --list   # 대상 확인
XTREME1_USER=... XTREME1_PASS=... python3 training/export_gt.py                          # 전량 → training/exports/<DS>.zip
XTREME1_USER=... XTREME1_PASS=... python3 training/export_gt.py --dataset Zenix_Night_6  # 특정 DS
```
- 선별: **이름이 `Zenix_`로 시작**하고 `annotatedCount>0` (Caterpie/N14/한글명/seq/test 제외). 상수 `REQUIRED_PREFIX`.
- **씬 데이터셋 대응**: annotationStatus 필터는 top-level(씬)에만 걸림 → 씬이 NOT_ANNOTATED면 0개.
  스크립트가 자동으로 `parentId=<sceneId>`를 붙여 자식 ANNOTATED 프레임만 export. (flat DS는 그대로)
- sourceName 실제값 `"Ground Truth"`(공백). 토큰/비밀번호는 env로만.

## 2. FOV 섹터 — analyze_fov.py
**채택: 카메라 캘리브 기반 단일 섹터** (Night_15 `camera_image_0` intrinsics+extrinsics → LiDAR 방위각).
산출값 `fov_sector_camera.json`(azimuth [-49.46, 50.23], 점유율 27.7%)을 전 DS에 동일 적용.
```bash
# (참고) GT 분포 기반 섹터도 지원하나 DS간 불일치로 폐기:
python3 training/analyze_fov.py --export-dir training/exports --output training/fov_sector.json
```
> 카메라 섹터는 캘리브에서 직접 계산(스크립트 `fov_sector_camera.json` 생성 코드 참조). DS마다
> GT FOV가 달라(Night_14는 -150°까지) GT분포 통합 섹터는 238°로 무의미해짐.

## 3. 변환 + FOV 크롭 + 분할 — convert / split_sequences
```bash
# Night(이름 일치): 디스크 pcd 사용
python3 training/convert_xtreme1_to_openpcdet.py --export training/exports/Zenix_Night_14.zip \
  --pcd-root /home/a/dataset_custom/zenix_dataset/dataset_0124/14_2026-01-24-01-57-13 \
  --fov-sector training/fov_sector_camera.json --frame-prefix "Zenix_Night_14__" --output ./data/zenix
# Day(a2z 리네임으로 디스크 이름 불일치): MinIO url에서 직접 fetch
python3 training/convert_xtreme1_to_openpcdet.py --export training/exports/Zenix_Day_2.zip \
  --from-url --fov-sector training/fov_sector_camera.json --frame-prefix "Zenix_Day_2__" --output ./data/zenix
```
- `--from-url`: export data json의 url(MinIO pcd = 실제 어노테이션된 pcd)을 직접 받음 → 디스크 이름
  매핑 불필요 + GT 정합 보장. (Day는 디스크가 `lidar_point_cloud_64/z..._64_NNN.pcd`, export는 `000000.pcd`)
- `--pcd-root` 다중(0124/0224), `--pcd-include-dir`(기본 `lidar_point_cloud_0`)로 point_cloud_16/_old 충돌 회피.
- `--fov-sector`: 포인트 섹터 크롭(npy 저장 직전). 섹터 밖 GT 박스는 드롭(카운트) — 포인트가 잘렸으므로.
- intensity: raw>2 필터 → raw/255 (서빙과 동일). `--source` 기본 `"Ground Truth"`.
- 출력: `points/*.npy`(Nx4 x,y,z,intensity∈[0,1]), `labels/*.txt`, `ImageSets/`. 마지막 CLASS_NAMES·히스토그램 확인.

**분할(오토라벨링 = 전량/랜덤)**:
```bash
python3 training/split_sequences.py --data-dir ./data/zenix --random --val-ratio 0.05
# (일반화 측정용이면 --random 빼고 시퀀스 단위 holdout)
```
> NAS는 CIFS — 대량 IO 워커 4 이하. 전체 dataset rglob는 느리니 DS별 레코딩 디렉토리를 `--pcd-root`로 지정 권장.

## 4. 학습 서버 환경 + 학습 (gh@192.168.0.145)
**환경(서빙 이미지와 동일 = ckpt 라운드트립 호환)**: conda env, **torch 1.10.1+cu113, spconv-cu113 2.1.25,
OpenPCDet @ commit 233f849**, `CUDA_HOME=/usr/local/cuda-11.7`.
```bash
conda create -n pcdet python=3.8 -y && conda activate pcdet
pip install torch==1.10.1+cu113 torchvision==0.11.2+cu113 --extra-index-url https://download.pytorch.org/whl/cu113
pip install spconv-cu113==2.1.25 numpy==1.23.5 numba==0.56.4 llvmlite==0.39.1 tensorboardX easydict pyyaml scikit-image tqdm SharedArray pyquaternion opencv-python-headless
git clone https://github.com/open-mmlab/OpenPCDet && cd OpenPCDet && git checkout 233f849
export CUDA_HOME=/usr/local/cuda-11.7 && python setup.py develop
```
필수 패치 2개:
- `pcdet/datasets/__init__.py`: argo2 import를 try/except로 가드 (av2 미설치).
- `pcdet/models/detectors/detector3d_template.py` `_load_state_dict`: spconv 키 보정 `assert val.shape.__len__()==5`를
  `elif`로 바꿔 **보정 불가 키 스킵**(VoxelNeXt 파인튜닝 시 클래스 다른 희소 헤드 로드 크래시 회피).
  상세: `training/voxelnext-spconv-fix.html`.

배치 + create_custom_infos + 학습:
```bash
# data/zenix → OpenPCDet/data/zenix (심볼릭링크 가능), cfgs → tools/cfgs/{dataset_configs,zenix_models}
# custom_dataset.py __main__의 class_names 하드코딩을 실제 6클래스로, data/save_path를 zenix로 수정
python -m pcdet.datasets.custom.custom_dataset create_custom_infos tools/cfgs/dataset_configs/zenix_dataset.yaml
cd tools
# 채택: VoxelNeXt
CUDA_VISIBLE_DEVICES=0 python train.py --cfg_file cfgs/zenix_models/voxelnext_zenix.yaml \
  --batch_size 8 --epochs 50 --num_epochs_to_eval 0 \
  --pretrained_model ~/finetune/cbgs_voxel0075_voxelnext.pth --extra_tag voxelnext_ft --fix_random_seed
```
- `--pretrained_model`은 shape 일치 가중치만 로드. 입력채널(4≠5) 첫 레이어·클래스 헤드 재초기화 = **정상**.
- dbinfos는 FOV 크롭된 npy에서 생성 → 경계 객체 절단. `filter_by_min_points`는 3 사용(16빔+크롭 대응).
- `--num_epochs_to_eval 0`: 학습중 KITTI AP eval은 hang/segfault라 끔. 평가는 6단계 서빙 기반으로.

## 5. 배포 (이 PC)
best ckpt + `voxelnext_zenix.yaml` + base `zenix_dataset.yaml`를 회수 후 `docker-compose.yml`:
```yaml
volumes:
  - ./voxelnext_zenix_ft.pth:/app/voxelnext_zenix_ft.pth:ro
  - ./training/cfgs/voxelnext_zenix.yaml:/app/pcdet_open/cfgs/zenix_models/voxelnext_zenix.yaml:ro
  - ./training/cfgs/zenix_dataset.yaml:/app/pcdet_open/cfgs/dataset_configs/zenix_dataset.yaml:ro
environment:
  - INTENSITY_NORM=fixed255
entrypoint: ["python","app.py","--cfg","cfgs/zenix_models/voxelnext_zenix.yaml","--ckpt","/app/voxelnext_zenix_ft.pth"]
```
- `_BASE_CONFIG_`는 working_dir(`/app/pcdet_open`) 기준 → base yaml이 그 상대경로에 마운트돼야 함.
- `full_nms`는 cfg `NMS_CONFIG` 유무로 자동 감지 — app.py 수정 불필요.
- 단일 파일 bind-mount inode 함정 → `docker compose --profile model up -d --force-recreate point-cloud-object-detection`.
- **DB model_class 갱신 불필요**: 라이다 모델(id=1)은 원래 model_class 없음(COCO id=2만). 검출 라벨은
  서빙 출력값을 그대로 사용. (시드 `deploy/mysql/migration/V2__Init_data.sql` 확인)
- 롤백: entrypoint `--model voxelnext`, environment 제거.

## 6. 평가 — eval_recall_ab.py (서빙 기반)
```bash
# 1) val 프레임의 pcd url + FOV GT 추출 → training/val_eval_ab.json (스크립트 상단 참고)
# 2) 서빙에 돌려 recall/precision/F1 (--pred-fov로 FOV 밖 예측 제외)
python3 training/eval_recall_ab.py --label ft_voxelnext --conf 0.5 --pred-fov training/fov_sector_camera.json
```
- 클래스무관, 중심거리 2m, 1:1 그리디 매칭. recall=잡은 GT, precision=맞은 예측/전체 예측.
- 결과(2026-06-15): VoxelNeXt FT, ±50° FOV필터 conf0.5 → **recall 99.4% / precision 99.7% / F1 0.996**.
- ⚠️ 360° 입력 그대로면 precision 42.8%(FOV 밖 예측이 FP) — **서빙 FOV 입력 크롭은 미적용/보류**
  (오토라벨링용으로 적용 후보). 결정 상세: `.omc/wiki/zenix-finetune-run-2026-06-15.md`.
- 지표 한계: 박스 IoU 정밀도·클래스 정확도는 미반영 → Xtreme1 UI 모델런 **육안 확인** 필수.

## 주의사항
- 학습은 별도 GPU 서버(3090). 이 PC(RTX 2080 8GB)는 비권장 + 동시 2모델 구동 OOM 위험.
- in-distribution 평가(랜덤분할)라 기존 녹화 오토라벨링엔 위 수치, 완전 새 환경은 더 낮을 수 있음.
- 16빔 sparsity + FOV 경계 절단으로 dbinfos 급감 가능 → `filter_by_min_points` 완화.
