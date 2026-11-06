# 数据目录说明

这里放本地运行数据和备份。它不是稳定源码结构，默认不应该提交运行数据库。

## 文件

- `campus_lite.db`：本地 SQLite 数据库。
- `novel_state_backups/`：小说状态、数据库重置或迁移前的备份。
- `backups/`：新工具创建的 SQLite 一致性快照，每份包含数据库和校验清单。
- `recovery/`：恢复演练副本、旧数据索引等本地材料。

以上运行目录均不提交到 Git。备份和索引可能含私人数据，仅在本机保存。

## 备份、校验和恢复演练

从项目根目录运行（工具只依赖 Python 标准库）：

```powershell
python scripts/data_tools.py backup
```

默认源库读取环境变量 `CAMPUS_DB_PATH`，未设置时为 `data/campus_lite.db`。
Python 命令不自动执行 `config.local.ps1`：使用自定义库时先加载该配置，或显式传入
`--database`，避免备份到另一份库。

工具只读打开原库，通过 SQLite backup 接口获取一致性快照，包含 WAL 中已提交的数据，
不包含尚未提交的事务。每份备份使用新的独立目录，`manifest.json` 最后写入，记录 UTC 时间、
代码提交、工作区是否有改动、文件 SHA256、大小、主要表记录数和外键检查结果。
未生成清单的目录属于未完成备份，不要用于恢复。备份不是运行库，请保持关闭且不要编辑。
如果外键问题数量非零，表示快照中已有逻辑关联问题，不能把“完整性通过”解释为所有业务数据正常。

将命令输出的真实目录路径填入 `$backupFolder`，进行校验和恢复演练：

```powershell
$backupFolder = 'data/backups/实际备份目录'
python scripts/data_tools.py verify $backupFolder
python scripts/data_tools.py restore $backupFolder --destination data/recovery/drill-01/campus_lite.db
python scripts/data_tools.py inventory --database data/recovery/drill-01/campus_lite.db
```

`restore` 先校验备份，随后以独占方式创建新文件。目标已存在、存在 SQLite 伴随文件，
或目标为当前正式库时均拒绝执行。演练目录已存在时换一个新路径，不覆盖旧演练。
所有子命令成功返回 0，失败返回非零退出码。工具不会启动应用或初始化、迁移数据库。

实际切换正式库是一项独立维护操作：先备份当前库并验证恢复副本，停止并确认本项目后端
及其他写库进程退出，再保留现有数据库及相关伴随文件，最后才替换正式库并启动验收。
不要在服务运行时直接复制覆盖 `.db`，也不要将旧 `-wal` / `-shm` 文件混入恢复库。
本工具故意不提供覆盖正式库的选项。

备份只覆盖 SQLite 数据。浏览器 localStorage、人格测试答题记录、素材文件和模型环境配置
不在备份中。旧 `novel_state_backups/` 中的历史文件仍保留；它们没有新清单，不能直接传给
`verify/restore`。如需处理历史库，应先单独评估其 schema，不能自动当作当前格式使用。

## 旧会话与小说找回

先使用备份或恢复副本生成只读索引：

```powershell
python scripts/data_tools.py inventory --database data/recovery/drill-01/campus_lite.db
```

索引包含会话、访客、角色、项目之间的对应关系和记录数，不导出聊天或小说正文。
使用原库执行索引也不会写入应用数据；如需稳定的统计快照，使用已关闭的备份副本。

当前入口规则：

1. 浏览器的 `campus-pulse-lite-visitor` 保存当前访客 ID。换浏览器、清理站点数据或更换
   域名/端口后，此标识可能不存在。`localhost` 与 `127.0.0.1` 也属于不同来源。
2. `campus-pulse-lite-character:<visitor_id>` 保存该访客选择的角色 ID。
3. 后端以访客 ID + 角色 ID 查找会话，选择 `updated_at` 最新的一条；小说列表只加载该会话
   下未归档的项目。自建角色还需要匹配所有者，且角色未被删除。
4. 打开会话仅返回最近 40 条消息，更多消息仍在数据库中。会话导出接口可以导出完整内容。

找回步骤：

- 从索引的项目标题、角色、消息数和更新时间定位目标，再确定真实 `visitor_id`、
  `character_id`、`session_id`。不要根据新生成的空白访客猜测旧身份。
- 保留浏览器原有访客标识，使用开发者工具的站点存储面板，在本项目页面来源下修改上述
  两个 localStorage 值，然后刷新。此操作会在当前浏览器切换访客身份，不会合并访客。
- 打开对应角色，再进入小说工坊核对目标项目。打开页面会正常更新会话活动时间等运行数据；
  因此应在备份完成后操作，不把它当作只读检查。
- 若 `sessions_for_same_pair` 大于 1，当前页面未提供任意历史会话选择器；修改访客标识
  不保证打开指定旧会话。角色已删除、项目已归档也可能导致页面不显示，须单独处理，
  不要直接重写 ID 或调整时间戳来强行显示。

人格测试答题记录主要存储于浏览器；恢复 SQLite 无法找回已经清除的答题记录。

## 备份场景

建议在这些操作前备份数据库：

- 修改存储 schema 或 JSON 字段上限。
- 调整小说版本、`planning_snapshot`、Story Canvas 或 Novel State 语义。
- 重建项目事件池、章节事件绑定或画布回退逻辑。
- 手动清理本地数据库。

## 原则

- 本地数据库属于运行数据，不当作稳定源码结构。
- 结构性修复可以重建数据库，但重建前必须先备份。
- 小说状态或版本语义调整前，优先用上述工具创建并验证一致性备份。
- 如果需要复现问题，优先记录 API 步骤和必要 JSON 片段，不直接把完整数据库当文档。
