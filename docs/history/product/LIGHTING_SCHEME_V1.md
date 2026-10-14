# 光照方案 v1：身份与迁移

## 浏览器/请求 schema（严格字段）

```json
{
  "schemaVersion": 1,
  "planId": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "version": 2,
  "parentVersion": 1,
  "name": "偏暗比较",
  "inputId": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "parameters": {"environmentId": "sunny", "offsetDeg": 0, "strength": 0.7}
}
```

planId/inputId 为32位小写hex；version1–1000，parentVersion 为小于 version 的整数或 null；名称1–60字，不含控制字符。未知字段、NaN/Inf、bool数字、非白名单环境/组合拒绝。

当前能力：三个环境原默认(0,1)；仅 sunny 增加(0,0.7)及实验性固定(45,1)。不是独立枚举的全排列，(45,0.7)禁止；1.4与-45关闭。offsetDeg 是基于原180°加载约定的附加偏移；不是把180°误称额外旋转，不使用 rotate_light 动画布尔值模拟任意角度。

## 多层身份

1. 规范化 parameters 增加 schemaVersion、确切 HDR SHA、processing 与 capabilityRevision。canonical JSON 排序键、统一整数数值；recipeKey=SHA256(normalized parameters)。默认档标明 legacy-fixed-preset，仅代表原加载约定，不声称历史记录含参数实测。
2. 提交 preset identity=SHA256(planId,version,recipeKey)。原请求幂等 fingerprint 已包含这个 identity、inputId 和原照片 SHA，因此参数/版本改变不能沿用旧 requestId 偷换结果。重复同一身份/字节返回同任务，变化返回409。
3. forward identities 包含逆向输入/provenance、五通道及 inverseKey、完整 HDR 方案、forward 权重、patch、runConfig、随机策略、请求/task/nonce。恢复必须全等；不修改旧 marker。
4. 结果回执保留原 taskId/nonce/input SHA/original SHA、runConfig、成功进程 exit、输出 SHA/尺寸及严格 inverse 证据；新增 lighting.recipeKey/parameters/adapterVersion/实际 helper condition/实际 model-entry tensor 证明。模型输入 env_ldr/env_log 按数组逐元素验证；这不是成图可控性证明。
5. 前端不按 sunny 名称借图：inputId、完整离散参数、成功状态、过期/不确定状态及任务结果身份必须匹配；具体图仍由服务重新核验哈希和回执。独立 study 只能匹配具体 sample/input SHA 与参数，始终标注“独立受控实测、非本次在线生成”。

## 版本/跨图/恢复

- 编辑追加 version，parentVersion指向旧版本；名称修改也版本化。
- 另存变体换 planId、version1；不自动生成。
- 跨图只带参数，新 inputId 及新方案身份，旧图不显示为该照片结果，inverse 不随库迁移。
- localStorage 存方案/版本/光标/任务 ID，不存照片、Key、机器配置。服务重启从原 request.json 还原提交快照，历史文件不回写伪参数。
- 尚未确认的 POST 保存 requestId+不可变方案/input快照+原照片SHA；刷新先 GET /api/requests/id。无服务记录时仅提示重新载入同一字节，不自动重算。
- 已生成图可作为同照片同配方的有效已有结果复用，来源显示其源方案版本/实际日期，而非谎称新版本刚生成。

## 无破坏迁移

原 `project/server.py`、`project/web`、3固定 preset 请求/历史、inverse cache 与来源记录原字节保留。新入口与新任务目录隔离；旧请求无 lightingScheme 仍按旧固定白名单处理，不补写不存在的参数证明。所有189个初始 tracked 文件最终哈希一致。停止新本地服务即可返回原应用；四角色事务另有独立可执行 ROLLBACK.sh。

## 局限

光照效果可能改轮廓、颜色、文字、纹理、材质。0.7 是较低 HDR 条件，不是精确EV；+45是有真实响应的固定配方，人工方向验收仍待补。参数适配器的普通网页→GPU→结果真实联合链路未运行。不能把离线身份测试替代该验收。
