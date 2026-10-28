# DS620：Windows 现场配置

在**连接 DS620、运行照相馆网页的 Windows 电脑**上操作，使用活动现场实际运行浏览器的 Windows 账号。

1. 安装 DNP 官方 DS620 Windows 驱动和 Google Chrome，接通打印机，装入 4×6 英寸耗材。
2. 将本目录完整复制到电脑，双击 **`start-stamp.cmd`**。不要使用其他管理员账号代运行。
3. 启动文件固定使用 `DS620`、4×6 英寸（101.6×152.4mm）纸张、竖版输出、1 份；同时按驱动能力设置无边距、100% 缩放、每张 1 页。先配置并回读验证，再打开照相馆专用 Chrome 窗口。
4. 在这个窗口内点击“打印照片”，直接交给默认的 DS620，不需要再次确认打印预览。先出一张实物，确认邮票边缘完整、方向正确、只出一张，再用于活动。

启动文件通过 Chromium 的 `--kiosk-printing` 开启静默打印，并用 `--use-system-default-printer` 选择系统默认打印机。
使用独立的 `%LOCALAPPDATA%\Selfit\DS620\Chrome` 浏览器目录，避免被日常已打开的 Chrome 吞掉启动参数；
不修改其他浏览器窗口的启动方式或整机浏览器策略。这个专用窗口只用于活动网页，打印将不再弹出确认。
已存在专用窗口时会提示使用现有窗口；关闭后可重新运行启动文件。

浏览器实际使用的是 **Windows 默认打印机**，网页不能按名称强制绑定设备。启动时会确认默认值是 DS620；
活动期间请保持 DS620 为默认，不要切换到其他打印机。脚本启动成功不代表纸张已打印，仍需现场实物验收。
如果驱动未安装、纸张不支持或设置回读不一致，将停止启动，不会继续使用 PDF 或其他默认目标。

脚本从驱动原始 PrintCapabilities XML 读取纸张，包括标准列表可能遗漏的厂商自定义纸型；
按实际尺寸识别标称 101.6×152.4mm 和 DNP 手册列出的含出血 105×156.1mm，两者都属于 6 寸输出。
写入时保留驱动返回的纸张标识、命名空间和尺寸，不手工编造纸张编号，也不把纸张强改为自定义尺寸。
如果驱动把纸张描述为 6×4，脚本按驱动坐标旋转为竖版输出。多个可用纸型时优先保留当前合格的纸型，
否则优先普通 `(6x4)` / `4x6`；仍无法唯一确定则停止。2×6、6×4.5、6×8 和 `(6x4)xN` 拼版模式不作为目标。
纸张设定后，脚本读取该纸张对应的驱动能力；支持的标准选项会设置为 `PageBorderless = Borderless`、
`PageScalingFactor = 100`、`PagesPerSheet = 1`，保存后逐项回读。驱动拒绝或保存不一致时停止，并恢复旧首选项。
部分驱动只通过自己的界面提供这些选项，脚本会显示黄色 `NOT been verified` 提示；没有开放的选项不会被宣称已配置。
此时请在 **DS620 → 打印首选项 → Option / 选项** 中确认 **Border = Disable（关闭白边）**，
每张 1 页、缩放 100%。即使驱动没有公布能力，脚本发现已知的有边距、非 100% 缩放或多页拼版设置时也会停止。
`READY` 表示默认打印机和已支持的设置回读通过，不代表未开放的设置或实体出片已验收。
旧打印首选项备份到 `%LOCALAPPDATA%\Selfit\Printing\日期时间\`。如果 Windows 让系统自动管理默认打印机，可在“打印机和扫描仪”中关闭该选项，避免后续使用其他打印机时默认目标变化。

实物纸张仍为 4×6 英寸（101.6×152.4mm），网页打印文档改为 DS620 的含出血区域 **105×156.1mm**，
生成 **1240×1844** 打印专用 PNG。完整原邮票等比缩放到 1200×1600，居中放在 1200×1800 的标称纸面中，
四边再延展底色，包含左右各 20 像素、上下各 22 像素的出血。只延展底色，不拉伸或裁切人物、文字、邮票框。
先前 900×1350 版本解决了上下约 8.47mm 的比例白边，但打印文档仍为标称尺寸，未覆盖驱动含出血区域。
本次网页补齐约每边 1.7–1.85mm 的差额；请刷新网页使用新版，已经能启动的 v3 包可继续使用，无需重配。
不改变扫码保存和分享的 900×1200 原图。透明底仍按白色相纸处理；驱动 Border 必须为 Disable。
驱动仍使用普通 4×6（有的驱动显示 6×4），不改成 6×4.5 或 6×8。不要选择“填充并裁切”或强行拉伸，先出一张实物确认边缘。

### 更新配置包（2026-10-28 v3）

关闭照相馆专用 Chrome 窗口，将新版压缩包**完整解压**到现场电脑，进入 `selfit-ds620-windows` 文件夹，
双击新版 `start-stamp.cmd`。不要在压缩包预览窗口里直接运行，也不要只替换 `.cmd`：本次包含新的 `ds620-media.ps1`，必须与 `configure-ds620.ps1` 一起放在同一目录。
纸张尺寸保持 6 寸；v2 添加了驱动布局设置与校验，v3 修复自定义纸张和含出血尺寸的识别；网页端的出血修复通过刷新页面更新。
重新打开网页后打印一张，确认背景铺到纸边、邮票边缘完整、没有多页拼版；如有黄色提示，先按提示确认驱动选项。

### 出现“0 matching 4x6 forms”

旧包通过 .NET 的标准纸型集合查找纸张，厂商自定义纸型可能不在该集合中；旧尺寸匹配也没有覆盖 DNP 的含出血打印区域。
因此这条提示不能证明打印机不支持 6 寸。请先完整替换为 v3，重新双击 `start-stamp.cmd`。
新版会在写入任何打印配置之前输出驱动实际纸型，并保存到
`%LOCALAPPDATA%\Selfit\Printing\日期时间\paper-sizes.txt`，同目录包含原始 `print-capabilities.xml` 和旧打印首选项。
如果仍无法识别，请提供该 `paper-sizes.txt`；无需反复更换耗材、使用管理员账号或猜纸张编号。

需要普通确认模式时，运行 `configure-ds620.cmd` 后自行在普通浏览器打开网页；首次在打印窗口确认 DS620、4×6、纵向、每张 1 页、无页眉页脚。普通浏览器可能保留历史打印目标，不具备上述专用窗口的静默参数。

如实际队列名不是 `DS620`，在 Windows PowerShell 中运行：

```powershell
.\configure-ds620.ps1 -PrinterName '实际打印机名称'
# 只检查，不修改设置：
.\configure-ds620.ps1 -PrinterName 'DS620' -CheckOnly
```

### 出现“在此系统上禁止运行脚本”

这是 Windows PowerShell 在执行 `.ps1` 前的拦截，还没有运行到打印机配置。
请使用更新后的 `start-stamp.cmd`，不要直接双击 `.ps1`。
两个 `.cmd` 入口使用 `-ExecutionPolicy Bypass`，仅为本次 PowerShell 进程允许运行包内脚本；
进程退出即失效，不修改 `CurrentUser` / `LocalMachine` 的永久策略，也不关闭杀毒软件。
仅使用已确认来源的完整配置包；不需要用另一个管理员账号启动。

暂时不方便替换启动文件时，在命令提示符中运行（路径不同请调整）：

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%USERPROFILE%\Desktop\selfit-ds620-windows\start-stamp.ps1"
```

