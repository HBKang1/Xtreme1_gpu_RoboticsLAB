-- map_model_class_to_ontology_ds71.sql 되돌리기.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/unmap_model_class_ds71.sql
--
-- 백업 테이블 bak_ds71_model_class_map 이 있어야 한다.

START TRANSACTION;

UPDATE `data_annotation_object` o
  JOIN `bak_ds71_model_class_map` b ON b.`id` = o.`id`
   SET o.`class_id` = b.`class_id`,
       o.`class_attributes` = b.`class_attributes`;

COMMIT;

SELECT `source_type`,
       JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.modelClass')) AS model_class,
       `class_id`,
       COUNT(*) AS objects
  FROM `data_annotation_object`
 WHERE `dataset_id` = 71
 GROUP BY 1, 2, 3
 ORDER BY objects DESC;
