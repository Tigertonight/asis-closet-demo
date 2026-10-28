# DS620：Windows 现场配置

在**连接 DS620、运行照相馆网页的 Windows 电脑**上操作，使用活动现场实际运行浏览器的 Windows 账号。

1. 安装 DNP 官方 DS620 Windows 驱动和 Google Chrome，接通打印机，装入 4×6 英寸耗材。
2. 将本目录完整复制到电脑，双击 **`start-stamp.cmd`**。不要使用其他管理员账号代运行。
3. 启动文件固定使用 `DS620`、6 寸纸张、竖版输出、1 份；先配置并回读验证，再打开照相馆专用 Chrome 窗口。
4. 在这个窗口内点击“打印照片”，直接交给默认的 DS620，不需要再次确认打印预览。先出一张实物，确认邮票边缘完整、方向正确、只出一张，再用于活动。

启动文件通过 Chromium 的 `--kiosk-printing` 开启静默打印，并用 `--use-system-default-printer` 选择系统默认打印机。
使用独立的 `%LOCALAPPDATA%\Selfit\DS620\Chrome` 浏览器目录，避免被日常已打开的 Chrome 吞掉启动参数；
不修改其他浏览器窗口的启动方式或整机浏览器策略。这个专用窗口只用于活动网页，打印将不再弹出确认。
已存在专用窗口时会提示使用现有窗口；关闭后可重新运行启动文件。

浏览器实际使用的是 **Windows 默认打印机**，网页不能按名称强制绑定设备。启动时会确认默认值是 DS620；
活动期间请保持 DS620 为默认，不要切换到其他打印机。脚本启动成功不代表纸张已打印，仍需现场实物验收。
如果驱动未安装、纸张不支持或设置回读不一致，将停止启动，不会继续使用 PDF 或其他默认目标。

脚本按 DS620 驱动报告的真实纸张尺寸匹配 6 寸，设置当前用户的默认打印机与打印首选项，不打印测试照片。
如果驱动把纸张描述为 6×4，脚本按驱动坐标旋转为竖版输出。找不到打印机、纸张不存在或存在多个同尺寸选项时会停止，不会猜测表单编号。
旧打印首选项备份到 `%LOCALAPPDATA%\Selfit\Printing\日期时间\`。如果 Windows 让系统自动管理默认打印机，可在“打印机和扫描仪”中关闭该选项，避免后续使用其他打印机时默认目标变化。

网页打印文档是 4×6 英寸（101.6×152.4mm）。原邮票图为 3:4；旧版直接居中打印会在上下各留约 8.47mm 白边。
2026-10-28 网页改为生成 900×1350（2:3）的打印专用图：完整保留原邮票，上下延展相同的边缘底色，
避免比例差造成白边。请刷新网页使用新版；不改变扫码保存和分享的原图。透明底仍按白色相纸处理。
驱动仍需选普通 4×6、无边距及正确缩放；不要选择“填充并裁切”或强行拉伸，先出一张实物确认边缘。

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
[Microsoft 默认打印机设置](https://learn.microsoft.com/en-us/powershell/scripting/samples/working-with-printers)、
[Microsoft PowerShell 执行策略与进程作用域](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1)、
[Chromium 打印启动参数](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/common/chrome_switches.cc)。
