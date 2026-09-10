-- create_dataset_classes_ds79.sql 되돌리기.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/drop_dataset_classes_ds79.sql
--
-- 주의: 이 클래스를 참조하는 어노테이션(data_annotation_object.class_id)이 이미
-- 있으면 지우지 않는다. 지우면 그 객체들이 클래스 없는 상태로 남는다.

SET @dsid = 79;

SELECT COUNT(*) AS objects_referencing_classes
  FROM `data_annotation_object`
 WHERE `dataset_id` = @dsid AND `class_id` IS NOT NULL;

DELETE FROM `dataset_class`
 WHERE `dataset_id` = @dsid
   AND NOT EXISTS (SELECT 1 FROM `data_annotation_object` o
                    WHERE o.`dataset_id` = @dsid AND o.`class_id` IS NOT NULL);

SELECT COUNT(*) AS remaining_classes FROM `dataset_class` WHERE `dataset_id` = @dsid;
