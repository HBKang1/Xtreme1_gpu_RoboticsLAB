-- Zenix_Snow_Day_* 데이터셋의 이미지 모델 예측 결과를 전부 지운다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/purge_snow_day_model_results.sql
--
-- 대상: 이름에 zenix_snow_day 가 들어간 IMAGE 데이터셋 (69/71/72/73/74/75).
--       2D_Zenix_Day_05(70), Image Trial(2/59), LIDAR 데이터셋은 건드리지 않는다.
--
-- 지우는 것
--   data_annotation_object  source_type='MODEL' 인 것만 (사람이 만든 GT 는 보존)
--   model_dataset_result    이미지별 원본 추론 결과
--   model_data_result       단건 실행 결과
--   model_run_record        실행 이력 (Results 드롭다운에서 사라짐)
--
-- 되돌리려면 restore_snow_day_model_results.sql 실행.

SET @dsids = '69,71,72,73,74,75';

START TRANSACTION;

-- ── 백업 (되돌릴 수 있도록 지우기 전 통째로 복사) ──
DROP TABLE IF EXISTS `bak_snow_annotation_object`;
CREATE TABLE `bak_snow_annotation_object` AS
SELECT * FROM `data_annotation_object`
 WHERE `dataset_id` IN (69,71,72,73,74,75) AND `source_type` = 'MODEL';

DROP TABLE IF EXISTS `bak_snow_dataset_result`;
CREATE TABLE `bak_snow_dataset_result` AS
SELECT * FROM `model_dataset_result` WHERE `dataset_id` IN (69,71,72,73,74,75);

DROP TABLE IF EXISTS `bak_snow_data_result`;
CREATE TABLE `bak_snow_data_result` AS
SELECT * FROM `model_data_result` WHERE `dataset_id` IN (69,71,72,73,74,75);

DROP TABLE IF EXISTS `bak_snow_run_record`;
CREATE TABLE `bak_snow_run_record` AS
SELECT * FROM `model_run_record` WHERE `dataset_id` IN (69,71,72,73,74,75);

SELECT 'backup' AS phase,
       (SELECT COUNT(*) FROM `bak_snow_annotation_object`) AS annotation_object,
       (SELECT COUNT(*) FROM `bak_snow_dataset_result`)    AS dataset_result,
       (SELECT COUNT(*) FROM `bak_snow_data_result`)       AS data_result,
       (SELECT COUNT(*) FROM `bak_snow_run_record`)        AS run_record;

-- ── 삭제 ──
DELETE FROM `data_annotation_object`
 WHERE `dataset_id` IN (69,71,72,73,74,75) AND `source_type` = 'MODEL';

DELETE FROM `model_dataset_result` WHERE `dataset_id` IN (69,71,72,73,74,75);
DELETE FROM `model_data_result`    WHERE `dataset_id` IN (69,71,72,73,74,75);
DELETE FROM `model_run_record`     WHERE `dataset_id` IN (69,71,72,73,74,75);

COMMIT;

-- ── 결과 확인: 아래 네 값이 모두 0 이어야 한다 ──
SELECT 'after' AS phase,
       (SELECT COUNT(*) FROM `data_annotation_object`
         WHERE `dataset_id` IN (69,71,72,73,74,75) AND `source_type`='MODEL') AS annotation_object,
       (SELECT COUNT(*) FROM `model_dataset_result` WHERE `dataset_id` IN (69,71,72,73,74,75)) AS dataset_result,
       (SELECT COUNT(*) FROM `model_data_result`    WHERE `dataset_id` IN (69,71,72,73,74,75)) AS data_result,
       (SELECT COUNT(*) FROM `model_run_record`     WHERE `dataset_id` IN (69,71,72,73,74,75)) AS run_record;

-- ── 다른 데이터셋이 영향받지 않았는지 ──
SELECT d.`name`, o.`source_type`, COUNT(*) AS objects
  FROM `data_annotation_object` o JOIN `dataset` d ON d.`id` = o.`dataset_id`
 GROUP BY d.`name`, o.`source_type` ORDER BY d.`name`;