如果仍被拦截，在 PowerShell 运行 `Get-ExecutionPolicy -List` 查看来源。
`MachinePolicy` / `UserPolicy` 是组织组策略，优先于本次进程参数；如果它们禁止运行脚本，
请由现场管理员按组织规则批准，本包不会修改或覆盖组织策略。
也可手动在 Windows 的“打印机和扫描仪 → DS620 → 打印首选项”选择普通 4×6 纸张，并设为默认打印机。
当前配置包在 macOS 开发环境中准备，尚未在现场 DS620 驱动上验收；只有脚本回读校验通过才显示 `READY`。

参考：[DNP DS620 纸张规格](https://www.shop.dnpphoto.eu/documents/product/DS620_PrintSizes.pdf)、
[Microsoft 当前用户打印首选项](https://learn.microsoft.com/en-us/dotnet/api/system.printing.printqueue.userprintticket)、
[Microsoft 无边距设置](https://learn.microsoft.com/en-us/dotnet/api/system.printing.printticket.pageborderless)、
[Microsoft 缩放设置](https://learn.microsoft.com/en-us/dotnet/api/system.printing.printticket.pagescalingfactor)、
[DNP DS620 驱动手册（Border 选项）](https://dnpphoto.eu/wp-content/uploads/2025/08/DP-DS620_PrinterDriverInstruction_For7810_V1.0.5.2_1_English.pdf)、
[DNP DS620 驱动手册（第 31 页打印区域）](https://dnpphoto.com/Portals/0/Resources/DS620_Driver_Instruction_For7%2C8%2C10_V2.0.1.1_English.pdf)、
[.NET 标准纸型集合的实现](https://source.dot.net/ReachFramework/PrintConfig/PageMediaSize.cs.html)、
[Microsoft 默认打印机设置](https://learn.microsoft.com/en-us/powershell/scripting/samples/working-with-printers)、
[Microsoft PowerShell 执行策略与进程作用域](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1)、
[Chromium 打印启动参数](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/common/chrome_switches.cc)。
