# Siri Styling 素材与拆款交付

交付对应 16 组标准人格，以及 FILM、LOOP、VOID、WABI 的 4 组微胖版本。每组 4 条笔记，共 80 条笔记、461 个单品；通过 `templateId + noteId` 独立绑定，微胖版本不会覆盖标准版本。

## 文件与引用

- `app/static/report-builder/data/16-personality-templates.json`：本地笔记配置，保留既有人格基础资料并同步本次四条笔记。
- `app/data/material-assets.v1.json`：素材主表，记录 SHA-256、大小、类型、对象 URL，以及七牛 Bucket、Key、私有访问标识。
- `app/data/styling-delivery.v1.json`：完整拆款数据，包括原始描述、原图、单品、穿法、叠穿顺序，以及人格、体型、笔记和素材之间的关系。
- `app/data/styling-source-assets.v1.json`：交付目录 645 个图片文件与素材 ID 的映射。
- `app/data/styling-report-assets.v1.json`：20 组报告当前选用的 180 个图片文件与素材 ID 的映射。
- `app/data/styling-delivery-verification.v1.json`：读取及 SHA-256 校验结果，以其中的状态和数量判断是否全部完成。

两个图片清单合计 825 个文件引用，按原始文件内容去重后为 704 张、631,806,695 字节。交付目录本身包含 624 张不同图片，其余 80 张是项目既有报告基础素材。文件名相同但内容不同的图片不会互相覆盖。

业务数据使用 `assetId`；项目中通过 `/api/v1/material-assets/{assetId}/content` 获取图片。拆款里的 `contentUrl` 是这个固定入口，`url` 是存储对象地址。私有空间的对象地址不能直接匿名访问，临时签名只在服务端读取时生成，不写入数据文件。

## 七牛配置

本次查询确认空间为 `selfit`，区域为 `z0`（华东），上传节点为 `https://upload.qiniup.com`，当前为私有空间。现有访问域名为 `http://tk7xxzqgj.hd-bkt.clouddn.com`。

凭据和连接配置保存在项目根目录 `.env.qiniu`，已被 Git 忽略。服务端读取该文件，也可通过 `QINIU_ENV_FILE` 指定位置；环境变量优先。变量名如下，仓库内不保存 AK/SK 的值：

```dotenv
QINIU_ACCESS_KEY=
QINIU_SECRET_KEY=
QINIU_BUCKET=selfit
QINIU_REGION=z0
QINIU_UPLOAD_HOST=https://upload.qiniup.com
QINIU_PUBLIC_BASE=http://tk7xxzqgj.hd-bkt.clouddn.com
QINIU_PRIVATE=true
```

现有域名是七牛测试域名，只有 30 个自然日生命周期，不支持 HTTPS 配置；长期使用需绑定正式域名。参见[七牛测试域名规范](https://developer.qiniu.com/fusion/1319/test-domain-access-restriction-rules)。项目对这些已授权发布的素材使用同源图片接口，服务端签名下载、校验并缓存到 `outputs/material-cache/`，因此页面无需携带签名，也无需直接加载 HTTP 域名。此素材库不用于用户私有照片。

## 上传与复核

上传工具使用 `requirements-storage.txt` 中的七牛官方 SDK。上传范围只包含本次交付和已选报告图片，每个对象上传后核对七牛返回的 Key 和内容校验值，再更新主表。成功记录可复用；运行失败后按同样命令继续即可。

```sh
.venv/bin/python scripts/publish_styling_delivery.py \
  --backend qiniu --env-file .env.qiniu --workers 4 \
  --bucket selfit --public-base http://tk7xxzqgj.hd-bkt.clouddn.com \
  --source /path/to/拆款交付-siri-styling

.venv/bin/python scripts/verify_styling_delivery.py --workers 4
```

对象 Key 使用 `selfit/materials/siri-styling-v1/asset_{完整SHA256}.{扩展名}`。更换域名时更新素材主表的对象 URL，保留 ID 和存储 Key；笔记和拆款绑定无需修改。发布到其他环境时，需要在那里配置签名凭据或准备已校验缓存。当前操作仅更新本地配置及云端素材，不代表应用代码已部署。
