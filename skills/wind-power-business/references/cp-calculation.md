# Cp 计算

## 使用目标

根据用户提供的风电机组功率曲线，计算每个风速点的理论风功率和 Cp 值，并给出最终 Cp 结果。

默认最终 Cp 结果为 `Cp,max`，即功率曲线中所有有效 Cp 值的最大值；同时输出该最大值对应的风速、功率和理论风功率。

## 执行要求

用户提供功率曲线后，优先调用脚本计算，不要手工逐行计算。

默认只生成一个可编辑的 Excel 成果文件。若用户明确要求非 Excel 成果，则同时生成 Markdown、CSV、JSON 三个文件。

必须先明确计算参数：

- 空气密度 `rho`，单位 `kg/m^3`。
- 叶轮直径 `D`，单位 `m`。
- 风速单位为 `m/s`。
- 功率单位为 `kW`。

如果用户没有提供空气密度或叶轮直径，先向用户确认参数，不要运行脚本，不要使用默认值代替。

## 校验规则

先做宽松的参数疑点校验，不要把它理解为绝对技术边界。遇到下列情况时，先询问用户确认；用户确认后再继续计算：

- 空气密度 `rho` 明显不在 `0.5-1.5 kg/m^3` 范围内。
- 叶轮直径 `D` 明显不在 `30-350 m` 范围内。
- 机型名疑似包含叶轮直径，但与用户给出的 `D` 明显不一致。例如 `G5000-200` 通常优先怀疑 `200` 是叶轮直径，如果用户给出 `D=110 m`，应先询问而不是直接计算。

如果脚本计算发现 `Cp,max > 0.593` 或多行 Cp 超过贝茨极限，默认停止交付成果，并要求用户核对参数。重点核对：

- 叶轮直径 `D` 是否把半径、叶片长度、塔筒高度等误填成直径。
- 机型名是否隐含叶轮直径，例如 `G5000-200` 通常优先怀疑 `200` 是叶轮直径。
- 功率单位是否为 `kW`。
- 空气密度是否为实际计算口径。

校验失败时不要生成正式 Excel 成果；需要先让用户确认修正后的参数，再重新运行脚本。

如果用户明确确认了疑点参数，可以在脚本中增加 `--allow-suspicious-parameters` 继续生成；该开关只表示用户已确认参数，不表示跳过 `Cp,max <= 0.593` 的物理校验。

脚本路径：

```text
skills/wind-power-business/scripts/compute_cp.py
skills/wind-power-business/scripts/fill_cp_workbook.py
```

Excel 模板路径：

```text
skills/wind-power-business/assets/cp-calculation-template.xlsx
```

## CLI 用法

成果文件默认放到 `projects/` 下的项目目录，例如：

```text
projects/20260703-Cp计算/
```

默认输出可编辑 Excel：

下面命令中的 `1.02` 和 `220` 只是示例参数；实际计算前必须使用用户确认的空气密度和叶轮直径。

```bash
python skills/wind-power-business/scripts/fill_cp_workbook.py input.txt --rho 1.02 --diameter 220 --output projects/20260703-Cp计算/cp-result.xlsx
```

从 stdin 读取并输出 Excel：

```bash
Get-Content input.txt | python skills/wind-power-business/scripts/fill_cp_workbook.py --rho 1.02 --diameter 220 --output projects/20260703-Cp计算/cp-result.xlsx
```

只有在用户明确要求非 Excel 格式时，才使用下列命令，并且三种格式应一起生成。

输出 Markdown：

```bash
python skills/wind-power-business/scripts/compute_cp.py input.txt --rho 1.02 --diameter 220 --output projects/20260703-Cp计算/cp-result.md
```

输出 CSV：

```bash
python skills/wind-power-business/scripts/compute_cp.py input.txt --rho 1.02 --diameter 220 --output projects/20260703-Cp计算/cp-result.csv
```

输出 JSON：

```bash
python skills/wind-power-business/scripts/compute_cp.py input.txt --rho 1.02 --diameter 220 --output projects/20260703-Cp计算/cp-result.json
```

指定参数：

```bash
python skills/wind-power-business/scripts/fill_cp_workbook.py input.txt --rho 1.02 --diameter 220 --output projects/20260703-Cp计算/cp-result.xlsx
```

## 定义

Cp 值即风能利用系数 / 功率系数，表示风机输出功率占通过叶轮扫掠面积的理论风功率的比例。

```text
Cp = P / Pwind
```

其中：

- `P`：风机输出功率，单位通常为 `kW`。
- `Pwind`：通过叶轮扫掠面积的理论风功率，单位与 `P` 保持一致。

