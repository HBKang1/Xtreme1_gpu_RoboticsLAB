-- rough_152141/152745/154627 (dataset_id=111,112,113) 의 camera_config json 을
-- testbed_st 캘리브레이션으로 교체한 뒤, file.size 를 실제 오브젝트 크기에 맞춘다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/sync_calib_file_size_ds111_113.sql
--
-- 교체 자체는 MinIO 오브젝트를 덮어쓰는 작업이라 SQL 로 하지 않는다. 이 스크립트는
-- DB 메타데이터만 맞춘다. rough 원본 722 bytes -> testbed 원본 711 bytes.
--
-- file.size 는 서빙에 쓰이지 않고(Content-Length 는 MinIO 가 준다) 목록/통계용이지만,
-- 실제 오브젝트와 어긋난 채로 두면 나중에 무결성 확인이 어려워진다.
--
-- 되돌리려면 restore_rough_calib.sh 로 오브젝트를 복원한 뒤 @newsize 를 722 로 바꿔
-- 다시 실행한다.

SET @newsize = 711;

START TRANSACTION;

DROP TABLE IF EXISTS `bak_calib_file_size_ds111_113`;
CREATE TABLE `bak_calib_file_size_ds111_113` AS
SELECT f.`id`, f.`size`
  FROM `data` d
  JOIN `file` f ON f.`id` = JSON_UNQUOTE(JSON_EXTRACT(d.`content`, '$[0].files[0].fileId'))
 WHERE d.`dataset_id` IN (111, 112, 113)
   AND d.`type` = 'SINGLE_DATA'
   AND JSON_UNQUOTE(JSON_EXTRACT(d.`content`, '$[0].name')) = 'camera_config';

SELECT COUNT(*) AS will_update FROM `bak_calib_file_size_ds111_113`;

UPDATE `file` f
  JOIN `bak_calib_file_size_ds111_113` b ON b.`id` = f.`id`
   SET f.`size` = @newsize;

COMMIT;

-- ── 결과 확인 ──
SELECT d.`dataset_id`, COUNT(*) AS files, MIN(f.`size`) AS min_size, MAX(f.`size`) AS max_size
  FROM `data` d
  JOIN `file` f ON f.`id` = JSON_UNQUOTE(JSON_EXTRACT(d.`content`, '$[0].files[0].fileId'))
 WHERE d.`dataset_id` IN (111, 112, 113) AND d.`type` = 'SINGLE_DATA'
 GROUP BY d.`dataset_id`;
