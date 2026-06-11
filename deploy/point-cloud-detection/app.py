import numpy as np
from pcdet_open.service import *

from pcdet_open.src.load_pcd import PointCloud
from pcdet_open.src.predictor import Predictor

import io
import requests
from os.path import join, dirname, abspath
import gc


class AppHandler(BaseApiHandler):
    predictor = None
    full_nms = True

    @staticmethod
    def _supports_full_nms(model):
        # query-based models (e.g. TransFusion) have no DENSE_HEAD.POST_PROCESSING.NMS_CONFIG;
        # calling Predictor with full_nms=True would raise KeyError for them
        try:
            return 'NMS_CONFIG' in model.model_cfg.DENSE_HEAD.POST_PROCESSING
        except (AttributeError, KeyError, TypeError):
            return False

    # override: Called for each request.
    def initialize(self, cfg_file: str, ckpt: str):
        if AppHandler.predictor is None:
            AppHandler.predictor = Predictor(cfg_file=cfg_file, ckpt=ckpt)
            AppHandler.full_nms = self._supports_full_nms(AppHandler.predictor.model)
            logging.info(f"full_nms={AppHandler.full_nms} (auto-detected from cfg)")

    # override
    def post(self):
        args = self.args
        datas = self.get_field(args, key='datas', type_=list, check_empty=True)

        results = [self.process_data(data) for data in datas]

        # clean up memory to avoid OOM
        gc.collect()

        self.return_ok(results)

    @staticmethod
    def _build_item_error(code: str, message: str, id: int = None):
        return {
            "id": id,
            "code": code,
            "message": message
        }

    def process_data(self, data):
        if not isinstance(data, dict):
            return self._build_item_error("InvalidArgument", "data must be a dictionary")

        id = data.get("id", None)
        if id is None:
            return self._build_item_error("InvalidArgument", 'missing "id"')

        pcd_url = self.get_field(data, key='pointCloudUrl', type_=str)
        if pcd_url is None:
            return self._build_item_error("InvalidArgument", 'missing "pointCloudUrl"')

        try:
            t = Timing()
            logging.info(f"{'-'*10} {pcd_url} {'-'*10}")

            # download
            r = requests.get(pcd_url, allow_redirects=True)
            t.log_interval(f"DOWNLOAD pcd({len(r.content)/1024/1024:.2g}MB)")

            # load pcd
            pcd_path = io.BytesIO(r.content)
            pc = PointCloud(pcd_path).normalized_numpy()
            t.log_interval(f"LOAD pcd")

            # remove nan and zeros
            count1 = len(pc)
            pc = pc[~np.isnan(pc[:, :3]).any(axis=1)]
            count2 = len(pc)
            if count2 < count1:
                logging.info(f"\tremove {count1 - count2} nan points")
            
            pc = pc[(pc[:, :3] != 0).any(axis=1)]
            count3 = len(pc)
            if count3 < count2:
                logging.info(f"\tremove {count2 - count3} zero points")

            # remove low-intensity points (snow noise): raw intensity 0,1,2
            # guard: pcds without intensity field load as (N, 3) — skip filtering
            if pc.shape[1] >= 4:
                count4 = len(pc)
                pc = pc[pc[:, 3] > 2]
                if len(pc) < count4:
                    logging.info(f"\tremove {count4 - len(pc)} low-intensity points (raw intensity <= 2)")
            t.log_interval(f"VALIDATE points")

            # predict
            results, _ = self.predictor(points=pc, full_nms=AppHandler.full_nms)
            t.log_interval(f"MODEL run")
            logging.info(f"{pc.shape} => {len(results['pred_boxes'])} objects")
        except Exception as e:
            logging.exception(e)
            return self._build_item_error("SystemError", str(e), id=id)

        class_names = self.predictor.class_names
        objects = [
            {
                "label": class_names[label-1].upper(),
                "confidence": score,

                "x": box[0],
                "y": box[1],
                "z": box[2],
                "dx": box[3],
                "dy": box[4],
                "dz": box[5],
                "rotX": 0,
                "rotY": 0,
                "rotZ": box[6]
            }
            for box, score, label in zip(
                results['pred_boxes'].astype(np.float64).round(3).tolist(),
                results['pred_scores'].astype(np.float64).round(3).tolist(),
                results['pred_labels'].tolist())
        ]

        return {
            "id": id,
            "code": "OK",
            "message": "",
            "objects": objects
        }


# model presets: cfg + default checkpoint. full_nms is auto-detected from the cfg,
# so any OpenPCDet model can also be served via explicit --cfg/--ckpt without code changes.
# OpenPCDet tools/cfgs yamls resolve _BASE_CONFIG_ relative to working_dir (/app/pcdet_open).
MODELS = {
    'centerpoint': {
        'cfg': 'cfgs/nuscenes_models/cbgs_voxel0075_res3d_centerpoint.yaml',  # relative to app dir
        'ckpt': '/app/cbgs_voxel0075_centerpoint_nds_6648.pth',               # shipped in image
    },
    'transfusion': {
        'cfg': '/app/OpenPCDet/tools/cfgs/nuscenes_models/transfusion_lidar.yaml',
        'ckpt': '/app/cbgs_transfusion_lidar.pth',                            # mount via compose
    },
    'voxelnext': {
        'cfg': '/app/OpenPCDet/tools/cfgs/nuscenes_models/cbgs_voxel0075_voxelnext.yaml',
        'ckpt': '/app/cbgs_voxel0075_voxelnext.pth',                          # mount via compose
    },
}


def main():
    parser = ArgumentParser()
    parser.add_argument('--model', type=str, default='centerpoint', choices=sorted(MODELS),
                        help='model preset (cfg + default checkpoint)')
    parser.add_argument('--cfg', type=str, default=None, help='override cfg yaml path')
    parser.add_argument('--ckpt', type=str, default=None, help='override checkpoint path')
    args = parse_args(parser)

    app_dir = dirname(abspath(__file__))
    preset = MODELS[args.model]
    cfg_file = args.cfg or join(app_dir, preset['cfg'])
    ckpt = args.ckpt or preset['ckpt']
    logging.info(f"model={args.model} cfg={cfg_file} ckpt={ckpt}")

    start_service([
            (r'/pointCloud/recognition', AppHandler, dict(cfg_file=cfg_file, ckpt=ckpt)),
        ],
        args)


if __name__ == '__main__':
    main()