## 理论风功率

```text
Pwind = 0.5 * rho * V^3 * A / 1000
```

其中：

- `rho`：空气密度，单位 `kg/m^3`。
- `V`：风速，单位 `m/s`。
- `A`：叶轮扫掠面积，单位 `m^2`。
- `/1000`：将 `W` 转换为 `kW`。

叶轮扫掠面积：

```text
A = PI() * D^2 / 4
```

其中 `D` 为叶轮直径，单位 `m`。

## 完整公式

```text
Cp = P / (0.5 * rho * V^3 * PI() * D^2 / 4 / 1000)
```

## Excel 模型结构

建议把模型分为两块：

```text
模型参数（可修改）
空气密度 rho
叶轮直径 D
最大功率系数 Cp,max

输入区（手动录入）
风速 V
功率 P
推力系数 Ct

计算区（公式自动）
理论功率 Pwind
功率系数 Cp
```

`Ct` 可作为输入列保留，但不参与 Cp 计算。

## 处理流程

1. 将用户提供的功率曲线保存为临时文本文件，至少包含风速 `V` 和功率 `P` 两列。
2. 读取或确认模型参数：空气密度 `rho`、叶轮直径 `D`。缺任一参数时先问用户。
3. 对明显异常的 `rho`、`D` 或机型名口径冲突先让用户确认。
4. 默认调用 `scripts/fill_cp_workbook.py` 基于 Excel 模板生成 xlsx。
5. 若脚本提示 Cp 超过贝茨极限，不交付结果文件；先回到用户确认参数。
6. 只交付 xlsx 文件，并在回复中简述 `Cp,max`。
7. 如果用户明确要求非 Excel 成果，再调用 `scripts/compute_cp.py` 同时生成 Markdown、CSV、JSON 三个附加文件。

如果功率曲线中存在空行，跳过空行；如果风速或功率为空，不计算该行 Cp。

## Excel 公式：命名变量口径

如果将空气密度单元格命名为 `空气密度`，将叶轮直径单元格命名为 `叶轮直径`，并且第 9 行为第一条功率曲线数据：

理论功率列：

```excel
=IF($A9="","",0.5*空气密度*$A9^3*PI()*叶轮直径^2/4/1000)
```

Cp 列：

```excel
=IF(OR($A9="",$B9=""),"",$B9/$D9)
```

最大功率系数：

```excel
=MAX(E9:E108)
```

## Excel 公式：固定单元格口径

如果：

- `A2` 为风速 `V`
- `B2` 为风机输出功率 `P`
- `$D$2` 为空气密度 `rho`
- `$E$2` 为叶轮直径 `D`

则 Cp 计算公式为：

```excel
=B2/(0.5*$D$2*A2^3*PI()*$E$2^2/4/1000)
```

如果 `F2` 已经计算出理论风功率 `Pwind`，则：

```excel
=B2/F2
```

最大 Cp：

```excel
=MAX(G:G)
```

## 示例

输入：

- 风速：`3 m/s`
- 风机输出功率：`186.4 kW`
- 空气密度：`1.02 kg/m^3`
- 叶轮直径：`220 m`

理论风功率：

```text
0.5 * 1.02 * 3^3 * PI() * 220^2 / 4 / 1000 ≈ 523.5 kW
```

Cp：

```text
186.4 / 523.5 ≈ 0.356
```

## 判断口径

- Cp 不应超过 `0.593`，这是贝茨极限。
- 如果最大 Cp 大约在 `0.53` 左右，通常属于合理范围。
- 通常在额定风速以前 Cp 较高；达到额定功率后，由于功率被限制，Cp 会随风速升高快速下降。

## 输出要求

用户提供功率曲线后，输出至少包含：

- 计算参数：空气密度、叶轮直径。
- 逐风速点结果：风速、功率、理论风功率、Cp。
- 最终结果：`Cp,max`、对应风速、对应功率、对应理论风功率。
- 异常提示：是否存在 Cp 超过 `0.593`、缺失风速/功率、单位不明确等问题。

## 公开性说明

Cp 的计算公式和计算过程属于公开、通用的工程计算方法。

需要区分的是输入数据来源：

- 如果风速、功率、推力系数曲线来自公开产品手册、公开招标文件、公开论文或公开技术资料，可按公开资料处理。
- 如果数据来自厂家内部资料、投标专用资料，或带有“保密”“仅供项目使用”等标识的文件，不应简单视为公开资料。

报告中表述“根据机组功率曲线计算风能利用系数”通常没有问题，但不要泄露受限来源中的具体机型曲线数据。
