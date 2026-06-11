# Zenix GT 파인튜닝 파이프라인 (Xtreme1 → OpenPCDet CenterPoint)

연구실 zenix 데이터(16빔, 설상, intensity 없음)에서 nuScenes 사전학습 모델 성능이 낮은
도메인 갭 문제를, Xtreme1에서 작업한 GT로 CenterPoint를 파인튜닝해 해결하는 파이프라인.

```
[이 PC]  Xtreme1 UI Export ──▶ convert_xtreme1_to_openpcdet.py ──▶ data/zenix/
                                                                      │ (복사)
[학습 서버]  OpenPCDet + cfgs/ ──▶ create_custom_infos ──▶ train.py ──▶ ckpt
                                                                      │ (복사)
[이 PC]  docker-compose 마운트 교체 (TransFusion 때와 동일) ──▶ 서빙
```

## 0. 사전 준비 (이 PC)

사전학습 체크포인트를 이미지에서 추출 (파인튜닝 초기 가중치):
```bash
docker run --rm --entrypoint cat kanghanbin/my-custom-xtreme1:v5 \
  /app/cbgs_voxel0075_centerpoint_nds_6648.pth > centerpoint_nuscenes_pretrained.pth
```

## 1. GT 내보내기 (Xtreme1 UI)

데이터셋 → Export → **Xtreme1 JSON** (결과 포함). zip 안에 프레임별
`data/<이름>.json`(원본 pcd 파일명)과 `result/<이름>.json`(GROUND_TRUTH 박스)이 생성됨.

## 2. 변환 (이 PC)

```bash
python3 training/convert_xtreme1_to_openpcdet.py \
  --export ~/Downloads/<export>.zip \
  --pcd-root /home/a/dataset_custom/zenix_dataset/dataset_0124 \
  --output ./data/zenix
```

출력: `points/*.npy`(float32 Nx4, intensity=0 패딩), `labels/*.txt`
(`x y z dx dy dz heading class`), `ImageSets/{train,val}.txt` (기본 9:1 분할).

마지막에 출력되는 **CLASS_NAMES 목록과 클래스 히스토그램을 반드시 확인**할 것.
클래스명이 지저분하면(`--class-map mapping.json`)으로 통합:
`{"승용차": "Car", "SUV": "Car", ...}`

## 3. 학습 서버 환경 구축

```bash
git clone https://github.com/open-mmlab/OpenPCDet.git && cd OpenPCDet
# (선택) 서빙 이미지와 동일 코드 기준: git checkout 233f849
pip install -r requirements.txt
pip install spconv-cu1xx   # 서버 CUDA 버전에 맞게 (예: spconv-cu118)
python setup.py develop
```

파일 배치:
```
OpenPCDet/
├── data/zenix/                 ← 2단계 출력 통째로 복사
├── tools/cfgs/dataset_configs/zenix_dataset.yaml   ← training/cfgs/에서 복사
└── tools/cfgs/zenix_models/centerpoint_zenix.yaml  ← training/cfgs/에서 복사
```

**두 yaml 모두 클래스 목록을 2단계 출력으로 교체**:
- `centerpoint_zenix.yaml`: `CLASS_NAMES`, `CLASS_NAMES_EACH_HEAD`
- `zenix_dataset.yaml`: `MAP_CLASS_TO_KITTI`, `filter_by_min_points`, `SAMPLE_GROUPS`

## 4. 인포 생성 + 학습

```bash
# custom_dataset.py 말미의 하드코딩된 class_names를 본인 클래스로 수정한 뒤:
#   pcdet/datasets/custom/custom_dataset.py → create_custom_infos 블록
python -m pcdet.datasets.custom.custom_dataset create_custom_infos \
  tools/cfgs/dataset_configs/zenix_dataset.yaml

cd tools
python train.py --cfg_file cfgs/zenix_models/centerpoint_zenix.yaml \
  --batch_size 8 \
  --pretrained_model /path/to/centerpoint_nuscenes_pretrained.pth
# 멀티 GPU: bash scripts/dist_train.sh <NGPU> --cfg_file ... --pretrained_model ...
```

참고:
- `--pretrained_model`은 shape이 일치하는 가중치만 로드함. 입력 채널(4 vs 5 feature)이
  다른 첫 레이어와 클래스 수가 다른 헤드는 자동으로 새로 초기화됨 — 정상 동작.
- 평가: `python test.py --cfg_file cfgs/zenix_models/centerpoint_zenix.yaml --ckpt <ckpt>`
- val mAP이 수렴하면 중단. 체크포인트는 `output/zenix_models/centerpoint_zenix/.../ckpt/`

## 5. 서빙 배포 (이 PC)

TransFusion 전환 때와 동일한 마운트 방식:

1. 학습된 ckpt와 `centerpoint_zenix.yaml`(+ `zenix_dataset.yaml`)을 이 PC로 복사
2. `deploy/point-cloud-detection/app.py`:
   - `cfg_file` → 마운트한 `centerpoint_zenix.yaml` 경로
   - `full_nms=False` → **`True`로 복원** (CenterPoint는 NMS_CONFIG 있음)
3. `docker-compose.yml` volumes에 ckpt/yaml 마운트 추가, entrypoint 인자를 새 ckpt로
4. **DB 클래스 갱신** — 서빙 라벨은 `CLASS_NAMES`의 대문자(`CAR`, `PEDESTRIAN`...)로
   나가므로 `model_class.code`와 일치해야 UI에 클래스가 매핑됨:
   ```sql
   DELETE FROM model_class WHERE model_id = 1;
   INSERT INTO model_class (model_id, name, code, created_at, created_by)
   VALUES (1,'Car','CAR',now(),1), (1,'Pedestrian','PEDESTRIAN',now(),1), ...;
   ```
5. `docker compose --profile model up -d point-cloud-object-detection` 후
   curl 스모크 테스트 (TransFusion 검증 때와 동일한 방법)

## 주의사항

- 학습 중 이 PC에서 돌릴 경우(비권장, 8GB): 서빙 컨테이너를 먼저 내려 VRAM 확보,
  `--batch_size 1~2`.
- zenix pcd에는 intensity가 없어 0으로 학습/서빙 모두 통일됨. 향후 intensity가 있는
  센서로 바꾸면 cfg의 `used_feature_list`와 재학습 필요.
- 16빔 sparsity 때문에 `filter_by_min_points` 기준(5포인트)에 걸려 멀리 있는 GT가
  학습에서 제외될 수 있음 — 히스토그램 대비 dbinfos 개수가 너무 줄면 3으로 낮출 것.
