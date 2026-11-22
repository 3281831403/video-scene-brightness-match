# video-scene-brightness-match

## 题面

把多机位素材拼成一条后，镜头之间一亮一暗、过曝还回绕成黑点：现有实现用等权平均计算亮度，绿色权重错误；分位裁剪没有忽略过曝像素，暗镜头被抬高；增益用线性比值而不是 dB；应用增益后不做钳制，高光回绕成暗点；平滑窗口为 0 时退化并触发除零；异常检测写死 6 dB，忽略画面内容；尺寸不一致不报错，后续索引越界；NaN 不做校验，整个镜头变黑；批量处理共用同一份统计，镜头之间串扰；window<0 不校验，切片直接报错。brightmatch/match.py 是核心，tests/test_match.py 15个红。要修的是：修复上述 10 个缺陷，只改 brightmatch/match.py，让 15 条测试全部通过。

## 数据模型

- 帧：二维 `list[list[float]]`，每行是一个 RGB 像素，通道顺序为 R、G、B。
- 镜头：帧列表，即 `list[list[list[float]]]`；同一镜头内的帧应尺寸一致。
- 亮度：线性光，范围 `0.0..1.0`；Rec.709 权重为 `0.2126 R + 0.7152 G + 0.0722 B`。
- 增益：执行 `20 * log10(ref / cur)` 得到的 dB 值。
- 浮点断言：绝对容差 `1e-6`。
- 非法输入：抛出 `BrightnessError`。

`brightmatch/match.py` 中的 8 个公开函数目前全部是 `raise NotImplementedError` 桩，需要在不修改测试的前提下逐一实现。

## 运行方式

在仓库根目录执行：

```powershell
python -m pytest tests -q
```

初始状态必须恰好输出 `15 failed`，并且不能出现 collection、import 或 syntax error。修复完成后应输出 `15 passed`；若仍有失败，失败项应当只来自尚未实现的桩。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 音视频处理 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 约束

- 只使用 Python 标准库（`math`）与 `pytest`，全程离线，不使用随机数。
- `tests/test_match.py` 不可修改；15 条测试是唯一验收标准。
- 修复只允许落在 `brightmatch/match.py`。
