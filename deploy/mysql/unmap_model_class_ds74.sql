-- map_model_class_to_ontology_ds74.sql 되돌리기.
-- 백업 테이블(bak_ds74_model_class_map)의 원래 class_id / class_attributes 로 복원한다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/unmap_model_class_ds74.sql
--
-- 주의: 복원 후 그 사이 툴에서 저장한 편집 내용은 사라진다.

START TRANSACTION;

UPDATE `data_annotation_object` o
  JOIN `bak_ds74_model_class_map` b ON b.`id` = o.`id`
   SET o.`class_id` = b.`class_id`,
       o.`class_attributes` = b.`class_attributes`;

COMMIT;

SELECT `source_type`, `source_id`, COUNT(*) AS objects, SUM(`class_id` IS NULL) AS null_class
  FROM `data_annotation_object` WHERE `dataset_id` = 74
 GROUP BY `source_type`, `source_id`;
