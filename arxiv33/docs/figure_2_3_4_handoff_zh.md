# Figure 2/3/4 交接说明

## 1. 目的

这份文档用于把主文 Figure 2、Figure 3、Figure 4 的绘图脚本、产物路径、构建方式和当前仍需注意的问题交接给下一位修改者。

当前论文使用的是 `elsarticle` 预印本版式，主文图片由 `paper/main.tex` 直接插入 `paper/Fig/` 下的导出文件。

## 2. 图号与文件映射

主文图号对应关系如下：

- Figure 2
  - LaTeX 引用文件：`paper/Fig/result_main_depth.pdf`
  - LaTeX 位置：`paper/main.tex` 中 `\includegraphics[width=\textwidth]{Fig/result_main_depth.pdf}`
  - 当前产物：
    - `paper/Fig/result_main_depth.pdf`
    - `paper/Fig/result_main_depth.png`

- Figure 3
  - LaTeX 引用文件：`paper/Fig/result_tradeoff_map.pdf`
  - LaTeX 位置：`paper/main.tex` 中 `\includegraphics[width=\textwidth]{Fig/result_tradeoff_map.pdf}`
  - 当前产物：
    - `paper/Fig/result_tradeoff_map.pdf`
    - `paper/Fig/result_tradeoff_map.png`

- Figure 4
  - LaTeX 引用文件：`paper/Fig/result_tightened_refinement.pdf`
  - LaTeX 位置：`paper/main.tex` 中 `\includegraphics[width=\textwidth]{Fig/result_tightened_refinement.pdf}`
  - 当前产物：
    - `paper/Fig/result_tightened_refinement.pdf`
    - `paper/Fig/result_tightened_refinement.png`

注意：

- `paper/Fig/result_repair_audit.*` 是主文 Figure 5，不在这次交接重点内。
- supplement 里的超参数三联图不是这里的 Figure 4。supplement 的那张图对应 `hyperparam_1/2/3_sensitivity.*`。

## 3. 真正相关的脚本

### 3.1 Figure 2 的正式脚本

Figure 2 的正式生成脚本在：

- `scripts/build_submission_assets.py`

关键函数：

- `label_panel()`：统一 panel label
- `plot_main_depth()`：生成主文 Figure 2
- `export()`：导出到 `paper/Fig/`

当前相关位置：

- `scripts/build_submission_assets.py:111`
- `scripts/build_submission_assets.py:384`

运行后会直接更新：

- `paper/Fig/result_main_depth.pdf`
- `paper/Fig/result_main_depth.png`

### 3.2 Figure 2/3/4 的迭代版脚本

更完整的多 panel 主图逻辑在：

- `scripts/generate_tmp_figures_v1.py`

关键函数：

- `add_panel_label()`：panel label 放置
- `add_offset_label()`：点标签/短标注
- `place_avoiding_labels()`：标签避让逻辑
- `plot_fig02_main_depth()`：Figure 2 的迭代版
- `plot_fig03_tradeoff()`：Figure 3 的主要来源
- `plot_fig04_refinement()`：Figure 4 的主要来源
- `export_figure()`：导出 `png/pdf/svg`

当前相关位置：

- `scripts/generate_tmp_figures_v1.py:184`
- `scripts/generate_tmp_figures_v1.py:233`
- `scripts/generate_tmp_figures_v1.py:314`
- `scripts/generate_tmp_figures_v1.py:884`
- `scripts/generate_tmp_figures_v1.py:1016`
- `scripts/generate_tmp_figures_v1.py:1327`

运行后默认更新：

- `tmp/figures_v1/fig02_main_pedagogical_depth.*`
- `tmp/figures_v1/fig03_preservation_tradeoff.*`
- `tmp/figures_v1/fig04_tightened_refinement_before_after.*`

### 3.3 现有的现实情况

当前仓库里存在两套并行图形来源：

- 一套是 `scripts/build_submission_assets.py`，会直接写到 `paper/Fig/`
- 一套是 `scripts/generate_tmp_figures_v1.py`，会先写到 `tmp/figures_v1/`

