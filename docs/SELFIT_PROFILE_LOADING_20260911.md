# 我的档案加载优化（2026-09-11）

档案数据返回后先显示身体特征和报告，正面照、全身照同时请求，每张照片独立更新。两张照片不再阻塞整页。加载失败只在相应照片区域显示重试；204/404 保留上传入口。

只替换照片所在的 DOM 区域，保留档案滚动位置和正在编辑的选项。刷新档案或保存新照片会使旧照片请求失效，避免旧结果覆盖新内容。授权请求头和现有页面内缓存保持原有规则；没有修改后端照片权限、标注生成或缓存策略。

修改文件：`app/static/selfit-tryon/studio.js`、`studio.css`、`index.html`、`DESIGN.md`。追加异步行为回归测试 `tests/test_selfit_profile_loading.cjs`。本次未提交、推送或部署。

## 验证

- `node --test tests/test_selfit_profile_loading.cjs tests/test_selfit_home_loading.cjs tests/test_selfit_studio_feed.cjs`：21 项通过。
- `node --check app/static/selfit-tryon/studio.js`、`git diff --check`：通过。
- `python -m pytest -q tests/test_selfit_studio.py`：9 项通过。
- 独立 localhost 测试服务使用仓库示例照片和合成账号，浏览器加载实际生产 JS/CSS；未读写真实用户档案。
- 393 × 852：暂停两个照片响应，档案特征和报告已展示；等待期间能编辑并保存脸型，先返回的正面照不会打断编辑。
- 全身照完成前后档案滚动位置均为 444.5px。
- 1440 × 960：应用外壳宽 393px，左右居中；故意返回单张照片 503，档案仍显示，点击该照片重试成功。
- 手机和桌面均无横向溢出、文字重叠、按钮裁切；照片占位与完成后的尺寸一致。正常页面无控制台警告、错误或损坏图片。模拟 503 页面仅出现预期的失败请求。
- 按 DESIGN.md 自检本次涉及的档案加载、恢复文案、图片区域、布局和按钮；未变更引导测试、算法或试穿生成。

## 扩展检查中的既有问题

额外执行 `tests/test_selfit_onboarding_api.py` 的 profile 相关用例时，`test_account_profile_edit_is_owned_versioned_and_survives_expiry` 失败：测试构造的 face 记录只有 attributes，没有 accepted 状态，现有后端不把它作为可用照片，因此返回值没有测试期望的 skin。本次没有修改该接口或此测试数据。排除标注图用例后的检查结果为 10 通过、1 失败（39 未选中），日志在 `outputs/profile-loading-20260911/python-check.log`。

`test_profile_photo_replacement_updates_archive_and_serves_annotated_overlay` 在本机沙箱执行时，MediaPipe 原生 face detector 初始化中止 Python 进程（exit 134），未作为通过项。没有为绕开该问题修改图像分析实现。

本次工作前的前端文件备份、隔离测试服务和手机截图在 `outputs/profile-loading-20260911/`；其中备份用于区分同期其他工作，不能整体回滚覆盖其他修改。
