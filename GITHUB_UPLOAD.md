# GitHub 上传说明（V3.10.3）

本目录是完整源码结构，不是增量补丁。

- 解压后进入本目录。
- 在 GitHub 仓库根目录使用 **Add file → Upload files**。
- 为保留目录结构，请拖入顶层文件夹（`agents`、`config`、`creator_hub`、`data`、`docs`、`exports`、`output`、`scripts`）以及顶层文件，不要把所有子目录中的文件先扁平化选中。
- 本包不包含 `creator_hub.sqlite`、API Key、输出、备份或业务表格。

重新部署后可运行 `setup.cmd`；已有数据库迁移到新设备时，将一致性备份放到 `data/creator_hub.sqlite`，再运行 `upgrade.cmd`。
