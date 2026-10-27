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

网页打印文档是 4×6 英寸（101.6×152.4mm），原邮票图为 3:4；完整等比保留时上下各约 8.47mm 留白。不要选“填充并裁切”或强行拉伸。

需要普通确认模式时，运行 `configure-ds620.cmd` 后自行在普通浏览器打开网页；首次在打印窗口确认 DS620、4×6、纵向、每张 1 页、无页眉页脚。普通浏览器可能保留历史打印目标，不具备上述专用窗口的静默参数。

如实际队列名不是 `DS620`，在 Windows PowerShell 中运行：

```powershell
.\configure-ds620.ps1 -PrinterName '实际打印机名称'
# 只检查，不修改设置：
.\configure-ds620.ps1 -PrinterName 'DS620' -CheckOnly
```

如果组织策略禁止运行脚本，请由现场管理员按组织规则批准；本配置包不会关闭执行策略或安全功能。
也可手动在 Windows 的“打印机和扫描仪 → DS620 → 打印首选项”选择普通 4×6 纸张，并设为默认打印机。
当前配置包在 macOS 开发环境中准备，尚未在现场 DS620 驱动上验收；只有脚本回读校验通过才显示 `READY`。

参考：[DNP DS620 纸张规格](https://www.shop.dnpphoto.eu/documents/product/DS620_PrintSizes.pdf)、
[Microsoft 当前用户打印首选项](https://learn.microsoft.com/en-us/dotnet/api/system.printing.printqueue.userprintticket)、
[Microsoft 默认打印机设置](https://learn.microsoft.com/en-us/powershell/scripting/samples/working-with-printers)、
[Chromium 打印启动参数](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/common/chrome_switches.cc)。
