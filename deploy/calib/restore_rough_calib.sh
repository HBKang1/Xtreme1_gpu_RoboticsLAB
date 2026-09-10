#!/usr/bin/env bash
# rough_152141/152745/154627 (dataset_id=111,112,113) 의 camera_config 를
# 교체 전 원본으로 되돌린다.
#
#   bash deploy/calib/restore_rough_calib.sh
#
# 원본은 교체 직전에 같은 버킷의 _calib_backup/20260820_rough_original/ 아래로
# 복사해 두었다. 대표 원본 1개는 deploy/calib/rough_original_camera_config.json
# 에도 있다(1,182개 파일이 전부 바이트 동일이라 하나로 복원 가능).
#
# 복원 후에는 file.size 를 722 로 되돌려야 한다:
#   sed 's/SET @newsize = 711;/SET @newsize = 722;/' \
#     deploy/mysql/sync_calib_file_size_ds111_113.sql \
#   | docker exec -i xtreme1_gpu_roboticslab-mysql-1 mysql -uroot -pImOxO8Lz xtreme1
set -euo pipefail

MINIO=xtreme1_gpu_roboticslab-minio-1
BK=loc/xtreme1/_calib_backup/20260820_rough_original

docker exec "$MINIO" sh -c "
set -e
mc alias set loc http://localhost:9000 admin 1tQB970y >/dev/null 2>&1
for spec in '111:4/111/7002216a77b14d5a938df4ada5b3310c' \
            '112:4/112/862dae1b17d5427b923bfa1ea01417ea' \
            '113:4/113/fdbdc2ccb16d43f087e1b08b367b9d3a'; do
  ds=\"\${spec%%:*}\"; p=\"\${spec##*:}\"
  mc cp --recursive '$BK'/ds\$ds/ \"loc/xtreme1/\$p/camera_config/\" >/dev/null
  echo \"ds\$ds restored: \$(mc ls \"loc/xtreme1/\$p/camera_config/\" | wc -l) objects\"
done"
