-- YOLO26 Zenix (Day) 이미지 2D 검출 모델 등록
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/image-detection/register_model.sql
--
-- model_class.code 는 체크포인트의 names(vehicle, pedestrian)와 대소문자까지 정확히
-- 같아야 한다. 다르면 박스는 그려지되 클래스 이름이 비어서 들어온다
-- (ModelUseCase.getModelClassMapByModelId 가 code 로 매핑).
-- name 은 UI 표시용이라 자유롭게 바꿔도 된다.

INSERT INTO `model`
  (`name`, `version`, `description`, `scenario`, `dataset_type`, `model_type`,
   `model_code`, `url`, `is_deleted`, `del_unique_key`, `created_at`, `created_by`)
VALUES
  ('YOLO26 Zenix (Day)', 'v1.0',
   '<p>YOLO26l fine-tuned on Zenix_Day_01 keyframes (239 imgs, imgsz=640, freeze=10). Detects vehicle / pedestrian.</p>',
   '["Image","Object Detection","Zenix"]',
   'IMAGE', 'DETECTION', 'IMAGE_DETECTION',
   'http://image-object-detection-yolo:5000/image/recognition',
   b'0', 0, current_timestamp, 1)
ON DUPLICATE KEY UPDATE
  `url` = VALUES(`url`), `version` = VALUES(`version`);

SET @mid = (SELECT `id` FROM `model` WHERE `name` = 'YOLO26 Zenix (Day)');

DELETE FROM `model_class` WHERE `model_id` = @mid;

INSERT INTO `model_class` (`model_id`, `name`, `code`, `created_at`, `created_by`) VALUES
  (@mid, 'Vehicle',    'vehicle',    current_timestamp, 1),
  (@mid, 'Pedestrian', 'pedestrian', current_timestamp, 1);

SELECT m.`id`, m.`name`, m.`url`, GROUP_CONCAT(c.`code`) AS classes
  FROM `model` m LEFT JOIN `model_class` c ON c.`model_id` = m.`id`
 WHERE m.`id` = @mid GROUP BY m.`id`;
