-- purge_snow_day_model_results.sql 되돌리기.
-- 백업 테이블(bak_snow_*)에서 원래 행을 그대로 복구한다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/restore_snow_day_model_results.sql
--
-- 주의: purge 이후에 같은 데이터셋에 모델을 다시 돌렸다면, 그 결과와 뒤섞인다.
--       그런 경우 복구 전에 새 실행 결과를 먼저 정리할 것.

START TRANSACTION;

INSERT INTO `model_run_record`     SELECT * FROM `bak_snow_run_record`;
INSERT INTO `model_data_result`    SELECT * FROM `bak_snow_data_result`;
INSERT INTO `model_dataset_result` SELECT * FROM `bak_snow_dataset_result`;
INSERT INTO `data_annotation_object` SELECT * FROM `bak_snow_annotation_object`;

COMMIT;

SELECT 'restored' AS phase,
       (SELECT COUNT(*) FROM `data_annotation_object`
         WHERE `dataset_id` IN (69,71,72,73,74,75) AND `source_type`='MODEL') AS annotation_object,
       (SELECT COUNT(*) FROM `model_dataset_result` WHERE `dataset_id` IN (69,71,72,73,74,75)) AS dataset_result,
       (SELECT COUNT(*) FROM `model_data_result`    WHERE `dataset_id` IN (69,71,72,73,74,75)) AS data_result,
       (SELECT COUNT(*) FROM `model_run_record`     WHERE `dataset_id` IN (69,71,72,73,74,75)) AS run_record;
