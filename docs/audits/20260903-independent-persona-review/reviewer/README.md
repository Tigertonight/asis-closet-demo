# 独立人格复核

只交付本目录 / reviewer.zip，不给审核者 examiner-key.json。
本包包含 160 套匿名穿搭；先阅读 persona-rubric.json，逐套查看大图。
不要查询源文件名、原人格标签、推荐分或生产提示词；按视觉判断 Top-1 / Top-2。
reason 需写出廓形、材质观感、色彩、比例、场景等证据；不确定也必须如实说明。
verdict 填 accept / reject / uncertain，issues 填搭配冲突、轮廓雷同、人格弱等问题。
answers.json 填审核者姓名/身份标识；只有未参与这些内容的生产/标注且未看到答案者才能声明 independent=true、labels_hidden=true。
本工具只记录独立性声明，不认证真实身份，不能用同一生产者的自审冒充盲审。
Top-1 ≥70%、Top-2 ≥90% 是待验证目标，不是本包的已取得成绩。
样本审查不代表 1,169 套全量审查；结果回收后逐套处置，禁止按总分自动批准整个池。