Figure 2 在正式脚本里可以直接生成。

Figure 3 和 Figure 4 的论文成图目前更接近 `generate_tmp_figures_v1.py` 这套 2x2 主图逻辑，再通过手动同步覆盖到 `paper/Fig/`。也就是说，Figure 3/4 的“真实 source of truth”在代码层面仍然是不够干净的。

## 4. 当前修改过的点

为了压住“标签遮挡”和“子图互相挤占”问题，当前已做过这些调整：

- Figure 2
  - 顶部 legend 下移并留出更稳定的上边距
  - delta 标注改为带白色描边，避免压在误差线附近时看不清
  - `subplots_adjust(top=..., bottom=...)` 重新分配

- Figure 3
  - 2x2 panel 的 `wspace` / `hspace` 增大
  - 顶部两组 legend 合并为一组全局 legend
  - `heat_ax` 的 colorbar 变窄并增大 pad
  - A/B/D 面板的点标签不再完全依赖固定 offset，而是先给一个偏移候选，再用 `place_avoiding_labels()` 做简单避让

- Figure 4
  - 2x2 panel 的 `wspace` / `hspace` 增大
  - 上排散点图标签接入 `place_avoiding_labels()`
  - 两条 colorbar 的 pad 变大
  - D 面板 legend 移到图上方，尽量不占数据区

## 5. 当前仍然存在的问题

下面这些问题仍然存在，交给下一位修改者时必须明确说明。

### 5.1 Source of truth 不唯一

这是目前最大的工程问题。

- Figure 2 的正式版本在 `build_submission_assets.py`
- Figure 3/4 的版式逻辑主要在 `generate_tmp_figures_v1.py`
- `paper/Fig/result_tradeoff_map.*` 和 `paper/Fig/result_tightened_refinement.*` 目前不是由一个唯一脚本自动生成并自动同步

风险：

- 改了 `tmp/figures_v1` 但没同步到 `paper/Fig`，论文不会变
- 改了 `paper/Fig` 的现成文件但没改脚本，下次重跑又会被覆盖
- 别人接手时很容易改错入口

建议：

- 最终应把 Figure 3/4 也统一收进一个正式导图脚本，避免手动复制

### 5.2 标签避让还是“轻量版”，不是完全自动布局

现在的 `place_avoiding_labels()` 只做了有限度的避让：

- 会尝试多个 offset 候选
- 会避免和已经放置的其他标签重叠
- 会尽量不越过当前 axes 边界

但它还没有做这些事：

- 不检测与 marker、折线、误差线、热图数值本体的碰撞
- 不检测与 legend/colorbar 的碰撞
- 不做全图级别的标签优化
- 不做跨 panel 的复杂约束求解

这意味着：

- 在数据点极密集时，仍然可能出现“标签虽然不撞标签，但还是压到点或线”的情况
- Figure 3 和 Figure 4 仍然需要人工目检

### 5.3 Figure 3 仍然是最复杂、最脆弱的一张

Figure 3 同时有：

- 上排两个轨迹散点 panel
- 下排一个 heatmap
- 下排一个 frontier scatter
- 全局 legend
- heatmap colorbar
- 多个数据标签

这张图当前虽然比之前松了，但仍有几个高风险区域：

- 上排 A/B 中模型标签与轨迹线、marker 的相对位置仍需要肉眼确认
- C 面板 colorbar 和 D 面板之间虽然已经加开，但仍属于布局高压区
- D 面板的若干标签如果数据更新，可能重新挤到零轴附近

### 5.4 Figure 4 的上排点标签仍依赖数据分布

Figure 4 的上排两个 failure landscape 只给前两名 case 打标签。

当前逻辑已经做了边界方向判断和简单避让，但仍有这些限制：

- 只对 `head(2)` 的点做标签，若后续要标更多点，当前布局可能再次拥挤
- 数据一旦变动，最优 offset 可能变化
- 目前没有强制“不能碰到 marker 本体”的约束

### 5.5 panel label 仍然是轴外放置

虽然现在已经比原来更保守，但 panel label 本质上仍然是通过 `ax.transAxes` 放在轴边界附近，而不是占据单独的标题行。

