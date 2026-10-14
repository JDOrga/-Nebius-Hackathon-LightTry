# 代码、模型和素材来源

固定上游：nv-tlabs/cosmos-transfer1-diffusion-renderer，commit `0f3e2dc435032ecbad654c2fc2153df85384b138`。本工程保存获取说明、上游依赖清单和必要 HDR 补丁，不复制整份上游或模型。上游代码的 SPDX/版权与 Apache-2.0 许可证必须继续保留；许可证副本在 `third_party/Cosmos-LICENSE`，并不为本工程自有内容授予新的总体许可。

HDR 补丁修改 rendering_utils.py、utils_env_proj.py，添加独立 env_sampling.py。补丁保留上下文中的上游版权信息，新增采样模块的来源为原独立实现；不宣称 NVIDIA 代码是原创。

模型与代码许可分开：Diffusion_Renderer_Inverse_Cosmos_7B、Diffusion_Renderer_Forward_Cosmos_7B 和 Cosmos Tokenizer 权重由各自模型卡及 NVIDIA Open Model License 管理。模型仓库与不可变 revision 在 weights_manifest 中。没有把权重按 MIT/Apache 代码分发，也不从历史授权推断另一操作者同意许可。

本仓库不包含真实演示图片或 HDR。`manifests/assets.json` 仅列出固定上游官方示例 image_1.jpg 与三个 HDR 的地址、大小和校验值。素材存放在自己的数据目录，按原来源保留署名和许可；现有清单没有充分记录每项图片/HDR 的独立发布授权，因此未经补齐来源/作者/许可，不把它们作为公开演示发布。

所有单元测试图片、公钥、云状态均为现场生成的合成数据。历史 contact sheet、截图、实验输出、原始四素材及用户文件保留在旧目录，不提交。
