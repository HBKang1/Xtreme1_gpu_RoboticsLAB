-- promote_model_results_to_gt_ds74.sql 되돌리기.
-- 승격했던 행을 원래 모델 결과(MODEL / source_id 26, RECTANGLE 2점)로 복원한다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/demote_gt_to_model_results_ds74.sql
--
-- 주의: 복원 후, 승격된 뒤에 툴에서 그 박스들을 편집했다면 그 편집 내용은 사라진다.

START TRANSACTION;

UPDATE `data_annotation_object` o
  JOIN `bak_ds74_promoted_to_gt` b ON b.`id` = o.`id`
   SET o.`source_type`      = b.`source_type`,
       o.`source_id`        = b.`source_id`,
       o.`class_id`         = b.`class_id`,
       o.`class_attributes` = b.`class_attributes`;

COMMIT;

SELECT `source_type`, `source_id`, COUNT(*) AS objects, COUNT(DISTINCT `data_id`) AS frames
  FROM `data_annotation_object` WHERE `dataset_id` = 74
 GROUP BY `source_type`, `source_id`;