风险：

- 一旦 figure size、caption 高度或导出 bbox 发生变化，仍可能出现裁切边缘过紧

### 5.6 没有自动化的“遮挡测试”

当前验收还是人工为主：

- 运行脚本
- 编译 `paper/main.tex`
- 查看 `paper/_pagecheck-13.png`
- 查看 `paper/_pagecheck-14.png`
- 查看 `paper/_pagecheck-15.png`

仓库里没有自动化检查来判断：

- 标签是否互相重叠
- 标签是否进入相邻 panel
- legend / colorbar 是否侵入邻图

### 5.7 supplement Figure 4 未处理

如果后续实际要修的是 supplement 的 Figure 4，也就是三联超参数敏感性图，那么当前这次改动没有覆盖它。

那部分对应脚本是：

- `scripts/generate_hybrid_mechanism_figures.py`

对应产物是：

- `paper/Fig/hyperparam_1_sensitivity.*`
- `paper/Fig/hyperparam_2_sensitivity.*`
- `paper/Fig/hyperparam_3_sensitivity.*`

那一组图当前依然是固定 legend、固定 `annotate("Default")` 和固定上边距逻辑，后续单独处理更稳妥。

## 6. 当前建议的修改顺序

如果下一位继续改，建议按这个顺序来：

1. 先统一 Figure 3/4 的正式生成入口  
不要再维持“tmp 生成后手工 copy 到 `paper/Fig`”的流程。

2. 再处理 Figure 3  
它是最拥挤、最容易复发遮挡问题的一张。

3. 再处理 Figure 4  
优先看上排标签与色条、下排 legend 的占位。

4. 最后再看 Figure 2  
Figure 2 现在已经相对稳定，通常只需要微调。

## 7. 推荐运行命令

当前机器上可用的是 conda 环境，已经验证 `base` 环境可跑这些绘图脚本。

### 7.1 生成 Figure 2 的正式产物

```powershell
conda run -n base python scripts\build_submission_assets.py
```

### 7.2 生成 Figure 2/3/4 的迭代版产物

```powershell
conda run -n base python scripts\generate_tmp_figures_v1.py
```

### 7.3 当前人工同步方式

Figure 3/4 现在仍需要把 `tmp` 产物拷回 `paper/Fig`：

```powershell
Copy-Item tmp\figures_v1\fig03_preservation_tradeoff.pdf paper\Fig\result_tradeoff_map.pdf -Force
Copy-Item tmp\figures_v1\fig03_preservation_tradeoff.png paper\Fig\result_tradeoff_map.png -Force
Copy-Item tmp\figures_v1\fig04_tightened_refinement_before_after.pdf paper\Fig\result_tightened_refinement.pdf -Force
Copy-Item tmp\figures_v1\fig04_tightened_refinement_before_after.png paper\Fig\result_tightened_refinement.png -Force
```

### 7.4 重编论文

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_paper.ps1
```

### 7.5 生成页面检查图

```powershell
pdftoppm -png -f 13 -l 15 paper\main.pdf paper\_pagecheck
pdftoppm -png -cropbox -f 13 -l 15 paper\main.pdf paper\_trimcheck
```

## 8. 需要重点看的文件

如果别人只看最少文件，优先顺序如下：

- `paper/main.tex`
- `scripts/build_submission_assets.py`
- `scripts/generate_tmp_figures_v1.py`
- `paper/Fig/result_main_depth.pdf`
- `paper/Fig/result_tradeoff_map.pdf`
- `paper/Fig/result_tightened_refinement.pdf`
- `paper/_pagecheck-13.png`
- `paper/_pagecheck-14.png`
- `paper/_pagecheck-15.png`

## 9. 一句话结论

当前最关键的问题不是“不会画”，而是 Figure 2/3/4 的生成入口和正式产物没有完全统一，尤其 Figure 3/4 仍然存在脚本分叉、手工同步和轻量避让逻辑三个结构性风险点。后续真正稳定这三张图，应该先统一 source of truth，再继续细修标签和 panel 布局。
