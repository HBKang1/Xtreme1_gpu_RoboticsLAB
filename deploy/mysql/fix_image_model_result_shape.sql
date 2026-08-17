-- 이미지 모델 실행 결과를 image-tool 이 읽을 수 있는 모양으로 고친다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/fix_image_model_result_shape.sql
--
-- 문제: ImageDetectionModelHandler 가 ObjectBO 를 그대로 직렬화해서 저장하는 바람에
--       points 가 최상위에 놓였다. 툴은 obj.contour.points 를 읽고(result-request
--       .convertObject2Annotate) 비어 있으면 그 객체를 조용히 버린다. 신뢰도도
--       modelConfidence 키에서 읽는데 confidence 로 저장돼 있었다.
--
--   before  {"type":"RECTANGLE","points":[...],"confidence":0.94,"modelClass":"Vehicle"}
--   after   {"id":..,"type":"RECTANGLE","contour":{"points":[...]},"modelClass":"Vehicle",
--            "modelConfidence":0.94,"trackId":..,"trackName":..,"sourceId":..,
--            "sourceType":"MODEL","version":0,"classValues":[]}
--
-- 백엔드 코드는 ImageDetectionModelHandler.syncModelAnnotationResult 에서 고쳤으므로
-- 앞으로의 실행은 처음부터 올바른 모양으로 저장된다. 이 스크립트는 그 전에 쌓인 것만 손본다.
-- 포인트 클라우드 결과는 이미 contour 가 있어 WHERE 절에서 걸러진다.

-- 되돌릴 수 있도록 대상 행을 통째로 백업
DROP TABLE IF EXISTS `data_annotation_object_bak_shape`;
CREATE TABLE `data_annotation_object_bak_shape` AS
SELECT * FROM `data_annotation_object`
 WHERE `source_type` = 'MODEL'
   AND JSON_EXTRACT(`class_attributes`, '$.contour') IS NULL
   AND JSON_EXTRACT(`class_attributes`, '$.points')  IS NOT NULL;

SELECT COUNT(*) AS backed_up FROM `data_annotation_object_bak_shape`;

UPDATE `data_annotation_object`
   SET `class_attributes` = JSON_OBJECT(
         'id',              REPLACE(UUID(), '-', ''),
         'type',            JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.type')),
         'contour',         JSON_OBJECT('points', JSON_EXTRACT(`class_attributes`, '$.points')),
         'modelClass',      JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.modelClass')),
         'modelConfidence', JSON_EXTRACT(`class_attributes`, '$.confidence'),
         'trackId',         REPLACE(UUID(), '-', ''),
         'trackName',       CAST(`id` AS CHAR),
         'sourceId',        `source_id`,
         'sourceType',      'MODEL',
         'version',         0,
         'classValues',     JSON_ARRAY()
       )
 WHERE `source_type` = 'MODEL'
   AND JSON_EXTRACT(`class_attributes`, '$.contour') IS NULL
   AND JSON_EXTRACT(`class_attributes`, '$.points')  IS NOT NULL;

SELECT `dataset_id`, `source_id`, COUNT(*) AS fixed
  FROM `data_annotation_object`
 WHERE `source_type` = 'MODEL'
   AND JSON_EXTRACT(`class_attributes`, '$.contour') IS NOT NULL
 GROUP BY `dataset_id`, `source_id`;
