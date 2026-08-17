import { IFrame } from '@/package/image-editor';
import { ISaveFormat, ISaveResp } from '../types';
import { get, post } from './base';
import { Api, DataflowAnnotationParamsReq, DataflowAnnotationParamsRsp, IFileConfig } from './type';

// 씬을 열면 LoadManager 가 전체 프레임을 한 번에 요청한다(isSeriesFrame 분기).
// 프레임 ID 가 전부 쿼리스트링에 들어가므로 씬이 크면 URL 이 헤더 한도를 넘어
// nginx 가 414, Tomcat 이 400 을 돌려주고 툴에는 network error 로 보인다.
// (1,358 프레임 = 8.2KB > nginx 8KB, 1,240 프레임 = 7.5KB + 쿠키 > Tomcat 8KB)
// 그래서 여기서 잘라 보낸다. 200개면 URL 이 약 1.2KB 로 기존 LIDAR 씬과 같은 수준.
const DATA_ID_CHUNK = 200;
// 서버를 한꺼번에 때리지 않도록 동시 요청 수를 제한한다.
const DATA_ID_CONCURRENCY = 4;

export async function getAnnotationByDataIds(params: DataflowAnnotationParamsReq) {
  const url = `${Api.ANNOTATION}/data/listByDataIds`;

  const chunks: Array<string | number>[] = [];
  for (let i = 0; i < params.dataIds.length; i += DATA_ID_CHUNK) {
    chunks.push(params.dataIds.slice(i, i + DATA_ID_CHUNK));
  }

  const data = [] as DataflowAnnotationParamsRsp[];
  for (let i = 0; i < chunks.length; i += DATA_ID_CONCURRENCY) {
    const batch = chunks.slice(i, i + DATA_ID_CONCURRENCY);
    const results = await Promise.all(
      batch.map((ids) => get(url, { dataIds: ids.join(',') })),
    );
    results.forEach((res) => data.push(...((res.data || []) as DataflowAnnotationParamsRsp[])));
  }

  console.log('frame data', data.length, `(${chunks.length} chunks)`);
  return data;
}

export async function getDataFile(id: string) {
  const url = `${Api.DATA}/listByIds`;
  let data = await get(url, { dataIds: id });
  data = data.data || [];

  const name = data[0]?.name || '';
  let configs = [] as IFileConfig[];
  data[0].content.forEach((config: any) => {
    let file = config.files?.[0].file || config.file;
    configs.push({
      name,
      size: +file.size,
      url: file.url,
      deviceName: config.name,
    });
  });

  return {
    config: configs[0],
    datasetId: data[0].datasetId,
    annotationStatus: data[0].annotationStatus,
    validStatus: data[0].status,
  };
}

export async function saveData(datasetId: string, dataInfos: Array<ISaveFormat>) {
  const url = `${Api.ANNOTATION}/data/save`;

  let data = await post(url, { datasetId, dataInfos });
  return (data.data || []) as ISaveResp[];
}

export async function getFrameSeriesData(datasetId: string, frameSeriesId: string) {
  const url = `/api/data/getDataIdBySceneIds`;
  const data = await get(url, {
    datasetId,
    sceneIds: frameSeriesId,
    // sortFiled: 'ID',
    // ascOrDesc: 'ASC',
  });
  console.log(data);
  const list = (data.data || {})[frameSeriesId] || [];
  // (list as any[]).reverse();
  if (list.length === 0) throw '';

  const dataList = [] as IFrame[];
  list.forEach((e: any) => {
    dataList.push({
      id: e,
      datasetId: datasetId,
      needSave: false,
      model: undefined,
      sceneId: frameSeriesId,
    } as IFrame);
  });
  return dataList;
  // return configs;
}
