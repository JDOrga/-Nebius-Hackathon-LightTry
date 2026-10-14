# 演示素材分发核对（2026-10-09）

本轮只准备本地演示素材，不上传、不传输、不发布。来源 URL、哈希、代码许可证各自解决不同问题，均不能替代素材授权。全包被忽略；公开候选文件只含代码、文档、署名/映射元数据和校验清单，不含真实图片。

## 原照和实际模型输入

历史依据：该运行的 `prepared_inputs.json`、`ATTRIBUTION.txt`；精简字段进入包内 `source-records.json`，原记录的 SHA256 留存，原文件不改写。2026-10-09 只读核对下面照片描述页的作者/许可，与历史记录一致；没有重下载图片。

|样例|作者|既有图片许可依据|本轮决定|
|---|---|---|---|
|陶罐|Miss Kamola|[照片页](https://commons.wikimedia.org/wiki/File:Terracotta_pot._Fayoztepa.jpg)，[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)|保留原照及实际输入，仅本地包|
|茶盒|Wellcome Library, London|[照片页](https://commons.wikimedia.org/wiki/File:Tabloid_Compressed_Tea_tin;_Burroughs_Wellcome_%26_Co._product_Wellcome_L0041232.jpg)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)|保留作者、来源、许可链接、修改说明，仅本地包|
|金属壶|oatsy40|[照片页](https://commons.wikimedia.org/wiki/File:Metal_Tea_Pot_(16063326056).jpg)，[CC BY 2.0](https://creativecommons.org/licenses/by/2.0/)|保留作者、来源、许可链接、修改说明，仅本地包|
|玻璃杯|Yesseruser|[照片页](https://commons.wikimedia.org/wiki/File:Glass_bottle.jpg)，[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)|保留原照及实际输入，仅本地包|

实际输入沿用既有 EXIF 方向处理、记录中的 ICC/sRGB 处理、等比缩放、1280×704 灰色留白；原照保留原文件。输入是照片派生，不把生成 JPEG 的完整授权结论延伸到输入。署名文件和说明页保留处理说明与不暗示背书的表述。本轮复制没有重新编码、修图、裁切或替换。

原照及输入具有上述许可依据；本轮为控制交付范围，也没有将它们列入公开媒体候选清单。历史照片记录在包内按字段摘录，不能把清单文件自身的许可当成图片许可。

## HDR 和 12 张已有结果

本地服务只读取 JPEG/PNG；三个 HDR 本体不需要、不装包。保留晴日公园 → sunny_vondelpark_2k.hdr / 0、粉色晨光 → pink_sunrise_2k.hdr / 1、夜间街灯 → street_lamp_2k.hdr / 2 的名称、哈希、固定上游 commit 来源。三 HDR 独立作者与素材许可仍待核实；未从文件名推测作者或 CC0。

12 张结果与四原照、四实际输入、HDR 顺序、历史 flat JPEG 和 canonical frame 校验值逐项对应。生成/导出身份不是公开分发授权。结果说明保留“Cosmos 生成式重打光”、作者与原照许可，不宣称结果继承 Apache-2.0。

已有上游 README 指向 [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/)。本轮只读检查该官方页面（显示版本日期 2025-10-24）：输出不属于 Derivative Model；NVIDIA 不主张输出所有权，输出及后续使用由使用者负责；另列模型/产品署名及独立组件条款。这并未授予第三方照片或 HDR 权利，也不证明这次历史生成所用全部模型/组件的适用许可已经逐项核清。

继续缺少：三 HDR 独立许可与其对输出分发的适用判断；历史所用模型/组件许可版本的完整对应及输出条款核对；结果公开分发的最终授权结论。未来拟发布时应按实际适用条款核查署名（包括适用时的 Built on NVIDIA Cosmos），本轮没有接受新许可或运行模型。

因此 **12 结果及全素材包默认仅本地保留，不进入公开候选、不上传**。不附带 HDR 本体不能清除这些缺口。历史目录及原始证据保留；本轮不是历史整轮运行成功声明。
